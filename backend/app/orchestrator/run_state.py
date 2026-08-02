"""Состояние одного прогона и исход шага — общий словарь стадий OBSERVE/PLAN/ACT.

Зачем отдельный объект. `run()` тащила через весь цикл дюжину переменных
(`visited`, `hops`, `snapshots`, `homepage`, `current`, `next_url`, счётчики
залипания и ранней остановки). Разбор на шаги без общего состояния превратил бы их
в функции с десятком параметров — то есть в ту же сложность, только размазанную.

Зачем `StepOutcome`. Внутри цикла двенадцать `break` и шесть `continue`; если
вынести шаги «как есть», управление потеряется. Шаг возвращает решение, а цикл
остаётся плоским: `CONTINUE` — следующая итерация, `PROCEED` — дальше по той же,
`STOP` — выход из цикла.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.schemas.snapshot import PageSnapshot


class StepOutcome(Enum):
    CONTINUE = "continue"
    PROCEED = "proceed"
    STOP = "stop"


@dataclass
class RunState:
    """Изменяемое состояние прогона. Живёт ровно один `run()`."""

    origin: str
    next_url: str | None
    visited: set[str] = field(default_factory=set)
    hops: dict[str, int] = field(default_factory=dict)
    snapshots: list[PageSnapshot] = field(default_factory=list)
    homepage: PageSnapshot | None = None
    current: PageSnapshot | None = None
    step_index: int = 0
    extract_streak: int = 0
    stale_pages: int = 0  # G-S1 early stop
    repeats: dict[tuple[Any, ...], int] = field(default_factory=dict)  # анти-залипание
    seen_relevant: set[str] = field(default_factory=set)
    just_visited: bool = False
    violations_total: int = 0
    canceled: bool = False

    def remember(self, snapshot: PageSnapshot) -> None:
        """Страница прочитана: попадает в историю прогона и становится текущей."""
        self.current = snapshot
        self.visited.add(snapshot.url)
        self.snapshots.append(snapshot)
        self.homepage = self.homepage or snapshot
        self.just_visited = True

    def adopt(self, snapshot: PageSnapshot) -> None:
        """Страница переснята на месте (после attended-паузы или интеракции):
        новой посещённой страницы нет, но текущая изменилась."""
        self.current = snapshot
        self.homepage = self.homepage or snapshot
        self.just_visited = True


@dataclass(frozen=True)
class Prepared:
    """Что известно о сайте до первого шага: robots, темп, пробы, sitemap."""

    robots: Any  # RobotsPolicy — импорт сюда затянул бы orchestrator в схемы
    rate_ms: int
    alive_probes: list[str]
    legal_probes: list[str]
    probe_links: list[dict[str, str]]
    sitemap_candidates: list[str]
