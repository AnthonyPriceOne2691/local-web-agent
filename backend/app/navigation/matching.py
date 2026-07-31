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
