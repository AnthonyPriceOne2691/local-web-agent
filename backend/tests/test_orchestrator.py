"""Оркестратор с моками Browser/LLM: happy path, fallback recovery, redirect discard,
blocker stop, budget, SPA fallback screenshot (doc 18 § обязательные кейсы)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.llm.navigator import Navigator
from app.llm.synthesizer import Synthesizer
from app.orchestrator.loop import CrawlOrchestrator
from app.schemas.run import RunConfig, RunRecord
from app.storage.sqlite_store import SqliteRunStore
from tests.conftest import REPO_ROOT, FakeBrowserSession, FakeOllama, page_raw

ORIGIN = "http://127.0.0.1:8901"

SYNTH_OK = {
    "summary": "Phone found",
    "facts": [{"key": "phone", "label": "Phone", "value": "+1 555",
               "confidence": "high",
               "evidence": [{"url": f"{ORIGIN}/contact", "quote": "+1 555"}]}],
    "not_found": [],
}


def make_orchestrator(tmp_path, browser, replies) -> tuple[CrawlOrchestrator, SqliteRunStore, FakeOllama]:
    settings = Settings(data_dir=REPO_ROOT / "data")
    store = SqliteRunStore(tmp_path / "runs")
    llm = FakeOllama(replies)
    from app.navigation.path_hints import PathHints

    orch = CrawlOrchestrator(
        settings=settings,
        browser=browser,
        navigator=Navigator(llm, settings),  # type: ignore[arg-type]
        synthesizer=Synthesizer(llm, settings),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        store=store,
        hints=PathHints.load(REPO_ROOT / "data" / "navigation"),
    )
    return orch, store, llm


def record_for(url: str, task: str = "Find the phone number", **cfg) -> RunRecord:
    return RunRecord(id="test-run", config=RunConfig(start_url=url, task=task, **cfg))


@pytest.fixture()
def two_page_site() -> FakeBrowserSession:
    return FakeBrowserSession({
        f"{ORIGIN}/": page_raw(title="Home", text="Welcome to Acme " * 30,
                               links=[(f"{ORIGIN}/contact", "Contact us")]),
        f"{ORIGIN}/contact": page_raw(title="Contact", text="Call +1 555 " * 30),
    })


async def test_happy_path_navigate_extract_synthesize(tmp_path, two_page_site):
    orch, store, llm = make_orchestrator(tmp_path, two_page_site, [
        {"action": "navigate", "url": f"{ORIGIN}/contact", "reasoning": "contact page"},
        {"action": "stop", "reasoning": "found"},
        SYNTH_OK,
    ])
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert record.status == "completed"
    assert record.pages_visited == 2
    assert record.result.facts[0].key == "phone"
    assert two_page_site.closed is True
    assert store.get("test-run").status == "completed"
    assert llm.unloaded  # swap: nav model выгружена перед synthesis


async def test_fabricated_url_recovers_via_fallback(tmp_path, two_page_site):
    orch, _, _ = make_orchestrator(tmp_path, two_page_site, [
        {"action": "navigate", "url": f"{ORIGIN}/admin", "reasoning": "invented"},  # I-H6
        {"action": "navigate", "url": f"{ORIGIN}/admin", "reasoning": "again"},     # replan 1 мимо
        {"action": "navigate", "url": f"{ORIGIN}/admin", "reasoning": "stubborn"},  # replan 2 (k=2) мимо
        {"action": "stop", "reasoning": "done"},
        SYNTH_OK,
    ])
    record = await orch.run(record_for(f"{ORIGIN}/"))
    violations = [v for s in record.steps for v in s.violations]
    assert sum(v.constraint_id == "I-H6" for v in violations) == 3  # k=2 → 3 попытки
    assert all(v.recovered for v in violations if v.constraint_id == "I-H6")  # fallback = recovery
    # fallback link scorer повёл на валидного кандидата
    assert record.pages_visited == 2
    drift = record.metadata["drift"]
    assert drift["fallbacks"] == 1 and drift["ih6"] == 3


async def test_drift_fallback_only_skips_llm_navigation(tmp_path, two_page_site):
    """Recovery success < 50% → link_scorer-only до конца run (doc 13 § Drift)."""
    orch, _, llm = make_orchestrator(tmp_path, two_page_site, [SYNTH_OK])
    record = record_for(f"{ORIGIN}/")
    record.metadata["drift"] = {"hard_total": 4, "ih6": 0,
                                "replan_ok": 0, "replan_fail": 2, "fallbacks": 2}
    record = await orch.run(record)
    # навигация шла без LLM (fallback-only): единственный chat-вызов — synthesis
    assert len(llm.calls) == 1
    assert record.pages_visited == 2  # fallback повёл на /contact


async def test_drift_low_temperature_after_hard_violations(tmp_path, two_page_site):
    orch, _, llm = make_orchestrator(tmp_path, two_page_site, [
        {"action": "stop", "reasoning": "done"},
        SYNTH_OK,
    ])
    record = record_for(f"{ORIGIN}/")
    record.metadata["drift"] = {"hard_total": 3, "ih6": 0,
                                "replan_ok": 5, "replan_fail": 0, "fallbacks": 0}
    await orch.run(record)
    assert llm.calls[0]["temperature"] == 0.2  # auto-tighten 0.4 → 0.2


async def test_offsite_redirect_discarded_mid_run(tmp_path):
    browser = FakeBrowserSession(
        pages={
            f"{ORIGIN}/": page_raw(title="Home", text="w " * 200,
                                   links=[(f"{ORIGIN}/out", "Out")]),
            "http://127.0.0.1:9999/evil": page_raw(title="Evil", text="evil " * 100),
        },
        redirects={f"{ORIGIN}/out": "http://127.0.0.1:9999/evil"},
    )
    orch, _, _ = make_orchestrator(tmp_path, browser, [
        {"action": "navigate", "url": f"{ORIGIN}/out", "reasoning": "go"},
        {"action": "stop", "reasoning": "nothing else"},
        {"summary": "nothing", "facts": [], "not_found": [{"key": "phone", "reason": "n/a"}]},
    ])
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert any("redirect_offsite" in s.note for s in record.steps)
    assert record.pages_visited == 1  # evil-страница не вошла


async def test_blocker_stops_run(tmp_path):
    browser = FakeBrowserSession({
        f"{ORIGIN}/": page_raw(title="Verify", text="Checking your browser before accessing"),
    })
    orch, _, _ = make_orchestrator(tmp_path, browser, [
        {"summary": "blocked", "facts": [], "not_found": []},
    ])
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert record.status == "blocked"
    assert record.metadata["blocked_by"] == "captcha"


async def test_spa_fallback_screenshot_captured(tmp_path):
    browser = FakeBrowserSession({
        f"{ORIGIN}/": page_raw(title="SPA", text="tiny"),  # < 200 chars
    })
    orch, _, _ = make_orchestrator(tmp_path, browser, [
        {"action": "stop", "reasoning": "nothing to click"},
        {"summary": "no price visible in DOM", "facts": [],
         "not_found": [{"key": "price", "reason": "not in DOM"}]},
    ])
    record = await orch.run(record_for(f"{ORIGIN}/", task="Find the price"))
    assert browser.screenshots  # SPA fallback capture сработал при auto
    assert record.status == "not_found"


async def test_cancel_before_synthesis_skips_llm(tmp_path, two_page_site):
    """FR-3.8: canceled run сохраняет partial trace, SYNTHESIZE пропущен."""
    import asyncio

    orch, store, llm = make_orchestrator(tmp_path, two_page_site, [SYNTH_OK])
    event = asyncio.Event()
    event.set()  # отменён ещё до первого шага
    record = await orch.run(record_for(f"{ORIGIN}/"), cancel_event=event)
    assert record.status == "canceled"
    assert record.metadata["canceled_by_user"] is True
    assert llm.calls == []  # ни навигации, ни синтеза
    assert two_page_site.closed is True
    assert store.get("test-run").status == "canceled"


async def test_early_stop_gs1_after_three_stale_pages(tmp_path):
    """G-S1: три посещённые страницы подряд без новых релевантных ссылок → SYNTHESIZE."""
    chain = {}
    for i, name in enumerate(["", "a", "b", "c", "d"]):
        nxt = ["a", "b", "c", "d"][i] if i < 4 else None
        links = [(f"{ORIGIN}/{nxt}", f"page {nxt}")] if nxt else []
        chain[f"{ORIGIN}/{name}" if name else f"{ORIGIN}/"] = page_raw(
            title=f"P{i}", text="generic filler words here " * 20, links=links)
    browser = FakeBrowserSession(chain)
    replies = [{"action": "navigate", "url": f"{ORIGIN}/{n}", "reasoning": "next"}
               for n in ["a", "b", "c", "d"]]
    replies.append({"action": "stop", "reasoning": "exhausted"})
    replies.append({"summary": "nothing found", "facts": [],
                    "not_found": [{"key": "phone", "reason": "absent"}]})
    orch, _, _ = make_orchestrator(tmp_path, browser, replies)
    record = await orch.run(record_for(f"{ORIGIN}/", max_pages=10))
    assert record.metadata.get("early_stop", "").startswith("G-S1")
    assert record.pages_visited < 6  # остановились раньше бюджета


async def test_start_page_unreachable_fails_cleanly(tmp_path):
    browser = FakeBrowserSession(pages={})
    orch, _, _ = make_orchestrator(tmp_path, browser, [])
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert record.status == "failed"
    assert "no pages observed" in (record.result.summary if record.result else record.error_message)
