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
    attempted: set[str] = field(default_factory=set)  # куда ходили, но страницы это не дало
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

    @property
    def seen(self) -> set[str]:
        """Куда агент уже ходил: прочитанные страницы плюс URL, которые страницы не дали.

        Два множества разведены намеренно. `visited` — то, что **прочитано**: на нём
        считается бюджет страниц (G-H1), и алиас редиректа съедал бы там чужую страницу.
        `attempted` — то, куда **ходили**: запрошенные URL, уведённые редиректом, и цели,
        до которых дойти не удалось. Не ходить второй раз надо в оба, поэтому очередь
        кандидатов и G-H3 смотрят сюда, а счётчик страниц — по-прежнему в `visited`.
        """
        return self.visited | self.attempted

    def remember(self, snapshot: PageSnapshot, requested_url: str | None = None) -> None:
        """Страница прочитана: попадает в историю прогона и становится текущей.

        `requested_url` — то, что агент просил открыть. При редиректе он отличается от
        `snapshot.url`, и без него ссылка остаётся «непосещённой»: замер журнала показал
        четыре прогона, где сайт уводил A → B, а модель раз за разом просила A снова
        (`sports.ru` — три захода на одну страницу из восьми шагов бюджета).
        """
        self.current = snapshot
        self.visited.add(snapshot.url)
        if requested_url and requested_url != snapshot.url:
            self.attempted.add(requested_url)
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
