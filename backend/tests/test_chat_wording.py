"""Язык ответа = язык запроса, и без смешения (doc 17 § Язык ответа, doc 16 v0.10).

История правила — важна, чтобы его снова не «починили» в обратную сторону:

1. Изначально проза модели шла на языке задачи, а строки бэкенда («How they scored:»,
   «Left out:») были английскими всегда. Владелец увидел в интерфейсе смесь: английская
   строка над русским абзацем — и потребовал единообразия.
2. Первым решением сделали **всё английским**. Владелец уточнил: пусть ответ идёт на
   языке запроса — русский вопрос, русский ответ.
3. Итог: язык запроса ведёт **и прозу модели, и наши строки внутри ответа**. Подписи
   интерфейса (кнопки, табы, статусы) остаются английскими — это мебель, не ответ.

Плюс отдельно: служебный текст (стек Playwright) в переписку не попадает ни на каком
языке — владелец видел три строки `at UtilityScript…` в чате.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.reporting.phrasing import Phrases, task_language
from tests.conftest import REPO_ROOT

PROMPTS = REPO_ROOT / "data" / "prompts"
DATA = Settings(data_dir=REPO_ROOT / "data").data_dir

STACK = (
    "Page.evaluate: TypeError: Cannot read properties of null (reading 'innerText')\n"
    "    at eval (eval at evaluate (:303:30), <anonymous>:9:24)\n"
    "    at UtilityScript.evaluate (<anonymous>:310:18)"
)

RU_TASK = "Найди самый подробный материал про искусственный интеллект"
EN_TASK = "Find the most detailed article about releases"


def say(task: str) -> Phrases:
    return Phrases.load(DATA, task)


# --- определение языка запроса ---


def test_language_comes_from_the_request_not_the_sites():
    assert task_language(RU_TASK) == "ru"
    assert task_language(EN_TASK) == "en"


def test_mixed_request_counts_as_russian():
    """«найди pricing page» — человек обращается по-русски, отвечаем так же."""
    assert task_language("найди pricing page на сайте") == "ru"


def test_empty_task_falls_back_to_english():
    assert task_language("") == "en"


# --- ответ целиком на одном языке ---


def test_russian_request_gets_russian_scaffolding():
    ru = say(RU_TASK)
    assert ru.say("scored", scores="lenta.ru 10/100") == "Оценки: lenta.ru 10/100"
    assert ru.say("left_out", items="habr.com — не удалось прочитать").startswith("Не вошли:")
    assert "сохранён" in ru.say("report_saved", name="comparison_report.md")


def test_english_request_keeps_english_scaffolding():
    en = say(EN_TASK)
    assert en.say("scored", scores="a.com 10/100") == "How they scored: a.com 10/100"
    assert en.say("left_out", items="b.com — couldn't be read").startswith("Left out:")


def test_no_mixing_inside_one_answer():
    """Главный дефект: наша строка на одном языке, проза модели на другом."""
    ru, en = say(RU_TASK), say(EN_TASK)
    for key, kwargs in (
        ("scored", {"scores": "x"}),
        ("left_out", {"items": "x"}),
        ("reading", {"site": "x"}),
        ("report_saved", {"name": "x"}),
    ):
        assert not _has_cyrillic(en.say(key, **kwargs)), f"английский ответ: {key}"
        assert _has_cyrillic(ru.say(key, **kwargs)), f"русский ответ: {key}"


def test_exclusion_reason_follows_the_request_language():
    assert say(RU_TASK).exclusion_reason("failed", None, None) == "не удалось прочитать"
    assert say(EN_TASK).exclusion_reason("failed", None, None) == "couldn't be read"


def test_progress_notes_follow_the_request_language():
    assert say(RU_TASK).say("reading_site", site="lenta.ru", index=1, total=2) == (
        "Читаю lenta.ru — сайт 1 из 2"
    )
    assert say(EN_TASK).say("reading_site", site="a.com", index=1, total=2) == ("Reading a.com — site 1 of 2")


def test_unknown_phrase_key_fails_loudly():
    """Опечатка в ключе — ошибка конфигурации, а не пустая строка в интерфейсе."""
    with pytest.raises(KeyError):
        say(EN_TASK).say("no_such_phrase")


# --- служебный текст не попадает в переписку ни на каком языке ---


def test_stack_trace_never_reaches_the_chat_in_either_language():
    for task, expected in ((EN_TASK, "couldn't be read"), (RU_TASK, "не удалось прочитать")):
        reason = say(task).exclusion_reason("failed", None, STACK)
        assert "UtilityScript" not in reason
        assert "TypeError" not in reason
        assert reason.startswith(expected)


def test_known_technical_causes_are_translated():
    assert say(EN_TASK).humanize_detail(STACK) == "the page never finished loading"
    assert say(RU_TASK).humanize_detail(STACK) == "страница так и не догрузилась"
    assert say(RU_TASK).humanize_detail("Page.goto: Timeout 30000ms exceeded") == (
        "сайт не ответил за отведённое время"
    )


def test_unrecognized_long_text_is_dropped_entirely():
    noise = "SomeInternalError: " + "x" * 200
    assert say(EN_TASK).humanize_detail(noise) == ""
    assert say(RU_TASK).exclusion_reason("failed", None, noise) == "не удалось прочитать"


def test_blocker_names_pass_through():
    """`blocked_by` — наш короткий словарь, прятать его не надо."""
    assert say(EN_TASK).exclusion_reason("blocked", "captcha", None) == "blocked us — captcha"
    assert say(RU_TASK).exclusion_reason("blocked", "captcha", None) == "закрылся от нас — captcha"


# --- промпты ---


def test_prompts_ask_for_the_task_language():
    for name in ("synthesizer_system.txt", "compare_system.txt"):
        text = (PROMPTS / name).read_text(encoding="utf-8")
        assert "language of the TASK" in text, name
        assert "Write everything in English" not in text, "правило «всегда английский» отменено"


def test_quotes_stay_verbatim_in_both_prompts():
    """Перевод цитаты сорвал бы сверку S-H3 против DOM — это не стилистика."""
    for name in ("synthesizer_system.txt", "compare_system.txt"):
        text = (PROMPTS / name).read_text(encoding="utf-8")
        assert "verbatim" in text.lower(), name


def _has_cyrillic(text: str) -> bool:
    return any("а" <= ch.casefold() <= "я" or ch.casefold() == "ё" for ch in text)


def test_phrase_table_covers_both_languages_symmetrically():
    """Пропущенный ключ в одном языке = тихий английский в русском ответе."""
    import yaml

    table = yaml.safe_load((DATA / "phrasing" / "chat_phrases.yaml").read_text(encoding="utf-8"))
    assert set(table["en"]) == set(table["ru"])
    assert set(table["exclusion"]["en"]) == set(table["exclusion"]["ru"])
    assert set(table["technical"]["en"]) == set(table["technical"]["ru"])


def test_phrase_file_lives_in_data_not_code():
    assert Path(DATA / "phrasing" / "chat_phrases.yaml").exists()
