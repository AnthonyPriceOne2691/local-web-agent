"""VisionInsight (doc 23) — результат одного VLM-вызова; в SYNTHESIZE идёт текстом."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VisionStatus = Literal["ok", "skipped", "failed", "degraded"]
ScreenStatus = Literal["ok", "blank", "obstructed", "error_page", "unknown"]


class VisionExtracted(BaseModel):
    key: str
    value: str
    confidence: Literal["high", "medium", "low"] = "medium"


class VisionInsight(BaseModel):
    profile: Literal["desktop", "tablet", "mobile"] = "desktop"
    url: str = ""
    status: VisionStatus = "ok"
    screen_status: ScreenStatus = "unknown"
    description: str = ""
    extracted: list[VisionExtracted] = Field(default_factory=list)
    design: dict = Field(default_factory=dict)
    text_not_in_dom: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    error: str | None = None
