"""Task → intent: casefold substring по двуязычному словарю RU+EN (doc 21)."""

from __future__ import annotations

from app.navigation.path_hints import PathHints


def classify_intent(task: str, hints: PathHints) -> str:
    text = task.casefold()
    best, best_hits = "generic", 0
    for intent, keywords in hints.intent_keywords.items():
        hits = sum(1 for kw in keywords if kw.casefold() in text)
        if hits > best_hits:
            best, best_hits = intent, hits
    return best
