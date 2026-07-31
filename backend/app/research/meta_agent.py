"""Meta-agent Phase 3 — rules-first planner (doc 24 § Planner).

План детерминирован: URLs (regex) → research intent (keywords) → N × crawl_site →
compare_results. LLM в планировании не участвует (Phase 4 — llm-planner для чата).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.navigation.matching import any_keyword
from app.schemas.research import ResearchIntent

URL_RE = re.compile(r"https?://[^\s,;\"'<>()\[\]]+", re.IGNORECASE)

# триггеры research intent (doc 24 § Research intents; RU+EN стемы)
DESIGN_KEYWORDS = (
    "design",
    "layout",
    "colors",
    "typography",
    "look and feel",
    "ui",
    "дизайн",
    "вёрстк",
    "верстк",
    "макет",
    "цвет",
    "шрифт",
    "выгляд",
    "отлича",
)
CONTENT_KEYWORDS = (
    "article",
    "blog",
    "статья",
    "статью",
    "статьи",
    "текст",
    "контент",
    "полнее",
    "полнот",
    "конкурент",
    "guide",
    "гайд",
    "post",
)

# per-site crawl defaults по intent (doc 21 § intents matrix, doc 24 § UC)
CRAWL_DEFAULTS: dict[str, dict[str, Any]] = {
    "comparative_design": {
        "intent": "design_audit",
        "max_pages": 6,  # UC-1: 20-мин бюджет (doc 24)
        "capture_screenshots": "always",
        "vision_enabled": "always",
    },
    "comparative_content": {
        "intent": "content_search",
        "max_pages": 12,  # UC-2 (doc 21)
        "capture_screenshots": "never",
        "vision_enabled": "never",
    },
    "multi_site_research": {"intent": None, "max_pages": 10},
    "single_site": {"intent": None, "max_pages": 10},
}

RUBRIC_BY_INTENT = {
    "comparative_design": "design_diff",
    "comparative_content": "content_completeness",
    "multi_site_research": "generic_merge",
}


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


def parse_urls(message: str, *, max_sites: int | None = 10) -> list[str]:
    """FR-6.1: URL-ы из сообщения; dedupe с сохранением порядка; cap M-H2.

    max_sites=None → без cap (вызывающий сам решает, что делать с избытком — runner
    предупреждает пользователя, а не глотает лишние URL молча).
    """
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_RE.findall(message):
        url = match.rstrip(".,;:!?")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls if max_sites is None else urls[:max_sites]


def classify_research_intent(message: str, n_urls: int) -> ResearchIntent:
    if n_urls <= 1:
        return "single_site"
    text = message.casefold()
    # Совпадение с НАЧАЛА слова: короткое `ui` иначе ловится внутри `guide` и
    # `build`, и контентная задача уезжала в рубрику дизайна (real-site прогон).
    if any_keyword(text, DESIGN_KEYWORDS):
        return "comparative_design"
    if any_keyword(text, CONTENT_KEYWORDS):
        return "comparative_content"
    return "multi_site_research"


def build_plan(intent: ResearchIntent, urls: list[str], task: str) -> list[ToolCall]:
    """Детерминированный план: N × crawl_site (sequential, D-7) → compare (если >1)."""
    defaults = {k: v for k, v in CRAWL_DEFAULTS[intent].items() if v is not None}
    plan = [ToolCall(name="crawl_site", args={"url": url, "task": task, **defaults}) for url in urls]
    if len(urls) >= 2:
        plan.append(
            ToolCall(
                name="compare_results", args={"comparison_task": task, "rubric": RUBRIC_BY_INTENT[intent]}
            )
        )
    return plan


def strip_urls(message: str) -> str:
    """Sub-task для crawl_site: сообщение без URL-перечисления."""
    text = URL_RE.sub("", message)
    return re.sub(r"[ \t]{2,}", " ", text).strip(" ,;:—-\n")
