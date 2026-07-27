"""compare_results — структурное действие: синтез сравнения по runs сессии.

Terminal-стадия сессии (comparison + report) — ведёт runner (structural).
Контракт плана: run_ids только из сессии (M-H3), неизвестная рубрика → дефолт.
Кросс-плановое правило «максимум один, последним» остаётся в планнере.
"""

from __future__ import annotations

from app.research.actions.base import ActionContext, ActionSpec
from app.research.actions.registry import register
from app.research.meta_agent import RUBRIC_BY_INTENT, ToolCall

KNOWN_RUBRICS = tuple(RUBRIC_BY_INTENT.values())


def _enforce(call: ToolCall, ctx: ActionContext) -> ToolCall | None:
    run_ids = set(ctx.session.run_ids)
    call.args["run_ids"] = [r for r in call.args.get("run_ids") or [] if r in run_ids]
    if call.args.get("rubric") not in KNOWN_RUBRICS:
        call.args["rubric"] = "generic_merge"
    return call


SPEC = register(
    ActionSpec(name="compare_results", tier=0, reversible=True, structural=True, enforce=_enforce)
)
