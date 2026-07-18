"""ExtractionResult (doc 05, schema_version 1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]
RunStatus = Literal["running", "completed", "partial", "not_found", "blocked", "failed", "canceled"]


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


class ExtractionResult(BaseModel):
    schema_version: int = 1
    run_id: str = ""
    task: str = ""
    start_url: str = ""
    status: RunStatus = "completed"
    summary: str = ""
    facts: list[Fact] = Field(default_factory=list)
    not_found: list[NotFound] = Field(default_factory=list)
    pages_visited: int = 0
    duration_seconds: float = 0.0
    generated_at: str = ""
