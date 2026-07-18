"""API (POST /runs 202→409 D-12, GET status, startup sweep) + JsonRunStore roundtrip."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.schemas.run import RunConfig, RunRecord
from app.storage.run_store import JsonRunStore
from tests.conftest import REPO_ROOT


def test_store_roundtrip_and_sweep(tmp_path):
    store = JsonRunStore(tmp_path / "runs")
    rec = RunRecord(id="r1", config=RunConfig(start_url="https://x.com", task="t"), status="running")
    store.save(rec)
    loaded = store.get("r1")
    assert loaded and loaded.config.task == "t"
    assert store.list_ids() == ["r1"]
    assert store.artifacts_dir("r1").is_dir()
    # sweep: running → failed (orphaned)
    assert store.startup_sweep() == 1
    assert store.get("r1").status == "failed"
    assert "orphaned" in store.get("r1").error_message


class InstantOrchestrator:
    """Стаб: мгновенно завершает run — для API-тестов без браузера/LLM."""

    def __init__(self, store):
        self._store = store

    async def run(self, record: RunRecord) -> RunRecord:
        await asyncio.sleep(0.05)
        record.status = "completed"
        record.pages_visited = 1
        self._store.save(record)
        return record


@pytest.fixture()
async def api_client(tmp_path, monkeypatch):
    settings = Settings(data_dir=REPO_ROOT / "data")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        # подменяем на изолированный store + мгновенный оркестратор (DI через app.state)
        app.state.run_store = JsonRunStore(tmp_path / "runs")
        app.state.orchestrator_factory = lambda: InstantOrchestrator(app.state.run_store)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def test_post_run_and_poll(api_client):
    client, app = api_client
    r = await client.post("/runs", json={"start_url": "https://example.com", "task": "find x"})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    for _ in range(50):
        record = (await client.get(f"/runs/{run_id}")).json()
        if record["status"] != "running":
            break
        await asyncio.sleep(0.02)
    assert record["status"] == "completed"
    listing = (await client.get("/runs")).json()
    assert listing["total"] == 1


async def test_second_run_409_while_active(api_client):
    client, app = api_client

    class SlowOrchestrator(InstantOrchestrator):
        async def run(self, record):
            await asyncio.sleep(0.5)
            return await super().run(record)

    app.state.orchestrator_factory = lambda: SlowOrchestrator(app.state.run_store)
    r1 = await client.post("/runs", json={"start_url": "https://example.com", "task": "first"})
    assert r1.status_code == 202
    r2 = await client.post("/runs", json={"start_url": "https://example.com", "task": "second"})
    assert r2.status_code == 409  # D-12 global run lock
    assert r2.json()["detail"]["error"] == "run_in_progress"


async def test_get_unknown_run_404(api_client):
    client, _ = api_client
    assert (await client.get("/runs/nope")).status_code == 404
    assert (await client.get("/runs/nope/result")).status_code == 404


async def test_health_shape(api_client):
    client, _ = api_client
    data = (await client.get("/health")).json()
    assert {"status", "ollama", "models", "active_run_id"} <= set(data)
