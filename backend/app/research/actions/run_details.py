"""get_run_result — детали завершённого run'а в ответ чата (reply-block)."""

from __future__ import annotations

from app.research.actions.base import (
    ActionContext,
    ActionSpec,
    enforce_run_id_in_session,
)
from app.research.actions.registry import register
from app.research.meta_agent import ToolCall


def _execute(call: ToolCall, ctx: ActionContext) -> str:
    run_id = call.args.get("run_id") or ""
    r = ctx.run_store.get(run_id)
    if r is None or r.result is None:
        return f"{run_id}: no result available"
    lines = [f"{r.config.start_url} ({r.status}): {r.result.summary}"]
    lines += [f"- {f.label or f.key}: {f.value}" for f in r.result.facts[:5]]
    if r.result.article:
        lines.append(f"- article: {r.result.article.title} ({r.result.article.word_count} words)")
    return "\n".join(lines)


SPEC = register(
    ActionSpec(
        name="get_run_result",
        tier=0,
        reversible=True,
        enforce=enforce_run_id_in_session,
        execute=_execute,
        note=lambda call: f"get_run_result {call.args.get('run_id')}",
    )
)
