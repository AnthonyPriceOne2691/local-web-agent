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
from typing import Any
from urllib.parse import urlparse

from app.navigation.matching import matches_keyword
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


def _looks_like_entry(path: str) -> bool:
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


def _task_hit(text: str, task: str) -> bool:
    """Слово задачи в тексте ссылки: с начала слова и по префиксу (стем-подобно)."""
    for word in task.casefold().split():
        stripped = word.strip(".,:;!?()«»\"'")
        if len(stripped) <= 3:
            continue
        if matches_keyword(text, stripped) or matches_keyword(text, stripped[:_MIN_TASK_PREFIX]):
            return True
    return False


def _content_signals(text: str, path: str, task: str, *, hunting_article: bool) -> tuple[int, list[str]]:
    """Сигналы про СОДЕРЖАНИЕ: тема, форма записи, заголовок, нечитаемость.

    Порядок весов здесь и есть политика: тема главная, форма только разрешает ничью
    между тематическими ссылками (замер T-3d — при обратном соотношении агента тянуло
    в турниры, теги и видео).
    """
    score, tags = 0, []
    on_topic = _task_hit(text, task) or _task_hit(_path_words(path), task)
    if on_topic:
        score += W_TASK
        tags.append("task-kw")
    if _looks_like_entry(path):
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
    link: dict[str, Any], *, intent: str, task: str, hints: PathHints, on_homepage: bool
) -> tuple[int, str]:
    href = link["href"].casefold()
    text = (link.get("text") or "").casefold()
    path = urlparse(href).path or "/"

    content = _content_signals(text, path, task, hunting_article=intent == "content_search")
    section = _section_signals(text, href, path, intent=intent, hints=hints, on_homepage=on_homepage)
    penalty = _penalties(path, intent=intent)

    score = content[0] + section[0] + penalty[0]
    tags = section[1] + content[1] + penalty[1]
    return score, "+".join(tags) or "plain"
