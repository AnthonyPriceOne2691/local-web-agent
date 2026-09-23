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
from app.reporting.phrasing import Phrases, clip_at_sentence, task_language
from app.research.runner import ResearchRunner
from app.schemas.research import ComparisonResult
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


# --- причина исключения обязана называть, кто именно не справился (T-3h) ---


def test_site_that_was_read_but_failed_at_synthesis_is_not_called_unreadable():
    """Живой прогон T-3h: `legalbet.ru` прочитал **4 страницы**, включая целевую статью, и
    упал на синтезе (`httpx.ReadTimeout` от локальной модели). Человеку сказали «не удалось
    прочитать — сайт не ответил за отведённое время»: неверно дважды — страницы прочитаны, и
    не ответила **модель**, а не сайт."""
    ru = say(RU_TASK).exclusion_reason("failed", None, "ReadTimeout", stage="SYNTHESIZE", pages_read=4)
    assert "4" in ru and "модель" in ru
    assert "сайт не ответил" not in ru

    en = say(EN_TASK).exclusion_reason("failed", None, "ReadTimeout", stage="SYNTHESIZE", pages_read=4)
    assert "4" in en and "model" in en
    assert not _has_cyrillic(en)


def test_site_where_no_page_opened_says_exactly_that():
    """Тот же прогон: `sports.ru` и `championat.com` дали 0 страниц (`Page.goto: Timeout`), и
    человек получил «не удалось прочитать» дважды без единой подробности."""
    reason = say(RU_TASK).exclusion_reason(
        "failed", None, "nav_error: Page.goto: Timeout 30000ms exceeded", pages_read=0
    )
    assert "ни одна страница не открылась" in reason
    assert "сайт не ответил за отведённое время" in reason


def test_ordinary_failure_wording_is_unchanged():
    """Негативный контроль: без контекста стадии формулировка та же, что была."""
    assert say(RU_TASK).exclusion_reason("failed", None, None) == "не удалось прочитать"
    assert say(EN_TASK).exclusion_reason("blocked", "captcha", None) == "blocked us — captcha"


# --- проза модели в чате режется по предложению, а не посреди слова ---

# Форма живого дефекта: сравнение хлебных сайтов (EN, 711 символов прозы) ушло в чат
# срезом `narrative[:600]`, и абзац закончился на «King Arthur's artic». Фикстура своя,
# но устроена так же: 600-й символ приходится на середину слова.
LONG_NARRATIVE = (
    "Alpha Baking's guide gives the most thorough explanation of baking bread at home, "
    "covering yeast science, storage and practical technique in detailed sections. "
    "Beta Food's 'Six steps to brilliant bread' (approx. 964 words) focuses on the "
    "fundamentals but lacks the depth of scientific explanation and the troubleshooting "
    "found in the Alpha guide. Gamma had no relevant bread-baking content at all; its "
    "pages focus on desserts and breakfast recipes instead of bread. Alpha's guide is "
    "more complete thanks to its breadth, with dedicated sections on flour, hydration, "
    "kneading, proofing and baking temperatures, and a long list of answers to common "
    "questions from readers. Beta remains a good start for beginners."
)


def test_chat_reply_never_ends_the_narrative_mid_word():
    """Целиком проза есть в панели «What we found»; в чате — законченные предложения."""
    assert LONG_NARRATIVE[599].isalpha() and LONG_NARRATIVE[600].isalpha(), "фикстура обязана резать слово"
    reply = ResearchRunner._chat_reply(
        ComparisonResult(narrative=LONG_NARRATIVE), "comparison_report.md", say(EN_TASK), []
    )
    paragraph = next(p for p in reply.split("\n\n") if p.startswith("Alpha Baking's guide"))
    assert LONG_NARRATIVE.startswith(paragraph)
    assert paragraph.endswith(".")
    assert len(paragraph) <= 600


def test_short_narrative_reaches_the_chat_whole():
    reply = ResearchRunner._chat_reply(
        ComparisonResult(narrative="a.com wins overall."), "comparison_report.md", say(EN_TASK), []
    )
    assert "a.com wins overall." in reply.split("\n\n")


def test_abbreviation_is_not_taken_for_the_end_of_a_sentence():
    """«approx. 964» — точка внутри предложения: за ней не заглавная буква."""
    text = "First point is short. Six steps to good bread (approx. 964 words) cover the basics."
    assert clip_at_sentence(text, 60) == "First point is short."


def test_text_without_a_sentence_end_is_cut_between_words():
    text = "one very long clause that goes on and on without ever reaching a full stop at all"
    clipped = clip_at_sentence(text, 40)
    assert clipped.endswith("…")
    head = clipped.removesuffix("…")
    assert text.startswith(head)
    assert text[len(head)] == " ", "обрезано посреди слова"


def test_sentence_clipping_works_for_cyrillic():
    text = "Первый пункт короткий. Второй пункт длиннее и продолжается дальше."
    assert clip_at_sentence(text, 40) == "Первый пункт короткий."


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
