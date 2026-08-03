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

1. **`entry` — сигнал «ссылка похожа на запись, а не на раздел»**: дата в пути,
   числовой id, длинный слуг с дефисами, `.html`. Признаки структурные, а не под
   конкретные сайты: они описывают форму URL записи, которая одинакова у блогов,
   новостных лент и вики.
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


def _task_hit(text: str, task: str) -> bool:
    """Слово задачи в тексте ссылки: с начала слова и по префиксу (стем-подобно)."""
    for word in task.casefold().split():
        stripped = word.strip(".,:;!?()«»\"'")
        if len(stripped) <= 3:
            continue
        if matches_keyword(text, stripped) or matches_keyword(text, stripped[:_MIN_TASK_PREFIX]):
            return True
    return False


def score_link(
    link: dict[str, Any], *, intent: str, task: str, hints: PathHints, on_homepage: bool
) -> tuple[int, str]:
    href = link["href"].casefold()
    text = (link.get("text") or "").casefold()
    path = urlparse(href).path or "/"
    score, reasons = 0, []
    keywords = [k.casefold() for k in hints.intent_keywords.get(intent, [])]
    slugs = [s.casefold() for s in hints.slugs_for(intent)]
    hunting_article = intent == "content_search"

    if on_homepage and any(k in text or k in href for k in keywords):
        score += 15
        reasons.append("homepage+intent")
    # Слуг раздела — только с главной: внутри раздела он уводил в соседний раздел.
    if on_homepage and any(s in href for s in slugs):
        score += 12
        reasons.append("slug")
    if _task_hit(text, task):
        score += 10
        reasons.append("task-kw")
    if _looks_like_entry(path):
        # Ищем статью — запись важнее раздела; на прочих интентах это просто «глубже».
        score += 12 if hunting_article else 4
        reasons.append("entry")
    if hunting_article and _looks_like_headline(text):
        score += 6
        reasons.append("headline")
    if intent == "contact" and any(s.casefold() in href for s in hints.legal_slugs):
        score += 8
        reasons.append("legal-contact")
    # Малая глубина хороша, пока мы ищем раздел; при охоте за статьёй она тянет назад
    # к спискам, поэтому на content_search бонус не начисляется.
    if not hunting_article and path.rstrip("/").count("/") <= 1:
        score += 3
        reasons.append("shallow")
    if any(s in href for s in LEGAL_SUBSTR) and intent != "contact":
        score -= 8
        reasons.append("legal-avoid")
    if any(s in href for s in FORBIDDEN_SUBSTR):
        score -= 10
        reasons.append("forbidden")
    return score, "+".join(reasons) or "plain"
