"""Link scoring (doc 21 формула; doc 04 fallback)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.navigation.path_hints import PathHints

FORBIDDEN_SUBSTR = ("/login", "/signin", "/signup", "/register", "/cart", "/checkout", "/wp-admin")
LEGAL_SUBSTR = ("/privacy", "/terms", "/cookie", "/legal")


def score_link(
    link: dict[str, Any], *, intent: str, task: str, hints: PathHints, on_homepage: bool
) -> tuple[int, str]:
    href = link["href"].casefold()
    text = (link.get("text") or "").casefold()
    score, reasons = 0, []
    keywords = [k.casefold() for k in hints.intent_keywords.get(intent, [])]
    slugs = [s.casefold() for s in hints.slugs_for(intent)]

    if on_homepage and any(k in text or k in href for k in keywords):
        score += 15
        reasons.append("homepage+intent")
    if any(s in href for s in slugs):
        score += 12
        reasons.append("slug")
    if any(w in text for w in task.casefold().split() if len(w) > 3):
        score += 10
        reasons.append("task-kw")
    if intent == "contact" and any(s.casefold() in href for s in hints.legal_slugs):
        score += 8
        reasons.append("legal-contact")
    if urlparse(link["href"]).path.rstrip("/").count("/") <= 1:
        score += 3
        reasons.append("shallow")
    if any(s in href for s in LEGAL_SUBSTR) and intent != "contact":
        score -= 8
        reasons.append("legal-avoid")
    if any(s in href for s in FORBIDDEN_SUBSTR):
        score -= 10
        reasons.append("forbidden")
    return score, "+".join(reasons) or "plain"
