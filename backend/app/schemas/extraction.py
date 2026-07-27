"""ExtractionResult (doc 05, schema_version 1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["high", "medium", "low"]
RunStatus = Literal[
    "running", "waiting_user", "completed", "partial", "not_found", "blocked", "failed", "canceled"
]  # waiting_user: attended-пауза (Phase 5)


class Evidence(BaseModel):
    url: str
    quote: str = ""
    source: Literal["dom", "vision", "both"] = "dom"
    screenshot_path: str | None = None


class Fact(BaseModel):
    key: str
    label: str = ""
    value: str
    confidence: Confidence = "medium"
    evidence: list[Evidence] = Field(default_factory=list)


class NotFound(BaseModel):
    key: str
    reason: str = ""


class Article(BaseModel):
    """Лучшая статья-кандидат (Phase 3 UC-2, doc 05 § article)."""

    url: str
    title: str = ""
    word_count: int = 0
    headings: list[str] = Field(default_factory=list)
    main_text_excerpt: str = ""  # до 12000 chars для compare (doc 20)
    published_date: str | None = None
    page_type_confidence: Confidence = "medium"

    @field_validator("word_count", mode="before")
    @classmethod
    def _coerce_word_count(cls, v):  # LLM пишет "≈2400"/"about 950" — вытащить цифры
        if isinstance(v, str):
            digits = "".join(ch for ch in v if ch.isdigit())
            return int(digits) if digits else 0
        return v or 0


class ArticleCandidate(BaseModel):
    url: str
    rejected_reason: str = ""


class ExtractionResult(BaseModel):
    schema_version: int = 1
    run_id: str = ""
    task: str = ""
    start_url: str = ""
    status: RunStatus = "completed"
    summary: str = ""
    facts: list[Fact] = Field(default_factory=list)
    not_found: list[NotFound] = Field(default_factory=list)
    article: Article | None = None  # UC-2 content_search (doc 05)
    article_candidates_considered: list[ArticleCandidate] = Field(default_factory=list)
    design_tokens: dict = Field(default_factory=dict)  # из vision_insights[].design (doc 05)
    pages_visited: int = 0
    duration_seconds: float = 0.0
    generated_at: str = ""
