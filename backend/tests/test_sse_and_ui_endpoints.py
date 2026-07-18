"""Phase 4 бэкенд: SSE /sessions/{id}/events, report, step screenshot (doc 15 v0.6)."""

from __future__ import annotations

import asyncio
import json

from app.schemas.research import SessionMessage, SessionRecord
from app.schemas.run import CrawlStep, RunConfig, RunRecord
from tests.test_api_and_store import api_client  # noqa: F401 — fixture reuse

# 1×1 прозрачный PNG (минимальный валидный файл для FileResponse-теста)
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da6364f8ffff3f0005fe02fea72d0e660000000049454e44ae426082"
)


async def _collect_events(client, url: str, *, timeout: float = 5.0) -> list[tuple[str, dict]]:
    """Читает SSE до события done (или таймаута); возвращает [(event, data), ...]."""
    events: list[tuple[str, dict]] = []
    async with asyncio.timeout(timeout):
        async with client.stream("GET", url) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            name = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    name = line.removeprefix("event: ")
                elif line.startswith("data: ") and name:
                    events.append((name, json.loads(line.removeprefix("data: "))))
                    if name == "done":
                        return events
    return events


def _fast_sse(app) -> None:
    app.state.settings.sse_poll_interval_s = 0.01


async def test_events_stream_replays_terminal_session(api_client):  # noqa: F811
    client, app = api_client
    _fast_sse(app)
    store = app.state.session_store
    session = SessionRecord(id="done1", status="completed", created_at="t", messages=[
        SessionMessage(role="user", content="compare a b", created_at="t"),
        SessionMessage(role="tool", content="crawl_site http://a (1/2)", created_at="t"),
        SessionMessage(role="assistant", content="Winner: a", created_at="t"),
    ])
    store.save(session)

    events = await _collect_events(client, "/sessions/done1/events")
    names = [n for n, _ in events]
    assert names == ["status", "message", "message", "message", "done"]
    assert events[0][1]["status"] == "completed"
    assert [e[1]["role"] for e in events[1:4]] == ["user", "tool", "assistant"]
    assert events[-1][1] == {"session_id": "done1", "status": "completed"}

    # реконнект с since_messages пропускает уже виденное
    events = await _collect_events(client, "/sessions/done1/events?since_messages=2")
    assert [n for n, _ in events] == ["status", "message", "done"]
    assert events[1][1]["index"] == 2

    assert (await client.get("/sessions/nope/events")).status_code == 404


async def test_events_stream_live_session_with_crawl_progress(api_client):  # noqa: F811
    client, app = api_client
    _fast_sse(app)
    sessions, runs = app.state.session_store, app.state.run_store
    session = SessionRecord(id="live1", status="running_tools", created_at="t")
    sessions.save(session)
    run = RunRecord(id="run1", config=RunConfig(start_url="http://a", task="t", max_pages=6),
                    status="running", session_id="live1", pages_visited=1,
                    current_url="http://a/", started_at="t")
    runs.save(run)

    async def _advance() -> None:
        await asyncio.sleep(0.05)
        run.pages_visited, run.current_url = 3, "http://a/pricing"
        runs.save(run)
        await asyncio.sleep(0.05)
        run.status = "completed"
        runs.save(run)
        session.status = "completed"
        session.messages.append(SessionMessage(role="assistant", content="ok", created_at="t"))
        sessions.save(session)

    task = asyncio.create_task(_advance())
    events = await _collect_events(client, "/sessions/live1/events")
    await task

    names = [n for n, _ in events]
    assert names[0] == "status" and events[0][1]["status"] == "running_tools"
    progress = [d for n, d in events if n == "crawl_progress"]
    assert progress[0]["pages_visited"] == 1 and progress[0]["max_pages"] == 6
    assert progress[-1]["pages_visited"] == 3
    assert progress[-1]["current_url"] == "http://a/pricing"
    assert ("message", {"index": 0, "role": "assistant", "content": "ok",
                        "created_at": "t"}) in events
    assert names[-1] == "done" and events[-1][1]["status"] == "completed"


async def test_events_stream_foreign_active_run_not_reported(api_client):  # noqa: F811
    """crawl_progress отдаёт только run своей сессии (D-12: активный run глобален)."""
    client, app = api_client
    _fast_sse(app)
    app.state.session_store.save(SessionRecord(id="mine", status="completed", created_at="t"))
    app.state.run_store.save(RunRecord(
        id="foreign", config=RunConfig(start_url="http://x", task="t"),
        status="running", session_id="other-session", started_at="t"))

    events = await _collect_events(client, "/sessions/mine/events")
    assert [n for n, _ in events] == ["status", "done"]


async def test_session_report_endpoint(api_client):  # noqa: F811
    client, app = api_client
    store = app.state.session_store
    store.save(SessionRecord(id="rep1", status="completed", created_at="t"))

    assert (await client.get("/sessions/rep1/report")).status_code == 404
    assert (await client.get("/sessions/nope/report")).status_code == 404

    (store.artifacts_dir("rep1") / "comparison_report.md").write_text("# Report\nwinner: a")
    resp = await client.get("/sessions/rep1/report")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert resp.text.startswith("# Report")


async def test_step_screenshot_endpoint(api_client):  # noqa: F811
    client, app = api_client
    store = app.state.run_store
    record = RunRecord(
        id="shot1", config=RunConfig(start_url="http://a", task="t"), status="completed",
        started_at="t",
        steps=[CrawlStep(index=0, state="OBSERVE", url="http://a",
                         screenshot_paths={"desktop": "screenshots/000_desktop.png"})])
    store.save(record)
    shots = store.artifacts_dir("shot1") / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    (shots / "000_desktop.png").write_bytes(PNG_BYTES)

    resp = await client.get("/runs/shot1/steps/0/screenshot")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == PNG_BYTES

    assert (await client.get("/runs/shot1/steps/0/screenshot?profile=mobile")).status_code == 404
    assert (await client.get("/runs/shot1/steps/9/screenshot")).status_code == 404
    assert (await client.get("/runs/nope/steps/0/screenshot")).status_code == 404
