"""Orchestrator edge-ветки: config-fail, extract_now, robots deny, I-H7/G-H1,
fallback exhausted, screenshot/consent сбои (coverage-гейт ≥90%, doc 18)."""

from __future__ import annotations

import httpx
import pytest

from app.orchestrator.robots import RobotsPolicy
from tests.conftest import FakeBrowserSession, page_raw
from tests.test_orchestrator import make_orchestrator, record_for

ORIGIN = "http://127.0.0.1:8901"

NOT_FOUND_SYNTH = {"summary": "none", "facts": [], "not_found": [{"key": "phone", "reason": "absent"}]}


@pytest.fixture
def one_pager() -> FakeBrowserSession:
    return FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Home", text="Welcome words " * 30, links=[(f"{ORIGIN}/contact", "Contact us")]
            ),
            f"{ORIGIN}/contact": page_raw(title="Contact", text="Call +1 555 " * 30),
        }
    )


async def test_config_hard_violation_fails_before_start(tmp_path, one_pager):
    orch, store, llm = make_orchestrator(tmp_path, one_pager, [])
    record = await orch.run(record_for("ftp://x.com/"))
    assert record.status == "failed"
    assert "P-1" in record.error_message
    assert llm.calls == [] and one_pager.visited_log == []


async def test_config_soft_note_on_public_rate(tmp_path, monkeypatch):
    """rate_limit_ms=0 на публичном хосте → soft G-H4 note, run продолжается."""
    from app.orchestrator import discovery as discovery_mod

    async def no_probes(client, origin, slugs):
        return [], []

    async def no_legal(client, origin, slugs, cache, timeout_s=4.0):
        return []

    async def no_robots(origin, *, respect):
        return RobotsPolicy(None, 0.0)

    # пробы живут в orchestrator.discovery (вынесены из loop.py, ≤500 LOC)
    monkeypatch.setattr(discovery_mod, "probe_slugs_f1", no_probes)
    monkeypatch.setattr(discovery_mod, "filter_alive", no_legal)
    monkeypatch.setattr(RobotsPolicy, "load", no_robots)
    browser = FakeBrowserSession({"https://example.com/": page_raw(title="Home", text="words " * 60)})
    orch, _, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "stop", "reasoning": "done"},
            NOT_FOUND_SYNTH,
        ],
    )
    record = await orch.run(record_for("https://example.com/", rate_limit_ms=0))
    assert any("raised to floor" in n for n in record.metadata.get("config_notes", []))


async def test_extract_now_streak_breaks_loop(tmp_path, one_pager):
    synth = {
        "summary": "found on homepage",
        "facts": [
            {
                "key": "greeting",
                "value": "Welcome",
                "confidence": "high",
                "evidence": [{"url": f"{ORIGIN}/", "quote": "Welcome words"}],
            }
        ],
        "not_found": [],
    }
    orch, _, _ = make_orchestrator(
        tmp_path,
        one_pager,
        [
            {"action": "extract_now", "reasoning": "answer visible"},
            {"action": "extract_now", "reasoning": "still here"},  # streak 2 → break
            synth,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert record.pages_visited == 1
    assert record.status == "completed"  # цитата прошла S-H3


async def test_robots_deny_skips_navigation(tmp_path, one_pager, monkeypatch):
    class DenyAll(RobotsPolicy):
        def __init__(self):
            super().__init__(None, 0.0)

        def allowed(self, url: str) -> bool:
            return False

    async def fake_load(cls, origin, *, respect):
        return DenyAll()

    monkeypatch.setattr(RobotsPolicy, "load", classmethod(fake_load))
    orch, _, llm = make_orchestrator(tmp_path, one_pager, [NOT_FOUND_SYNTH])
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert any("robots_disallow" in s.note for s in record.steps)
    assert record.pages_visited == 0


async def test_unparseable_action_ih7_then_recovers(tmp_path, one_pager):
    orch, _, _ = make_orchestrator(
        tmp_path,
        one_pager,
        [
            "complete garbage, not json",  # I-H7
            {"action": "stop", "reasoning": "ok now"},
            NOT_FOUND_SYNTH,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/"))
    violations = [v for s in record.steps for v in s.violations]
    assert any(v.constraint_id == "I-H7" for v in violations)
    assert record.status == "not_found"


async def test_gh1_budget_forces_stop(tmp_path, one_pager):
    orch, _, _ = make_orchestrator(
        tmp_path,
        one_pager,
        [
            {"action": "navigate", "url": f"{ORIGIN}/contact", "reasoning": "greedy"},  # budget=1
            NOT_FOUND_SYNTH,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/", max_pages=1))
    violations = [v for s in record.steps for v in s.violations]
    assert any(v.constraint_id == "G-H1" for v in violations)
    assert record.pages_visited == 1


async def test_fallback_exhausted_stops_gracefully(tmp_path):
    """Все кандидаты невалидны (визитед) → stop 'no valid candidates'."""
    browser = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Dead end", text="nothing here " * 30, links=[(f"{ORIGIN}/", "self loop")]
            )
        }
    )
    replies = [{"action": "navigate", "url": f"{ORIGIN}/", "reasoning": "loop"}] * 3
    replies.append(NOT_FOUND_SYNTH)
    orch, _, _ = make_orchestrator(tmp_path, browser, replies)
    record = await orch.run(record_for(f"{ORIGIN}/"))
    stop_steps = [s for s in record.steps if s.action == "stop"]
    assert stop_steps and "no valid candidates" in stop_steps[-1].reasoning


async def test_screenshot_failure_does_not_kill_run(tmp_path):
    class BrokenShots(FakeBrowserSession):
        async def screenshot(self, path: str) -> None:
            raise RuntimeError("disk full")

    browser = BrokenShots({f"{ORIGIN}/": page_raw(title="SPA", text="tiny")})
    orch, _, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "stop", "reasoning": "done"},
            NOT_FOUND_SYNTH,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/", task="Find the price"))
    assert record.status == "not_found"  # run выжил без скриншота


async def test_synthesis_timeout_does_not_throw_away_the_pages_read(tmp_path):
    """Живой прогон T-3h: `legalbet.ru` прочитал 4 страницы, включая целевую статью, и упал
    на синтезе таймаутом локальной модели — прогон ушёл в `failed`, а прочитанное пропало
    целиком, будто сайт не читался (doc 26 § T-3h).

    Прогон остаётся `failed` (иначе сайт без фактов полезет в сравнение и получит оценку),
    но страницы обязаны остаться в записи: их читали, и в отчёте это должно быть видно.
    """

    class TimingOutSynth:
        async def synthesize(self, **_kwargs):
            raise httpx.ReadTimeout("timed out")

    browser = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Home", text="Words about betting " * 30, links=[(f"{ORIGIN}/wiki", "Как ставить")]
            ),
            f"{ORIGIN}/wiki": page_raw(title="Wiki", text="How to bet on football " * 40),
        }
    )
    orch, store, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "navigate", "url": f"{ORIGIN}/wiki", "reasoning": "article"},
            {"action": "stop", "reasoning": "read enough"},
        ],
    )
    orch._synthesizer = TimingOutSynth()  # type: ignore[assignment]

    record = await orch.run(record_for(f"{ORIGIN}/", task="Найди статью про ставки на футбол"))

    assert record.status == "failed"  # в сравнение не попадёт
    assert record.metadata.get("failed_stage") == "SYNTHESIZE"
    assert record.pages_visited == 2
    assert record.result is not None, "прочитанное выброшено — именно этот дефект и чинится"
    assert record.result.pages_visited == 2
    assert f"{ORIGIN}/wiki" in (record.result.summary or "")
    # То же состояние обязано лежать в store, а не только в объекте в памяти.
    assert store.get(record.id).result is not None


async def test_consent_failure_marked_not_fatal(tmp_path):
    class BrokenConsent(FakeBrowserSession):
        async def eval_js(self, script: str):
            raise RuntimeError("page crashed")

    browser = BrokenConsent({f"{ORIGIN}/": page_raw(title="SPA", text="tiny")})
    orch, _, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "stop", "reasoning": "done"},
            {
                "profile": "desktop",
                "screen_status": "blank",
                "description": "",
                "extracted": [],
                "confidence": "low",
            },  # vision batch (empty DOM auto)
            NOT_FOUND_SYNTH,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/", task="Find the price"))
    assert record.metadata["consent"][f"{ORIGIN}/"] == "failed"
    assert record.status == "not_found"
