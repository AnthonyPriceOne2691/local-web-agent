"""Research sessions API (doc 15/24): POST /sessions, messages, events SSE,
report, cancel, delete."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.sse import session_event_stream
from app.schemas.research import SessionConfig, SessionRecord

logger = logging.getLogger(__name__)
router = APIRouter()

BUSY_STATUSES = ("running_tools", "comparing")


class CreateSession(BaseModel):
    title: str = ""
    max_sites: int | None = None
    rubric: str | None = None
    attended: bool = False


class UserMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


@router.post("/sessions", status_code=201)
async def create_session(body: CreateSession, request: Request) -> dict[str, Any]:
    state = request.app.state
    config = SessionConfig(
        max_sites=body.max_sites or state.settings.max_sites_per_session,
        rubric_override=body.rubric,
        attended=body.attended,
    )
    record = SessionRecord(
        id=uuid.uuid4().hex[:12], title=body.title, config=config, created_at=datetime.now(UTC).isoformat()
    )
    state.session_store.save(record)
    return {"session_id": record.id}


@router.post("/sessions/{session_id}/messages", status_code=202)
async def post_message(session_id: str, body: UserMessage, request: Request) -> dict[str, Any]:
    state = request.app.state
    session = state.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status in BUSY_STATUSES:
        raise HTTPException(status_code=409, detail={"error": "session_busy", "status": session.status})
    active = state.run_store.active_run_id()  # D-12: один crawl глобально
    if active is not None:
        raise HTTPException(status_code=409, detail={"error": "run_in_progress", "active_run_id": active})
    cancel_event = asyncio.Event()
    state.session_cancel_events[session_id] = cancel_event
    resume_event = asyncio.Event()  # attended (Phase 5): пробрасывается в текущий crawl
    state.session_resume_events[session_id] = resume_event

    async def _execute() -> None:
        try:
            runner = state.research_runner_factory()
            await runner.run_message(
                session, body.content, cancel_event=cancel_event, resume_event=resume_event
            )
        except Exception:
            # Фоновая задача: без этого лога останется только status=failed
            # в сессии — без причины и стека.
            logger.exception("session %s failed", session_id)
            session.status = "failed"
            session.finished_at = datetime.now(UTC).isoformat()
            state.session_store.save(session)
        finally:
            state.session_cancel_events.pop(session_id, None)
            state.session_resume_events.pop(session_id, None)

    state.background_tasks.add(asyncio.create_task(_execute()))
    return {"session_id": session_id, "status": "running_tools"}


@router.get("/sessions")
async def list_sessions(request: Request, limit: int = 20) -> dict[str, Any]:
    store = request.app.state.session_store
    ids = store.list_ids()[:limit]
    sessions = []
    for sid in ids:
        s = store.get(sid)
        if s:
            sessions.append(
                {
                    "session_id": s.id,
                    "title": s.title,
                    "status": s.status,
                    "runs": len(s.run_ids),
                    "created_at": s.created_at,
                }
            )
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> SessionRecord:
    session: SessionRecord | None = request.app.state.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/sessions/{session_id}/events")
async def session_events(session_id: str, request: Request, since_messages: int = 0) -> StreamingResponse:
    """SSE-прогресс (doc 15 v0.6): status / message / crawl_progress / done.

    Poll-паттерн поверх store (Phase 4, no WebSocket); реконнект возобновляет
    с `?since_messages=N` — messages только аппендятся.
    """
    state = request.app.state
    if state.session_store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    stream = session_event_stream(
        session_id,
        sessions=state.session_store,
        runs=state.run_store,
        settings=state.settings,
        since_messages=since_messages,
    )
    return StreamingResponse(stream, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/sessions/{session_id}/report")
async def get_session_report(session_id: str, request: Request) -> Response:
    """comparison_report.md как text/markdown (экспорт из Chat UI, doc 24)."""
    state = request.app.state
    if state.session_store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    path = state.session_store.artifacts_dir(session_id) / "comparison_report.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="report not generated")
    return Response(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@router.post("/sessions/{session_id}/cancel", status_code=202)
async def cancel_session(session_id: str, request: Request) -> dict[str, Any]:
    """doc 15: текущий crawl доводится до cancel, очередь очищается."""
    state = request.app.state
    session = state.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status not in BUSY_STATUSES:
        raise HTTPException(status_code=409, detail={"error": "not_running", "status": session.status})
    event = state.session_cancel_events.get(session_id)
    if event is not None:
        event.set()
    else:  # беспроцессный zombie
        session.status = "failed"
        session.config.canceled_by_restart = True
        state.session_store.save(session)
    return {"session_id": session_id, "status": "canceling"}


@router.post("/sessions/{session_id}/resume", status_code=202)
async def resume_session(session_id: str, request: Request) -> dict[str, Any]:
    """Attended (Phase 5): пользователь прошёл challenge → снять паузу активного crawl."""
    state = request.app.state
    session = state.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    active_id = state.run_store.active_run_id()
    active = state.run_store.get(active_id) if active_id else None
    if active is None or active.session_id != session_id or active.status != "waiting_user":
        raise HTTPException(status_code=409, detail={"error": "not_waiting"})
    event = state.session_resume_events.get(session_id)
    if event is not None:
        event.set()
    return {"session_id": session_id, "status": "resuming"}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict[str, Any]:
    state = request.app.state
    session = state.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status in BUSY_STATUSES:
        raise HTTPException(status_code=409, detail="session is active — cancel it first")
    state.session_store.delete(session_id)
    return {"deleted": session_id}
