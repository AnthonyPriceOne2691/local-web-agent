"""Сопоставление задачи со словарём ключевых слов (docs 21/24).

Правило одно, но важное: ключевик ищется **с начала слова**, а не любой
подстрокой. Найдено real-site прогоном 2026-08-01: короткое `ui` из дизайн-словаря
совпадало внутри `g-ui-de` и `b-ui-ld`, поэтому контентная задача «найди
getting started guide, чей полнее» уезжала в рубрику сравнения дизайна и таблица
заполнялась цветами и типографикой. На фикстурах не воспроизводилось — там в
задачах всегда стояли явные «дизайн» или «статья».

Правая граница сознательно НЕ проверяется: половина словаря — стемы
(`статья`/`статью`, `оплат`, `ваканс`), и `дизайна` обязано совпадать с `дизайн`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

_TASK_WORD = re.compile(r"[a-zа-яё0-9]{4,}", re.IGNORECASE)

# Кириллица → латиница, одна схема. Это **алфавит**, а не политика, поэтому таблица в
# коде, а не в data/: настраивать в ней нечего. Схемы транслитерации у сайтов разные
# (`ц` → c/ts, `х` → h/kh, `ю` → yu/iu), и совпадение по полному слову было бы лотереей —
# спасает то, что тема ищется **префиксом**: первые 4 символа у схем совпадают
# (`ставки` → stav…, `футбол` → futb…, `школа` → shko…).
_RU_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}  # fmt: skip


def transliterate(text: str) -> str:
    """Кириллица → латиница. Нужно, чтобы тема ловилась в путях вида `/stavki-na-futbol`:
    русские сайты пишут URL транслитом, а задача приходит по-русски — и правка «искать тему
    в словах пути» (T-3d) на таких путях не срабатывала вовсе (doc 26 § T-3g)."""
    return "".join(_RU_TO_LAT.get(ch, ch) for ch in text.casefold())


def task_words(task: str, stopwords: Iterable[str]) -> tuple[str, ...]:
    """Значимые слова задачи: от 4 символов, без служебных.

    Служебные слова отсекаются потому, что иначе «найди статью» становится темой: после
    транслитерации `статью` → `stat` совпадало с `/stat/football`, и страница статистики
    получала полный вес темы.
    """
    stop = {w.casefold() for w in stopwords}
    return tuple(w for w in _TASK_WORD.findall(task.casefold()) if w not in stop)


@lru_cache(maxsize=512)
def _pattern(keyword: str) -> re.Pattern[str]:
    # (?<![^\W\d_]) — перед ключевиком не буква: слово начинается здесь.
    return re.compile(rf"(?<![^\W\d_]){re.escape(keyword)}", re.IGNORECASE | re.UNICODE)


def matches_keyword(text: str, keyword: str) -> bool:
    """Есть ли ключевик в тексте как начало слова (стем допускается)."""
    return bool(keyword) and _pattern(keyword.casefold()).search(text) is not None


def count_keywords(text: str, keywords: Iterable[str]) -> int:
    """Сколько ключевиков словаря встретилось (для выбора лучшего интента)."""
    return sum(1 for kw in keywords if matches_keyword(text, kw))


def any_keyword(text: str, keywords: Iterable[str]) -> bool:
    return any(matches_keyword(text, kw) for kw in keywords)
