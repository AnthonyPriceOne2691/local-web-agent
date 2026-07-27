"""export_gdocs — Tier 0 sink: результат run'а → новый Google Doc (облако).

Consent (A-H4) — явный запрос пользователя («скопируй в Google Docs»);
планнер обучен не звать без запроса, облачность помечается tool-нотой (M-S1).
Недоступность google-либ/кредов/сети не роняет сессию — сообщаем в чат.
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


def _execute(call: ToolCall, ctx: ActionContext) -> str:
    r = ctx.run_store.get(call.args.get("run_id") or "")
    if r is None or r.result is None:
        return f"export_gdocs: у run {call.args.get('run_id')} нет результата"
    title, body = build_export_content(r.result, title_override=call.args.get("title"))
    try:
        from app.sinks.gdocs import export_to_doc  # ленивый: optional extra `gdocs`

        url = export_to_doc(title, body,
                            credentials_path=ctx.settings.gdocs_credentials,
                            token_path=ctx.settings.gdocs_token)
        return f"Экспортировано в Google Docs (облако): {url}"
    except Exception as exc:
        return f"Google Docs недоступен ({type(exc).__name__}): {str(exc)[:200]}"


SPEC = register(ActionSpec(
    name="export_gdocs", tier=0, reversible=True, cloud=True,
    enforce=enforce_run_id_in_session, execute=_execute,
    note=lambda call: f"export_gdocs run={call.args.get('run_id')} → Google Docs (облако)"))
