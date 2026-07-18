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
