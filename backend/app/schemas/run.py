"""Run config / record / steps (docs 04/12 — Phase 1 flat-JSON вариант)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.extraction import ExtractionResult, RunStatus


class RunConfig(BaseModel):
    start_url: str
    task: str = Field(min_length=1, max_length=2000)  # contract P-2
    max_pages: int = Field(default=10, ge=1, le=50)
    max_depth: int = Field(default=2, ge=0, le=10)  # hop depth (D-13)
    rate_limit_ms: int = Field(default=1000, ge=0)
    respect_robots: bool = True
    capture_screenshots: Literal["auto", "always", "never"] = "auto"
    use_sitemap: Literal["auto", "always", "never"] = "auto"  # P2.5 (doc 21)


class Violation(BaseModel):
    constraint_id: str
    message: str = ""
    proposed_url: str | None = None
    recovered: bool = True
    severity: Literal["hard", "soft"] = "hard"


class CrawlStep(BaseModel):
    index: int
    state: str
    url: str = ""
    action: str = ""
    target_url: str | None = None
    reasoning: str = ""
    note: str = ""
    violations: list[Violation] = Field(default_factory=list)
    duration_ms: int = 0
    screenshot_paths: dict[str, str] = Field(default_factory=dict)
    llm_stats: dict = Field(default_factory=dict)


class RunRecord(BaseModel):
    id: str
    config: RunConfig
    status: RunStatus = "running"
    intent: str = "generic"
    pages_visited: int = 0
    current_url: str = ""
    steps: list[CrawlStep] = Field(default_factory=list)
    result: ExtractionResult | None = None
    error_message: str = ""
    metadata: dict = Field(default_factory=dict)
    started_at: str = ""
    finished_at: str | None = None
