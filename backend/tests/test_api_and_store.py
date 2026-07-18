"""API (POST /runs 202→409 D-12, GET status, startup sweep) + SqliteRunStore roundtrip."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.schemas.extraction import ExtractionResult
from app.schemas.run import CrawlStep, RunConfig, RunRecord, Violation
from app.storage.sqlite_store import SqliteRunStore
from tests.conftest import REPO_ROOT


def _record(run_id: str = "r1", status: str = "running") -> RunRecord:
    return RunRecord(id=run_id, config=RunConfig(start_url="https://x.com", task="t"), status=status)


def test_store_roundtrip_and_sweep(tmp_path):
    store = SqliteRunStore(tmp_path / "runs")
    rec = _record()
    rec.steps.append(CrawlStep(index=1, state="OBSERVE", url="https://x.com", duration_ms=42,
                               screenshot_paths={"desktop": "screenshots/001.png"}))
    rec.steps.append(CrawlStep(index=1, state="ACT", action="navigate", target_url="https://x.com/a",
                               violations=[Violation(constraint_id="I-H6", message="not in queue")],
                               llm_stats={"eval_count": 7}))
    store.save(rec)
    loaded = store.get("r1")
    assert loaded and loaded.config.task == "t"
    assert len(loaded.steps) == 2  # одинаковый step_index (OBSERVE+ACT) не схлопывается
    assert loaded.steps[0].screenshot_paths == {"desktop": "screenshots/001.png"}
    assert loaded.steps[1].violations[0].constraint_id == "I-H6"
    assert loaded.steps[1].llm_stats == {"eval_count": 7}
    assert store.list_ids() == ["r1"]
    assert store.artifacts_dir("r1").is_dir()
    assert store.active_run_id() == "r1"  # D-12: lock из БД
    # sweep: running → failed (orphaned)
    assert store.startup_sweep() == 1
    assert store.get("r1").status == "failed"
    assert "orphaned" in store.get("r1").error_message
    assert store.active_run_id() is None


def test_store_result_artifact_and_delete(tmp_path):
    store = SqliteRunStore(tmp_path / "runs")
    rec = _record()
    rec.status = "completed"
    rec.result = ExtractionResult(status="completed", summary="ok")
    store.save(rec)
    result_json = store.artifacts_dir("r1") / "result.json"
    assert json.loads(result_json.read_text())["summary"] == "ok"
    assert store.delete("r1") is True
    assert store.get("r1") is None
    assert not (tmp_path / "runs" / "artifacts" / "r1").exists()
    assert store.delete("r1") is False  # идемпотентно


def test_store_legacy_json_import(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    legacy = _record("legacy1", status="completed")
    (runs_dir / "legacy1.json").write_text(legacy.model_dump_json(), encoding="utf-8")
    (runs_dir / "broken.json").write_text("{not json", encoding="utf-8")
    store = SqliteRunStore(runs_dir)
    assert store.get("legacy1") is not None
    assert store.list_ids() == ["legacy1"]
    # файлы уехали в legacy_json/, повторный старт не дублирует
    assert not (runs_dir / "legacy1.json").exists()
    assert (runs_dir / "legacy_json" / "legacy1.json").exists()
    store2 = SqliteRunStore(runs_dir)
    assert store2.list_ids() == ["legacy1"]


class InstantOrchestrator:
    """Стаб: мгновенно завершает run — для API-тестов без браузера/LLM."""

    def __init__(self, store):
        self._store = store

    async def run(self, record: RunRecord, cancel_event=None) -> RunRecord:
        await asyncio.sleep(0.05)
        record.status = "completed"
        record.pages_visited = 1
        self._store.save(record)
        return record


@pytest.fixture()
async def api_client(tmp_path, monkeypatch):
    settings = Settings(data_dir=REPO_ROOT / "data", runs_dir_override=tmp_path / "runs")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        # подменяем на изолированный store + мгновенный оркестратор (DI через app.state)
        app.state.run_store = SqliteRunStore(tmp_path / "runs")
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


async def test_cancel_run_flow(api_client):
    client, app = api_client

    class CancelableOrchestrator(InstantOrchestrator):
        async def run(self, record, cancel_event=None):
            for _ in range(100):  # ждём cancel до ~2 s
                if cancel_event is not None and cancel_event.is_set():
                    record.status = "canceled"
                    record.metadata["canceled_by_user"] = True
                    self._store.save(record)
                    return record
                await asyncio.sleep(0.02)
            return await super().run(record, cancel_event)

    app.state.orchestrator_factory = lambda: CancelableOrchestrator(app.state.run_store)
    run_id = (await client.post(
        "/runs", json={"start_url": "https://example.com", "task": "t"})).json()["run_id"]
    r = await client.post(f"/runs/{run_id}/cancel")
    assert r.status_code == 202 and r.json()["status"] == "canceling"
    for _ in range(50):
        record = (await client.get(f"/runs/{run_id}")).json()
        if record["status"] != "running":
            break
        await asyncio.sleep(0.02)
    assert record["status"] == "canceled"
    # 409 повторно (terminal), 404 для неизвестного
    assert (await client.post(f"/runs/{run_id}/cancel")).status_code == 409
    assert (await client.post("/runs/nope/cancel")).status_code == 404
    # canceled run можно удалить
    assert (await client.delete(f"/runs/{run_id}")).status_code == 200


async def test_cancel_zombie_and_delete_active(api_client):
    client, app = api_client
    store = app.state.run_store
    # zombie: running-запись без живой таски → cancel финализирует напрямую
    store.save(_record("zombie", status="running"))
    assert (await client.delete("/runs/zombie")).status_code == 409  # активный не удалить
    r = await client.post("/runs/zombie/cancel")
    assert r.status_code == 202
    assert store.get("zombie").status == "canceled"
    assert (await client.delete("/runs/zombie")).status_code == 200


async def test_get_unknown_run_404(api_client):
    client, _ = api_client
    assert (await client.get("/runs/nope")).status_code == 404
    assert (await client.get("/runs/nope/result")).status_code == 404


async def test_health_shape(api_client):
    client, _ = api_client
    data = (await client.get("/health")).json()
    assert {"status", "ollama", "models", "active_run_id"} <= set(data)
