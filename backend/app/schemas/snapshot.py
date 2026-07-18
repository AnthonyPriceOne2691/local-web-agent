"""PageSnapshot + AgentAction (docs 03/04)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PageStatus = Literal["ok", "login_wall", "captcha", "error", "spa_loading"]


class Heading(BaseModel):
    level: int
    text: str


class Link(BaseModel):
    href: str
    text: str = ""
    same_site: bool = True


class ScreenshotRef(BaseModel):
    profile: Literal["desktop", "tablet", "mobile"]
    relative_path: str
    width: int
    height: int


class PageSnapshot(BaseModel):
    url: str
    status: PageStatus = "ok"
    title: str = ""
    meta_description: str = ""
    headings: list[Heading] = Field(default_factory=list)
    main_text: str = ""
    links: list[Link] = Field(default_factory=list)
    screenshots: list[ScreenshotRef] = Field(default_factory=list)
    truncated: bool = False
    priority: bool = False


class AgentAction(BaseModel):
    """LLM action schema (doc 04). Также используется как JSON Schema для
    structured outputs Ollama (doc 16)."""

    action: Literal["navigate", "extract_now", "stop"]
    url: str | None = None
    reasoning: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class Candidate(BaseModel):
    href: str
    text: str = ""
    score: int = 0
    reason: str = ""
