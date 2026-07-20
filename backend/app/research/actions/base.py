"""Action Protocol (doc 25 § Action Protocol + Registry) — типы Layer 2 действий.

Каждое действие описано `ActionSpec`: метаданные тира (doc 25 § Таксономия:
автономность × обратимость), пер-action пост-валидация плана (M-H3 и родня)
и исполнение reply-block действий. Структурные действия (crawl_site,
compare_results) управляют потоком сессии — их ведёт runner, execute у них нет.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.config import Settings
from app.research.meta_agent import ToolCall
from app.schemas.research import SessionRecord
from app.storage.run_store import RunStore
from app.storage.session_store import SessionStore


@dataclass(frozen=True)
class ActionContext:
    """Контекст enforce/execute-хуков: сессия, stores, настройки.

    `session_store` есть только на исполнении (runner); `allowed_urls` — только
    на валидации плана (планнер, M-H3).
    """

    session: SessionRecord
    run_store: RunStore
    settings: Settings
    session_store: SessionStore | None = None
    allowed_urls: frozenset[str] = frozenset()


EnforceHook = Callable[[ToolCall, ActionContext], ToolCall | None]
ExecuteHook = Callable[[ToolCall, ActionContext], str]
NoteHook = Callable[[ToolCall], str]


@dataclass(frozen=True)
class ActionSpec:
    """Зарегистрированное действие Layer 2 (A-H1).

    tier (doc 25): 0 sink · 1 safe interaction · 2 confirm · 3 prepare-only.
    Runner выполняет только tier ≤ 1 (A-H2/A-H3 гейт); `cloud` — результат
    покидает машину → только по явному запросу пользователя (A-H4).
    """

    name: str
    tier: int
    reversible: bool
    cloud: bool = False
    structural: bool = False  # поток (очередь/cooldown/финал) ведёт runner
    enforce: EnforceHook | None = None  # пер-action контракт; None → без правок
    execute: ExecuteHook | None = None  # reply-block; None у structural
    note: NoteHook | None = None  # M-S1 tool-нота; None → имя действия


def enforce_run_id_in_session(call: ToolCall, ctx: ActionContext) -> ToolCall | None:
    """M-H3: run_id только из runs текущей сессии — чужой/выдуманный отброшен."""
    return call if call.args.get("run_id") in set(ctx.session.run_ids) else None
