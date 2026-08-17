"""Слово задачи ловится по морфологии своего языка (doc 21 § Тема, doc 26 § T-3o).

Живой прогон магазинов 07.08 показал, что правило «префикс ≥4 символов», введённое для
русских окончаний (`ставки`/`ставок`), на английском ловит чужие слова:

| Ссылка на `sparkfun.com/terms` | Совпало со словом задачи | Как |
|---|---|---|
| «Screw / Spring **Terminals**» (товар) | `terms` | префикс `term` |
| «Read Our **Story**» | `store` | префикс `stor` |
| «Learn **More** About Teensy» (товар) | `more` | служебное слово, которого не было в стоп-листе |

Цена замерена: три товарные ссылки получили тот же счёт 31, что и настоящая цель
`/returns`, а `/support` — где у SparkFun и лежат условия доставки — остался с 3 баллами и
в очередь не попал вовсе. Агент ушёл на страницу товара.

Правило теперь по языку слова: кириллица — префикс (формы образуются окончаниями),
латиница — лёгкий стем целиком (`returns` ≡ `return`, но `terms` ≢ `terminals`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.navigation.link_scorer import score_link
from app.navigation.path_hints import PathHints

REPO = Path(__file__).resolve().parents[2]
SHOP_TASK = (
    "Find the shipping and returns policy, and compare which store explains delivery terms more clearly."
)
SHOP_CTX = "https://www.sparkfun.com/terms Terms Of Service - SparkFun Electronics"
RU_TASK = "Найди статью о том, как делать ставки на футбол, и сравни, где тема раскрыта полнее."
SHOP_BAKE_TASK = "Find an article that explains how to bake bread at home, and compare which site is better."


@pytest.fixture(scope="module")
def hints() -> PathHints:
    return PathHints.load(REPO / "data" / "navigation")


def _score(href: str, text: str, hints: PathHints, *, task: str, context: str = "") -> tuple[int, str]:
    return score_link(
        {"href": href, "text": text}, intent="generic", task=task, hints=hints,
        on_homepage=False, page_context=context,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("href", "text"),
    [
        ("https://www.sparkfun.com/components/connectors/screw.html", "Screw / Spring Terminals"),
        ("https://www.sparkfun.com/about-sparkfun", "Read Our Story"),
        ("https://www.sparkfun.com/teensy", "Learn More About Teensy"),
    ],
)
def test_english_lookalikes_do_not_count_as_topic(href: str, text: str, hints: PathHints):
    """Записи живого прогона: эти три ссылки получали тему, которой в них нет."""
    score, reason = _score(href, text, hints, task=SHOP_TASK, context=SHOP_CTX)
    assert "task-kw" not in reason, f"{text}: {reason}"


def test_real_target_still_scores_as_topic(hints: PathHints):
    """Обратная сторона: настоящие цели по-прежнему тематические, иначе лечили бы шум
    ценой ответа. `Return Policy` должен ловиться словом `returns` — это форма слова."""
    for href, text in (
        ("https://www.sparkfun.com/returns", "Returns & Exchanges"),
        ("https://www.sparkfun.com/returns", "Return Policy"),
        ("https://www.adafruit.com/shipping", "Shipping & Returns"),
        ("https://thepihut.com/pages/delivery", "Delivery"),
    ):
        _, reason = _score(href, text, hints, task=SHOP_TASK, context=SHOP_CTX)
        assert "task-kw" in reason, f"{text}: {reason}"


def test_verb_and_gerund_are_the_same_word(hints: PathHints):
    """`bake` и «Baking» — одно слово (doc 21 § Тема, doc 26 § T-3q).

    Замер очереди на корне `food52.com` объяснил промах живого прогона точнее, чем прежняя
    формулировка «тянет в записи»: раздел `/food/baking` с подписью «Baking» получил **ноль**
    баллов — агент не видел даже раздела выпечки, зато «NO BAKE» (мороженое, то есть «без
    выпечки») получило полный вес темы.

    Отсечения одного окончания мало: `baking` → «bak» короче порога, а `bake` не режется
    вовсе, и формы не встречаются. Поэтому слово раскрывается в НЕСКОЛЬКО форм (`bak`,
    `bake`), а совпадение ищется по пересечению — при этом `terms` и `terminals` остаются
    разными словами, ради чего правило и вводилось.
    """
    for text, expect in (
        ("Baking", True),
        ("Bread baking guide", True),
        ("Bakes and pastries", True),
        ("Spring Terminals", False),  # контроль: ложные пары не вернулись
        ("Read Our Story", False),
    ):
        _, reason = _score("https://food52.com/section", text, hints, task=SHOP_BAKE_TASK)
        assert ("task-kw" in reason) is expect, f"{text}: {reason}"


def test_help_desk_sections_are_known_resources(hints: PathHints):
    """Справочные разделы агент должен знать и применять (замечание владельца 07.08).

    `/support` и `/faq` — это структура сайта, а не предметная область: там лежат контакты,
    условия и ответы на вопросы. На живом прогоне магазинов обе ссылки получали 3 балла
    (только `shallow`) и в очередь не попадали, хотя у SparkFun условия доставки лежат
    именно на `/support`.

    Ключевое — **не только с главной**: слуги давали вес лишь на корне, а агент стоял на
    `/terms`. Раздел помощи полезен с любой страницы, в отличие от соседнего раздела темы.
    """
    for href, text in (
        ("https://www.sparkfun.com/support", "Support"),
        ("https://www.sparkfun.com/faq", "FAQs"),
        ("https://thepihut.com/pages/faqs", "FAQs"),
    ):
        score, reason = _score(href, text, hints, task=SHOP_TASK, context=SHOP_CTX)
        assert "help-desk" in reason, f"{href}: {reason}"
        assert score > 3, f"{href}: {score}"


def test_help_desk_never_outranks_the_topic(hints: PathHints):
    """Граница: справка — подсказка, а не ответ. Ссылка по теме обязана стоять выше."""
    on_topic, _ = _score(
        "https://www.adafruit.com/shipping", "Shipping & Returns", hints, task=SHOP_TASK, context=SHOP_CTX
    )
    help_desk, _ = _score(
        "https://www.sparkfun.com/support", "Support", hints, task=SHOP_TASK, context=SHOP_CTX
    )
    assert on_topic > help_desk


def test_shipping_task_gets_its_own_intent(hints: PathHints):
    """Задача про доставку/возврат больше не `generic`: у неё свой интент, а значит и
    F1-пробы (`/support`, `/faq`, `/shipping`) — агент найдёт раздел даже без ссылки."""
    from app.navigation.intent import classify_intent

    assert classify_intent(SHOP_TASK, hints) == "support"
    assert classify_intent("Где посмотреть условия доставки и возврата?", hints) == "support"
    # контроль: чужие задачи интент не перетягивают
    assert classify_intent(RU_TASK, hints) == "content_search"


def test_german_search_task_is_recognised_as_content_search(hints: PathHints):
    """Живой прогон немецких сайтов (doc 26 § T-3p): задача «Finde eine Anleitung…»
    классифицировалась как `generic`, потому что словарь интентов знал только RU и EN.

    Цена не в названии интента, а в трёх следствиях: у `generic` нет блог-слугов для проб,
    не запрашивается блок `article` (сравнение полноты шло по фактам-URL вместо объёма
    статьи) и синтез идёт быстрым путём вместо канонного, положенного поиску статьи.
    """
    from app.navigation.intent import classify_intent

    for task in (
        "Finde eine Anleitung, wie man Brot selbst backt, und vergleiche, welche Seite das Thema erklärt.",
        "Suche einen Artikel über Sauerteig",
        "Finde einen Ratgeber zum Brotbacken",
    ):
        assert classify_intent(task, hints) == "content_search", task

    # контроль: русские и английские задачи интент не сменили
    assert classify_intent(RU_TASK, hints) == "content_search"
    assert classify_intent(SHOP_TASK, hints) == "support"
    assert classify_intent("Wie ist die Lieferung und Rückgabe geregelt?", hints) == "support"


def test_words_with_diacritics_are_not_torn_apart(hints: PathHints):
    """Слово с диакритикой — одно слово, а не обломки (doc 21 § Тема).

    Найдено офлайн-разбором немецкой задачи ДО прогона: класс символов знал только `a-z` и
    `а-яё`, поэтому буквы вне этих алфавитов работали как разделители:

        gründlicher → «ndlicher»      erklärt → «erkl»      Brötchen → «tchen»

    Бьёт по любому языку с диакритикой — немецкий, французский, испанский, польский,
    турецкий, — и не только в задаче: по этим же обломкам ищется тема в тексте ссылок.
    """
    from app.navigation.matching import task_words

    # Слова здесь тематические, а не служебные: `gründlicher`/`erklärt` из формулировки
    # сравнения сами лежат в стоп-листе — на них проверялась бы не эта дыра, а он.
    for task, expected in (
        ("Anleitung: Brötchen backen in der Küche", ("brötchen", "küche")),
        ("Trouvez un guide pour préparer une baguette française", ("préparer", "française")),
        ("Encuentra una receta para preparar pan español", ("español",)),
    ):
        words = task_words(task, hints.task_stopwords)
        for word in expected:
            assert word in words, f"{task!r}: {word!r} не найдено в {words}"


def test_german_service_words_are_not_a_topic(hints: PathHints):
    """Служебные немецкие слова темой не считаются — тот же класс, что английское `more`."""
    from app.navigation.matching import task_words

    task = "Finde eine Anleitung, wie man Brot selbst backt, und vergleiche, welche Seite das Thema erklärt."
    words = task_words(task, hints.task_stopwords)
    for junk in ("eine", "welche", "seite", "thema", "selbst", "finde", "vergleiche"):
        assert junk not in words, f"{junk!r} попало в значимые слова: {words}"
    assert "brot" in words and "anleitung" in words  # тема осталась


def test_russian_endings_still_match_by_prefix(hints: PathHints):
    """Контроль по-русски: правило префикса для кириллицы остаётся — на нём держатся
    все прошлые замеры (эталон на хабе `legalbet`, вики `sports.ru`)."""
    for href, text in (
        ("https://legalbet.ru/shkola-bettinga/stavki-na-futbol", "Ставки на футбол"),
        ("https://legalbet.ru/shkola-bettinga/", "Школа ставок"),  # «ставок» ← «ставки»
        ("https://www.sports.ru/betting/stavochnaya-wiki", ""),  # тема только в транслите пути
    ):
        _, reason = _score(href, text, hints, task=RU_TASK)
        assert "task-kw" in reason, f"{text or href}: {reason}"
