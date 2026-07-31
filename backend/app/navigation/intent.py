"""Task → intent: casefold substring по двуязычному словарю RU+EN (doc 21)."""

from __future__ import annotations

from app.navigation.matching import count_keywords
from app.navigation.path_hints import PathHints


def classify_intent(task: str, hints: PathHints) -> str:
    text = task.casefold()
    best, best_hits = "generic", 0
    for intent, keywords in hints.intent_keywords.items():
        hits = count_keywords(text, keywords)  # с начала слова, не любой подстрокой
        if hits > best_hits:
            best, best_hits = intent, hits
    return best
