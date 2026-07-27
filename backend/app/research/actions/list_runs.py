"""list_session_runs — список runs текущей сессии в ответ чата (reply-block)."""

from __future__ import annotations

from app.research.actions.base import ActionContext, ActionSpec
from app.research.actions.registry import register
from app.research.meta_agent import ToolCall


def _execute(call: ToolCall, ctx: ActionContext) -> str:
    lines = []
    for run_id in ctx.session.run_ids:
        r = ctx.run_store.get(run_id)
        if r is not None:
            lines.append(f"- {r.id}: {r.config.start_url} — {r.status} ({r.pages_visited} pages, {r.intent})")
    return "Runs:\n" + "\n".join(lines) if lines else "No runs in this session yet."


SPEC = register(ActionSpec(name="list_session_runs", tier=0, reversible=True, execute=_execute))
