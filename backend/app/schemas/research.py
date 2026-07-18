"""Research-session схемы Phase 3 (docs 05/24): ComparisonResult, session, messages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SessionStatus = Literal["active", "running_tools", "comparing", "completed", "failed"]
ResearchIntent = Literal[
    "comparative_design", "comparative_content", "multi_site_research", "single_site"
]


class ExcludedSite(BaseModel):
    start_url: str
    reason: str = ""


class Winner(BaseModel):
    run_id: str = ""
    start_url: str = ""
    label: str = ""
    reason: str = ""


class Ranking(BaseModel):
    run_id: str = ""
    url: str = ""
    score: int = 0
    summary: str = ""


class Dimension(BaseModel):
    name: str
    scores: dict[str, int | float | str] = Field(default_factory=dict)


class ComparisonResult(BaseModel):
    schema_version: int = 1
    session_id: str = ""
    comparison_task: str = ""
    rubric: str = "generic_merge"
    status: Literal["completed", "partial", "failed"] = "completed"
    excluded: list[ExcludedSite] = Field(default_factory=list)
    winner: Winner | None = None  # design_diff: optional (doc 05)
    rankings: list[Ranking] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)
    narrative: str = ""
    generated_at: str = ""


class SessionMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = ""
    tool_calls: list[dict] = Field(default_factory=list)
    created_at: str = ""


class SessionConfig(BaseModel):
    max_sites: int = 10  # M-H2 (doc 24)
    rubric_override: str | None = None
    canceled_by_restart: bool = False


class SessionRecord(BaseModel):
    id: str
    title: str = ""
    status: SessionStatus = "active"
    research_intent: ResearchIntent | None = None
    config: SessionConfig = Field(default_factory=SessionConfig)
    messages: list[SessionMessage] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    comparison_result: ComparisonResult | None = None
    created_at: str = ""
    finished_at: str | None = None
