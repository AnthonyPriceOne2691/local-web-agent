"""Attended-режим (Phase 5, doc 24): пауза на anti-bot challenge → человек проходит →
повторный OBSERVE. Реального браузера нет — FakeBrowser отдаёт captcha, затем контент."""

from __future__ import annotations

import asyncio

from app.orchestrator.attended import EventAttendedGate
from app.schemas.research import SessionRecord
from app.schemas.run import RunConfig, RunRecord
from tests.conftest import FakeBrowserSession, page_raw
from tests.test_api_and_store import api_client  # noqa: F401 — fixture reuse
from tests.test_orchestrator import make_orchestrator, record_for
from tests.test_sse_and_ui_endpoints import _collect_events, _fast_sse

CHALLENGE = page_raw(title="Just a moment", text="Checking your browser cloudflare " * 5)


class ChallengeBrowser(FakeBrowserSession):
    """Первый ЗАХОД на challenge_url → captcha, повторный (после resume) → контент.

    Счётчик по goto, не по raw_snapshot: SPA-fallback делает два raw_snapshot за
    один заход — challenge должен держаться до нового goto (как на реальном сайте)."""

    def __init__(self, pages: dict, *, challenge_url: str):
        super().__init__(pages)
        self._challenge_url = challenge_url
        self._goto_count = 0

    async def goto(self, url: str, *, timeout_ms: int) -> str:
        final = await super().goto(url, timeout_ms=timeout_ms)
        if final == self._challenge_url:
            self._goto_count += 1
        return final

    async def raw_snapshot(self) -> dict:
        if self.current_url == self._challenge_url and self._goto_count <= 1:
            return CHALLENGE
        return self.pages[self.current_url]


async def _wait_status(record: RunRecord, status: str, *, tries: int = 300) -> bool:
    for _ in range(tries):
        if record.status == status:
            return True
        await asyncio.sleep(0.01)
    return False


# ---------------------------------------------------------- orchestrator
async def test_attended_pause_resume_then_observe(tmp_path):
    origin = "http://127.0.0.1:8911"
    browser = ChallengeBrowser(
        {f"{origin}/": page_raw(title="Home", text="Real page content here " * 40)},
        challenge_url=f"{origin}/")
    orch, store, _llm = make_orchestrator(tmp_path, browser, [
        {"action": "stop", "reasoning": "content is here"},
        {"summary": "Home read after challenge", "facts": [], "not_found": []},
    ])
    resume = asyncio.Event()
    gate = EventAttendedGate(resume, store, timeout_s=5.0)
    record = record_for(f"{origin}/", task="read page", attended=True,
                        respect_robots=False, vision_enabled="never",
                        capture_screenshots="never")

    task = asyncio.create_task(orch.run(record, attended_gate=gate))
    assert await _wait_status(record, "waiting_user"), "run не встал на паузу"
    assert record.metadata["challenge"]["kind"] == "captcha"
    assert record.metadata["challenge"]["url"] == f"{origin}/"
    resume.set()  # человек прошёл проверку
    result = await task

    assert result.metadata.get("blocked_by") is None       # не заблокирован
    assert result.metadata.get("challenge_cleared") == 1
    assert result.metadata.get("challenge") is None         # снят
    assert browser.visited_log.count(f"{origin}/") == 2     # captcha + повторный заход
    assert result.status in ("completed", "partial", "not_found")


async def test_attended_timeout_blocks(tmp_path):
    origin = "http://127.0.0.1:8912"
    browser = ChallengeBrowser(
        {f"{origin}/": page_raw(title="Home", text="content " * 40)},
        challenge_url=f"{origin}/")
    orch, _store2, _llm = make_orchestrator(tmp_path, browser, [
        {"summary": "unused", "facts": [], "not_found": []},
    ])
    resume = asyncio.Event()  # никто не пройдёт проверку
    gate = EventAttendedGate(resume, _store2, timeout_s=0.05)
    record = record_for(f"{origin}/", task="read", attended=True,
                        respect_robots=False, vision_enabled="never",
                        capture_screenshots="never")

    result = await orch.run(record, attended_gate=gate)
    assert result.status == "blocked"
    assert result.metadata["blocked_by"] == "captcha"
    assert result.metadata.get("challenge_timeout") is True


async def test_captcha_without_attended_still_blocks(tmp_path):
    """Без attended-gate поведение прежнее: captcha → blocked сразу (регрессия Phase 2)."""
    origin = "http://127.0.0.1:8913"
    browser = ChallengeBrowser(
        {f"{origin}/": page_raw(title="Home", text="content " * 40)},
        challenge_url=f"{origin}/")
    orch, _store3, _llm = make_orchestrator(tmp_path, browser, [
        {"summary": "x", "facts": [], "not_found": []}])
    record = record_for(f"{origin}/", task="read", respect_robots=False,
                        vision_enabled="never", capture_screenshots="never")

    result = await orch.run(record)  # attended_gate=None
    assert result.status == "blocked"
    assert result.metadata["blocked_by"] == "captcha"
    assert browser.visited_log.count(f"{origin}/") == 1  # без повторного захода


# ------------------------------------------------------------- SSE + API
async def test_sse_emits_challenge_wait(api_client):  # noqa: F811
    client, app = api_client
    _fast_sse(app)
    sessions, runs = app.state.session_store, app.state.run_store
    sessions.save(SessionRecord(id="chsse", status="running_tools", created_at="t"))
    run = RunRecord(id="runwait", status="waiting_user", session_id="chsse", started_at="t",
                    config=RunConfig(start_url="http://site.test/x", task="t", attended=True),
                    metadata={"challenge": {"url": "http://site.test/x", "kind": "captcha"}})
    runs.save(run)

    async def _advance() -> None:
        await asyncio.sleep(0.05)
        run.status = "completed"
        runs.save(run)
        sessions.save(SessionRecord(id="chsse", status="completed", created_at="t"))

    task = asyncio.create_task(_advance())
    events = await _collect_events(client, "/sessions/chsse/events")
    await task

    challenge = [d for n, d in events if n == "challenge_wait"]
    assert challenge, "нет события challenge_wait"
    assert challenge[0]["kind"] == "captcha"
    assert challenge[0]["url"] == "http://site.test/x"
    assert challenge[0]["run_id"] == "runwait"


async def test_resume_run_endpoint_guards(api_client):  # noqa: F811
    client, app = api_client
    runs = app.state.run_store
    assert (await client.post("/runs/nope/resume")).status_code == 404
    runs.save(RunRecord(id="rdone", status="completed", started_at="t",
                        config=RunConfig(start_url="http://a", task="t")))
    r = await client.post("/runs/rdone/resume")  # не в waiting_user
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "not_waiting"


async def test_resume_session_endpoint_sets_event(api_client):  # noqa: F811
    client, app = api_client
    sessions, runs = app.state.session_store, app.state.run_store
    sessions.save(SessionRecord(id="srez", status="running_tools", created_at="t"))
    runs.save(RunRecord(id="ractive", status="waiting_user", session_id="srez", started_at="t",
                        config=RunConfig(start_url="http://a", task="t", attended=True)))
    event = asyncio.Event()
    app.state.session_resume_events["srez"] = event

    r = await client.post("/sessions/srez/resume")
    assert r.status_code == 202
    assert event.is_set()  # resume проброшен в активный crawl

    # active_run_id считает waiting_user занятым → D-12 lock держится
    assert app.state.run_store.active_run_id() == "ractive"
