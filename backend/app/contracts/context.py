"""ActionContext — всё, что нужно checks для валидации одного действия (doc 13).

Собирается оркестратором на каждый PLAN-шаг; чистые данные, без I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class RobotsLike(Protocol):
    def allowed(self, url: str) -> bool: ...


@dataclass
class ActionContext:
    origin: str
    start_url: str
    current_url: str
    intent: str = "generic"
    candidates: set[str] = field(default_factory=set)  # normalized hrefs (queue ∪ probes ∪ sitemap)
    visited: set[str] = field(default_factory=set)
    hops: dict[str, int] = field(default_factory=dict)
    max_pages: int = 10
    max_depth: int = 2
    pages_visited: int = 0
    robots: RobotsLike | None = None
    forbidden_paths: tuple[str, ...] = ()
    allow_private: bool = False
    interactive_elements: list = field(default_factory=list)  # InteractiveElement (I-H10, doc 25)
    attended: bool = False  # Tier 2 (doc 25): submit разрешён под подтверждением человека


def build_action_context(record, current, candidates, visited, hops, origin, robots) -> ActionContext:
    """ActionContext из состояния оркестратора (вынесено из loop.py ради ≤500 LOC, doc 18)."""
    from app.observer.links import normalize_url

    cfg = record.config
    return ActionContext(
        origin=origin,
        start_url=cfg.start_url,
        current_url=current.url,
        intent=record.intent,
        candidates={normalize_url(c.href) for c in candidates},
        visited=visited,
        hops=hops,
        max_pages=cfg.max_pages,
        max_depth=cfg.max_depth,
        pages_visited=len(visited),
        robots=robots,
        allow_private=cfg.allow_private,
        interactive_elements=current.interactive_elements,
        attended=cfg.attended,
    )
