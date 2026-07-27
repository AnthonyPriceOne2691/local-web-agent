"""GET /health (doc 15): ollama + models presence + active run."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    state = request.app.state
    ollama = await state.llm_client.health()
    required = {state.settings.nav_model, state.settings.synth_model}
    models_present = {m: any(t.startswith(m) or t == m for t in ollama["models"]) for m in required}
    return {
        "status": "ok" if ollama["reachable"] and all(models_present.values()) else "degraded",
        "ollama": "reachable" if ollama["reachable"] else "unreachable",
        "ollama_version": ollama["version"],
        "models": models_present,
        "active_run_id": state.run_store.active_run_id(),
    }
