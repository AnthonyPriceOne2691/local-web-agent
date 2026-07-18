"""Runs API (doc 15): POST /runs (409 при активном — D-12), GET /runs, GET /runs/{id}."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from app.schemas.run import RunConfig, RunRecord

router = APIRouter()


@router.post("/runs", status_code=202)
async def start_run(config: RunConfig, request: Request) -> dict:
    state = request.app.state
    if state.active_run_id is not None:  # D-12: global run lock
        raise HTTPException(
            status_code=409,
            detail={"error": "run_in_progress", "active_run_id": state.active_run_id},
        )
    record = RunRecord(
        id=uuid.uuid4().hex[:12],
        config=config,
        status="running",
        started_at=datetime.now(UTC).isoformat(),
    )
    state.run_store.save(record)
    state.active_run_id = record.id

    async def _execute() -> None:
        try:
            orchestrator = state.orchestrator_factory()
            await orchestrator.run(record)
        except Exception as exc:  # noqa: BLE001 — фон не должен падать молча
            record.status = "failed"
            record.error_message = str(exc)[:500]
            state.run_store.save(record)
        finally:
            state.active_run_id = None

    state.background_tasks.add(asyncio.create_task(_execute()))
    return {"run_id": record.id, "status": "running"}


@router.get("/runs")
async def list_runs(request: Request, limit: int = 20) -> dict:
    store = request.app.state.run_store
    ids = store.list_ids()[:limit]
    runs = []
    for run_id in ids:
        r = store.get(run_id)
        if r:
            runs.append({
                "run_id": r.id, "task": r.config.task, "status": r.status,
                "pages_visited": r.pages_visited, "started_at": r.started_at,
            })
    return {"runs": runs, "total": len(store.list_ids())}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> RunRecord:
    record = request.app.state.run_store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    return record


@router.get("/runs/{run_id}/result")
async def get_result(run_id: str, request: Request) -> dict:
    record = request.app.state.run_store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    if record.result is None:
        raise HTTPException(status_code=404, detail="run not finished")
    return record.result.model_dump()
