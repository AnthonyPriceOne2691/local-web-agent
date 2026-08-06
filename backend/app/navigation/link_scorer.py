"""Link scoring (doc 21 формула; doc 04 fallback).

**Правка после испытания T-3d (doc 26):** формула была контекстно-слепа и вела агента
в сторону от ответа. На трёх реальных порталах со статьями про ставки агент прошёл
раздел → раздел → раздел и не открыл ни одной статьи, после чего заявил, что статей на
сайтах нет — при том, что они там есть.

Причина в весах: `slug` (+12) и `shallow` (+3) достаются **страницам-спискам**
(`/news`, `/betting`, `/blog`), а ссылка на саму статью получала 0 — её заголовок
(«Как правильно делать ставки…») не совпадал с текстом задачи буквально, а путь
(`/wiki/3067963-...`) не совпадал ни с одним слугом. Агент шёл туда, где счёт выше.

Что изменено:

1. **Тема важнее формы.** Первая версия правки дала форме URL больше веса, чем теме
   (`entry` +12 против `task-kw` +10) — и агента начало тянуть в сторону: форма записи
   срабатывает на страницах турниров, тегах и видео, поэтому top-10 забивался
   нетематическими ссылками, у половины из которых текст вообще пустой. Модель выбирала
   вслепую. Теперь тема — главный вес, а `entry` только разрешает ничью между
   тематическими ссылками и добавляет мало, когда темы нет.
2. **`headline` — заголовок вместо навигационной подписи**: у ссылки в меню 1–2 слова,
   у статьи — фраза. Дешёвый признак, отделяющий запись от навигации.
3. **`slug` действует только на главной.** Словарь слугов существует, чтобы **войти** в
   раздел с корня; будучи внутри, прыжок в соседний раздел — это и есть то самое
   блуждание (news → бонусы → букмекеры). Внутри раздела глубина важнее.
4. **Слова задачи сопоставляются началом слова** (`matching`), а не подстрокой, и
   отдельно учитывается префикс ≥4 символов: «ставки» должно ловить «ставках».
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, NamedTuple
from urllib.parse import urlparse

from app.navigation.matching import any_keyword, matches_keyword, task_words, transliterate
from app.navigation.path_hints import PathHints

FORBIDDEN_SUBSTR = ("/login", "/signin", "/signup", "/register", "/cart", "/checkout", "/wp-admin")
LEGAL_SUBSTR = ("/privacy", "/terms", "/cookie", "/legal")

# Форма URL записи: /2026/03/20/slug · /3067963-zagolovok · /article-3964176-... · .html
_DATE_IN_PATH = re.compile(r"/(19|20)\d{2}(/\d{1,2})?/")
_NUMERIC_ID = re.compile(r"/[a-z-]*\d{4,}[a-z0-9-]*")
_LONG_SLUG = re.compile(r"/[a-z0-9]+(?:-[a-z0-9]+){2,}")

_MIN_HEADLINE_WORDS = 4
_MIN_HEADLINE_CHARS = 25
_MIN_TASK_PREFIX = 4

# Веса: тема (20) > форма записи при теме (+8) > форма записи без темы (4).
# Порядок именно такой по замеру T-3d: при обратном соотношении агент уходил в
# нетематические записи (турниры, теги, видео) — doc 26 § T-3d.
W_TASK = 20
W_ENTRY_PLAIN = 4
W_ENTRY_ON_TOPIC = 8
W_HEADLINE = 6
W_BLIND = -4  # ссылка без текста и без темы: модель не может о ней судить
# Жанр «обучающее» ниже темы (20), но выше формы записи (8): он отвечает на «как делать X»,
# а форма отвечает только «это запись, а не раздел». Промо штрафуется как раз потому, что
# тему оно проходит, а ответа не содержит — замер hop-1 (doc 26 § T-3g).
#
# Двойной вес — по той же причине, что у формы записи: **жанр усиливает тему, но не
# заменяет её**. Замер: при одном весе безусловно `championat.com/guide/lifestyle` (жанр
# есть, темы нет, текст пуст) поднялся на #9 и вытеснил статью про ставки из top-10 — ровно
# та ошибка «форма выше темы», которая уже была сделана в T-3d.
W_LEARN_ON_TOPIC = 10
W_LEARN_PLAIN = 4
W_PROMO = -10
# Слово задачи, которого нет в контексте текущей страницы, — единственное, что различает
# ссылки **внутри** тематического раздела. Замер на хабе «Школа беттинга»: эталонная статья
# про футбол стояла #26 со счётом 38, а top-12 — «Как делать ставки в БК X» со счётом 44 при
# полностью совпадающих признаках; слова «делать» и «ставки» там знают все ссылки, потому что
# они уже в заголовке раздела. Вес выше разрыва в 6 очков (`headline`), но ниже темы.
W_SUBJECT = 8


def looks_like_entry(path: str) -> bool:
    """Похож ли путь на отдельную запись (статью), а не на раздел."""
    if path.endswith((".html", ".htm")):
        return True
    if _DATE_IN_PATH.search(path) or _NUMERIC_ID.search(path):
        return True
    # Длинный слуг из трёх и более слов — так выглядят заголовки в URL.
    return bool(_LONG_SLUG.search(path)) and path.rstrip("/").count("/") >= 2


def _looks_like_headline(text: str) -> bool:
    return len(text.split()) >= _MIN_HEADLINE_WORDS and len(text) >= _MIN_HEADLINE_CHARS


def _path_words(path: str) -> str:
    """Путь как текст: `/stavki-na-futbol` → «stavki na futbol».

    Нужно, чтобы тема ловилась и по URL, а не только по подписи ссылки: на живом
    прогоне половина ссылок в очереди имела пустой текст, и судить о них было нечем.
    """
    return path.replace("-", " ").replace("_", " ").replace("/", " ")


def _task_hit(text: str, words: tuple[str, ...]) -> bool:
    """Слово задачи в тексте: с начала слова и по префиксу (стем-подобно)."""
    for word in words:
        if matches_keyword(text, word) or matches_keyword(text, word[:_MIN_TASK_PREFIX]):
            return True
    return False


class TaskGenre(NamedTuple):
    """Жанровые словари, уже разобранные под конкретную задачу."""

    learn: tuple[str, ...]
    promo: tuple[str, ...]  # пусто, когда промо и есть запрос пользователя


@lru_cache(maxsize=256)
def _task_genre(task: str, learn: tuple[str, ...], promo: tuple[str, ...]) -> TaskGenre:
    """Штраф промо выключается, если о промо и спрашивают («найди бонусы букмекеров»).
    Транслит проверяется тоже: запрос может прийти латиницей («najdi bonusy»)."""
    low = task.casefold()
    asks_promo = any_keyword(low, promo) or any_keyword(transliterate(low), promo)
    return TaskGenre(learn=learn, promo=() if asks_promo else promo)


@lru_cache(maxsize=256)
def _task_forms(task: str, stopwords: frozenset[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Значимые слова задачи и их транслитерация. Кэш по задаче: на портале сотни ссылок,
    и разбирать одну и ту же задачу для каждой — впустую."""
    words = task_words(task, stopwords)
    return words, tuple(transliterate(w) for w in words)


@lru_cache(maxsize=256)
def _subject_words(task: str, stopwords: frozenset[str], page_context: str) -> tuple[str, ...]:
    """Слова задачи, которых **нет** в контексте текущей страницы (её URL + заголовок).

    Правило без параметров и потому переносимое: стоя в разделе «Школа ставок: обучение как
    делать ставки», слова «делать» и «ставки» знают все ссылки раздела — они уже в контексте,
    и различить ими нечего. Различает то, чего в контексте нет («футбол»).

    Пустой контекст (первый шаг, кэш homepage, пробы) → различающих слов нет вовсе: правило
    работает только там, где известно, где стоит агент.

    **Если контекст не знает ни одного слова задачи, правило тоже молчит** — и это не
    осторожность, а замер: на корне `championat.com` заголовок «Чемпионат.com: новости
    спорта» не содержит слов задачи, поэтому «различающими» становились все слова сразу,
    бонус получали десять случайных ссылок и ссылка на статью раздела ставок **вылетала из
    top-10**. Правило про сужение **внутри** раздела: нечего сужать — нечего и начислять.
    """
    if not page_context.strip():
        return ()
    words, translit = _task_forms(task, stopwords)
    known = _path_words(page_context.casefold())
    covered, rest = [], []
    for word, lat in zip(words, translit, strict=True):
        if _task_hit(known, (word,)) or _task_hit(known, (lat,)):
            covered.append(word)
        else:
            rest.append(word)
    return tuple(rest) if covered else ()


def _content_signals(
    text: str,
    path: str,
    task: str,
    *,
    hunting_article: bool,
    stopwords: frozenset[str],
    genre: TaskGenre,
    subject: tuple[str, ...],
) -> tuple[int, list[str]]:
    """Сигналы про СОДЕРЖАНИЕ: тема, форма записи, заголовок, нечитаемость.

    Порядок весов здесь и есть политика: тема главная, форма только разрешает ничью
    между тематическими ссылками (замер T-3d — при обратном соотношении агента тянуло
    в турниры, теги и видео).
    """
    score, tags = 0, []
    words, translit = _task_forms(task, stopwords)
    path_words = _path_words(path)
    # Транслит сопоставляется только с путём: текст ссылки на русском ловится словами как есть.
    on_topic = _task_hit(text, words) or _task_hit(path_words, words) or _task_hit(path_words, translit)
    if on_topic:
        score += W_TASK
        tags.append("task-kw")
    if looks_like_entry(path):
        score += W_ENTRY_ON_TOPIC if (hunting_article and on_topic) else W_ENTRY_PLAIN
        tags.append("entry")
    if hunting_article and _looks_like_headline(text):
        score += W_HEADLINE
        tags.append("headline")
    # Ссылка без читаемого текста и без темы — слепой выбор для модели: в очереди она
    # занимала место тематических (живой прогон: шесть таких в top-10 с пустым «»).
    if not text.strip() and not on_topic:
        score += W_BLIND
        tags.append("blind")
    # Слово задачи, которого нет в контексте страницы, — то самое, что различает ссылки
    # внутри раздела (замер на хабе «Школа беттинга», doc 21 § Выбор внутри раздела).
    if subject and (_task_hit(text, subject) or _task_hit(path_words, subject)):
        score += W_SUBJECT
        tags.append("subject")
    if hunting_article:
        score, tags = _genre_signals(score, tags, text, path_words, genre=genre, on_topic=on_topic)
    return score, tags


def _genre_signals(
    score: int, tags: list[str], text: str, path_words: str, *, genre: TaskGenre, on_topic: bool
) -> tuple[int, list[str]]:
    """Обучающий жанр против промо — только при охоте за статьёй.

    Задача «как делать ставки на футбол» просит **обучающий** материал, а формула не
    отличала его ни от новости, ни от бонусной акции: у промо есть и тема («ставки»), и
    форма записи, и длинный заголовок, поэтому на корне букмекерского обзорника промо
    занимало девять мест из десяти (замер hop-1, doc 26 § T-3g).

    Штраф промо снимается, если промо и есть запрос пользователя: «найди бонусы
    букмекеров» — законный сценарий, и ломать его нельзя.
    """
    haystack = f"{text} {path_words}"
    if any_keyword(haystack, genre.learn):
        score += W_LEARN_ON_TOPIC if on_topic else W_LEARN_PLAIN
        tags.append("learn")
    if genre.promo and any_keyword(haystack, genre.promo):
        score += W_PROMO
        tags.append("promo")
    return score, tags


def _section_signals(
    text: str, href: str, path: str, *, intent: str, hints: PathHints, on_homepage: bool
) -> tuple[int, list[str]]:
    """Сигналы про ВХОД В РАЗДЕЛ: словарь интента, слуг, юридические страницы, глубина.

    Слуг и малая глубина работают только когда мы ещё ищем раздел: при охоте за статьёй
    они тянули назад к спискам (news → бонусы → букмекеры на живом прогоне).
    """
    score, tags = 0, []
    hunting_article = intent == "content_search"
    keywords = [k.casefold() for k in hints.intent_keywords.get(intent, [])]
    slugs = [s.casefold() for s in hints.slugs_for(intent)]

    if on_homepage and any(k in text or k in href for k in keywords):
        score += 15
        tags.append("homepage+intent")
    if on_homepage and any(s in href for s in slugs):
        score += 12
        tags.append("slug")
    if intent == "contact" and any(s.casefold() in href for s in hints.legal_slugs):
        score += 8
        tags.append("legal-contact")
    if not hunting_article and path.rstrip("/").count("/") <= 1:
        score += 3
        tags.append("shallow")
    return score, tags


def _penalties(path: str, *, intent: str) -> tuple[int, list[str]]:
    """Штрафы ищутся в **пути**, а не во всём URL: `/legal` совпадало внутри
    `//legalbet.ru`, и каждая ссылка сайта-обзорника букмекеров теряла 8 очков как
    юридическая страница (найдено офлайн-оракулом, doc 26 § T-3e). Так же ловились
    `//cartier` на `/cart` и `//logincorp` на `/login`.

    Запрос сознательно не смотрим: штраф про то, что страница **является** корзиной или
    входом, а не про параметр `?next=/login` у обычной ссылки.
    """
    score, tags = 0, []
    if any(s in path for s in LEGAL_SUBSTR) and intent != "contact":
        score -= 8
        tags.append("legal-avoid")
    if any(s in path for s in FORBIDDEN_SUBSTR):
        score -= 10
        tags.append("forbidden")
    return score, tags


def score_link(
    link: dict[str, Any],
    *,
    intent: str,
    task: str,
    hints: PathHints,
    on_homepage: bool,
    page_context: str = "",
) -> tuple[int, str]:
    """`page_context` — URL и заголовок страницы, на которой агент стоит. Пусто = правило
    «различает то, чего нет в контексте» не действует (doc 21 § Выбор внутри раздела)."""
    href = link["href"].casefold()
    text = (link.get("text") or "").casefold()
    path = urlparse(href).path or "/"

    content = _content_signals(
        text,
        path,
        task,
        hunting_article=intent == "content_search",
        stopwords=hints.task_stopwords,
        genre=_task_genre(task, hints.learn_markers, hints.promo_markers),
        # На главной правило «различает то, чего нет в контексте» молчит: там агент выбирает
        # РАЗДЕЛ, а не сужает внутри него. Замер: иначе бонус получают ссылки по всему сайту,
        # и обучающий хаб на корне `legalbet.ru` съезжает с #1 на #7 (doc 21).
        subject=() if on_homepage else _subject_words(task, hints.task_stopwords, page_context),
    )
    section = _section_signals(text, href, path, intent=intent, hints=hints, on_homepage=on_homepage)
    penalty = _penalties(path, intent=intent)

    score = content[0] + section[0] + penalty[0]
    tags = section[1] + content[1] + penalty[1]
    return score, "+".join(tags) or "plain"
