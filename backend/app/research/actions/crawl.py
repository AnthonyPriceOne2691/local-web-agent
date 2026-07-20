"""crawl_site — структурное действие: обход одного сайта (Layer 1 run).

Tier 1: чтение сайта; интеракции внутри обхода гейтят I-H10/I-H11 (doc 13).
Поток — очередь, cooldown, time-budget — ведёт runner (structural); реестр
даёт контракт плана: URL строго из ALLOWED URLS (M-H3) + clamp max_pages.
"""

from __future__ import annotations

from app.research.actions.base import ActionContext, ActionSpec
from app.research.actions.registry import register
from app.research.meta_agent import ToolCall

MAX_PAGES_CAP = 12  # планнер не раздувает обход (doc 24 § Planner)


def _enforce(call: ToolCall, ctx: ActionContext) -> ToolCall | None:
    if call.args.get("url") not in ctx.allowed_urls:  # M-H3: URL не выдумывается
        return None
    call.args["max_pages"] = min(
        int(call.args.get("max_pages") or ctx.settings.max_pages), MAX_PAGES_CAP)
    return call


SPEC = register(ActionSpec(
    name="crawl_site", tier=1, reversible=True, structural=True, enforce=_enforce))
