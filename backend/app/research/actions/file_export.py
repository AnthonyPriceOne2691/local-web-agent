"""export_file — Tier 0 sink: результат run'а → локальный markdown-файл.

Первый плагин реестра (doc 25): новое действие = этот модуль + описание в
data/prompts/tools/. Локальный sink не покидает машину → consent не требуется
(cloud carve-out — только про облако); файл пишется в artifacts сессии.
"""

from __future__ import annotations

from app.research.actions.base import (
    ActionContext,
    ActionSpec,
    enforce_run_id_in_session,
)
from app.research.actions.registry import register
from app.research.meta_agent import ToolCall
from app.sinks.content import build_export_content
from app.sinks.file import export_to_file


def _execute(call: ToolCall, ctx: ActionContext) -> str:
    r = ctx.run_store.get(call.args.get("run_id") or "")
    if r is None or r.result is None:
        return f"export_file: у run {call.args.get('run_id')} нет результата"
    if ctx.session_store is None:
        return "export_file: недоступно вне сессии"
    title, body = build_export_content(r.result, title_override=call.args.get("title"))
    path = export_to_file(title, body,
                          out_dir=ctx.session_store.artifacts_dir(ctx.session.id),
                          filename=call.args.get("filename"))
    return f"Сохранено в файл: {path}"


SPEC = register(ActionSpec(
    name="export_file", tier=0, reversible=True,
    enforce=enforce_run_id_in_session, execute=_execute,
    note=lambda call: f"export_file run={call.args.get('run_id')}"))
