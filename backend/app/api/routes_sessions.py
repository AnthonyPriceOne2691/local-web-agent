"""Research sessions API (doc 15/24): POST /sessions, messages, cancel, delete."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.schemas.research import SessionConfig, SessionRecord

router = APIRouter()

BUSY_STATUSES = ("running_tools", "comparing")


class CreateSession(BaseModel):
    title: str = ""
    max_sites: int | None = None
    rubric: str | None = None


class UserMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


@router.post("/sessions", status_code=201)
async def create_session(body: CreateSession, request: Request) -> dict:
    state = request.app.state
    config = SessionConfig(
        max_sites=body.max_sites or state.settings.max_sites_per_session,
        rubric_override=body.rubric,
    )
    record = SessionRecord(id=uuid.uuid4().hex[:12], title=body.title, config=config,
                           created_at=datetime.now(UTC).isoformat())
    state.session_store.save(record)
    return {"session_id": record.id}


@router.post("/sessions/{session_id}/messages", status_code=202)
async def post_message(session_id: str, body: UserMessage, request: Request) -> dict:
    state = request.app.state
    session = state.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status in BUSY_STATUSES:
        raise HTTPException(status_code=409, detail={"error": "session_busy",
                                                     "status": session.status})
    active = state.run_store.active_run_id()  # D-12: один crawl глобально
    if active is not None:
        raise HTTPException(status_code=409,
                            detail={"error": "run_in_progress", "active_run_id": active})
    cancel_event = asyncio.Event()
    state.session_cancel_events[session_id] = cancel_event

    async def _execute() -> None:
        try:
            runner = state.research_runner_factory()
            await runner.run_message(session, body.content, cancel_event=cancel_event)
        except Exception as exc:  # noqa: BLE001 — сессия не должна виснуть в running_tools
            session.status = "failed"
            session.finished_at = datetime.now(UTC).isoformat()
            state.session_store.save(session)
            print(f"session {session_id} failed: {exc}")
        finally:
            state.session_cancel_events.pop(session_id, None)

    state.background_tasks.add(asyncio.create_task(_execute()))
    return {"session_id": session_id, "status": "running_tools"}


@router.get("/sessions")
async def list_sessions(request: Request, limit: int = 20) -> dict:
    store = request.app.state.session_store
    ids = store.list_ids()[:limit]
    sessions = []
    for sid in ids:
        s = store.get(sid)
        if s:
            sessions.append({"session_id": s.id, "title": s.title, "status": s.status,
                             "runs": len(s.run_ids), "created_at": s.created_at})
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> SessionRecord:
    session = request.app.state.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.post("/sessions/{session_id}/cancel", status_code=202)
async def cancel_session(session_id: str, request: Request) -> dict:
    """doc 15: текущий crawl доводится до cancel, очередь очищается."""
    state = request.app.state
    session = state.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status not in BUSY_STATUSES:
        raise HTTPException(status_code=409, detail={"error": "not_running",
                                                     "status": session.status})
    event = state.session_cancel_events.get(session_id)
    if event is not None:
        event.set()
    else:  # беспроцессный zombie
        session.status = "failed"
        session.config.canceled_by_restart = True
        state.session_store.save(session)
    return {"session_id": session_id, "status": "canceling"}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    state = request.app.state
    session = state.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status in BUSY_STATUSES:
        raise HTTPException(status_code=409, detail="session is active — cancel it first")
    state.session_store.delete(session_id)
    return {"deleted": session_id}
