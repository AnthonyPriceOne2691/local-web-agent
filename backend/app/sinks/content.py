"""Сборка экспортируемого контента из результата run'а (DRY: gdocs- и file-sink).

Приоритет — article (найденная статья: заголовок, URL, excerpt из снапшота);
без статьи — summary + факты. Логика перенесена из Tier 0 Google Docs export.
"""

from __future__ import annotations

from app.schemas.extraction import ExtractionResult


def build_export_content(
    result: ExtractionResult,
    *,
    title_override: str | None = None,
) -> tuple[str, str]:
    """(title, body) для экспорта в любой sink."""
    art = result.article
    title = (title_override or (art.title if art else "") or f"Research: {result.start_url}")[:200]
    if art and art.main_text_excerpt:
        body = f"{art.title}\n{art.url}\n\n{art.main_text_excerpt}"
    else:
        facts = "\n".join(f"- {f.label or f.key}: {f.value}" for f in result.facts[:20])
        body = f"{result.summary}\n\n{facts}".strip()
    return title, body
