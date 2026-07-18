"""SSE-поток прогресса research-сессии (doc 15 v0.6, doc 24 § Chat UI, Phase 4).

Poll-паттерн (exit-критерий doc 06: no WebSocket): генератор диффит session
store и run store с шагом `sse_poll_interval_s` и отдаёт только новое.
События: `status` (смена статуса сессии; `comparing` == старт compare),
`message` (новые SessionMessage: tool-notes M-S1, ответ ассистента),
`crawl_progress` (активный run сессии: pages_visited / current_url),
`done` (терминальный статус — поток закрывается). Комментарий `: ping`
раз в `sse_heartbeat_s` держит соединение открытым в паузах.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from app.config import Settings
from app.storage.run_store import RunStore
from app.storage.session_store import SessionStore

TERMINAL_SESSION_STATUSES = ("completed", "failed")
_PROGRESS_FIELDS = ("run_id", "status", "start_url", "pages_visited", "max_pages", "current_url")


def format_sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _active_run_progress(session_id: str, runs: RunStore) -> tuple | None:
    """Прогресс активного crawl этой сессии (orchestrator чекпоинтит каждый шаг)."""
    active_id = runs.active_run_id()
    if active_id is None:
        return None
    record = runs.get(active_id)
    if record is None or record.session_id != session_id:
        return None
    return (record.id, record.status, record.config.start_url,
            record.pages_visited, record.config.max_pages, record.current_url)


async def session_event_stream(
    session_id: str,
    *,
    sessions: SessionStore,
    runs: RunStore,
    settings: Settings,
    since_messages: int = 0,
) -> AsyncIterator[str]:
    """Бесконечный дифф-цикл до терминального статуса; реконнект — `?since_messages=N`."""
    seen_messages = max(0, since_messages)
    last_status: str | None = None
    last_progress: tuple | None = None
    idle_s = 0.0
    while True:
        session = sessions.get(session_id)
        if session is None:  # удалена во время стрима
            yield format_sse("done", {"session_id": session_id, "status": "deleted"})
            return
        if session.status != last_status:
            last_status = session.status
            idle_s = 0.0
            yield format_sse("status", {"session_id": session_id, "status": session.status})
        for i in range(seen_messages, len(session.messages)):
            msg = session.messages[i]
            idle_s = 0.0
            yield format_sse("message", {"index": i, "role": msg.role,
                                         "content": msg.content, "created_at": msg.created_at})
        seen_messages = len(session.messages)
        progress = _active_run_progress(session_id, runs)
        if progress is not None and progress != last_progress:
            last_progress = progress
            idle_s = 0.0
            yield format_sse("crawl_progress", dict(zip(_PROGRESS_FIELDS, progress, strict=True)))
        if session.status in TERMINAL_SESSION_STATUSES:
            yield format_sse("done", {"session_id": session_id, "status": session.status})
            return
        await asyncio.sleep(settings.sse_poll_interval_s)
        idle_s += settings.sse_poll_interval_s
        if idle_s >= settings.sse_heartbeat_s:
            idle_s = 0.0
            yield ": ping\n\n"
