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


class InteractiveElement(BaseModel):
    """Кликабельный/вводимый элемент страницы для action-режима (doc 25 A-1).

    `index` — устойчивый порядковый номер в document order: агент ссылается на
    элемент по номеру, а не по хрупкому селектору. Инвариант для будущего click
    (Tier 1): тот же селектор + visibility-фильтр + document order → тот же index.
    """

    index: int
    kind: str = ""  # button / text / email / password / submit / select / textarea / checkbox …
    label: str = ""
    input_type: str = ""  # для <input>: тип поля (submit/password → Tier 2, doc 25)
    name: str = ""
    disabled: bool = False


class PageSnapshot(BaseModel):
    url: str
    status: PageStatus = "ok"
    title: str = ""
    meta_description: str = ""
    headings: list[Heading] = Field(default_factory=list)
    main_text: str = ""
    links: list[Link] = Field(default_factory=list)
    interactive_elements: list[InteractiveElement] = Field(default_factory=list)  # doc 25 A-1
    screenshots: list[ScreenshotRef] = Field(default_factory=list)
    vision_insights: list[dict] = Field(default_factory=list)  # VisionInsight dumps (doc 23)
    truncated: bool = False
    priority: bool = False


class AgentAction(BaseModel):
    """LLM action schema (doc 04). Также используется как JSON Schema для
    structured outputs Ollama (doc 16)."""

    action: Literal["navigate", "extract_now", "click", "fill", "stop"]
    url: str | None = None
    element_index: int | None = None  # click/fill: индекс ∈ interactive_elements (doc 25)
    value: str = ""  # fill: текст в текстовое поле (Tier 2, doc 25)
    reasoning: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class Candidate(BaseModel):
    href: str
    text: str = ""
    score: int = 0
    reason: str = ""
