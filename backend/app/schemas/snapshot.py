"""PageSnapshot + AgentAction (docs 03/04)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PageStatus = Literal["ok", "login_wall", "captcha", "error", "spa_loading"]


class Heading(BaseModel):
    level: int
    text: str


class Link(BaseModel):
    href: str
    text: str = ""
    same_site: bool = True


ViewportProfile = Literal["desktop", "tablet", "mobile"]


class ScreenshotRef(BaseModel):
    profile: ViewportProfile
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
    value: str = ""  # текущее содержимое поля (password не собирается никогда)

    def label_matches(self, signals: tuple[str, ...]) -> bool:
        """Совпадает ли label с одним из сигналов (casefold substring).

        Живёт на модели, а не в contracts: пометку нужно знать и enforcer'у
        (I-H12), и промпту навигатора, а `app.llm` импортировать `app.contracts`
        не может — import-linter ловит обратное направление слоёв.
        """
        label = (self.label or "").casefold()
        return bool(label) and any(s in label for s in signals)

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
    vision_insights: list[dict[str, Any]] = Field(default_factory=list)  # VisionInsight dumps (doc 23)
    truncated: bool = False
    priority: bool = False


class FillField(BaseModel):
    """Одно поле формы для `fill_form` (Tier 2, doc 25)."""

    element_index: int
    value: str = ""


class AgentAction(BaseModel):
    """LLM action schema (doc 04). Также используется как JSON Schema для
    structured outputs Ollama (doc 16)."""

    action: Literal["navigate", "extract_now", "click", "fill", "fill_form", "stop"]
    url: str | None = None
    element_index: int | None = None  # click/fill: индекс ∈ interactive_elements (doc 25)
    value: str = ""  # fill: текст в текстовое поле (Tier 2, doc 25)
    # fill_form: вся форма за ОДНО решение LLM. Пополевой fill стоил вызова модели
    # на каждое поле (живой прогон: 7.5 + 3.8 + 3.6 s на три поля).
    fields: list[FillField] = Field(default_factory=list)
    reasoning: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class Candidate(BaseModel):
    href: str
    text: str = ""
    score: int = 0
    reason: str = ""
