"""Sessions API (doc 15) + e2e UC-1/UC-2 через настоящий crawl-стек на моках."""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.llm.navigator import Navigator
from app.llm.synthesizer import Synthesizer
from app.orchestrator.loop import CrawlOrchestrator
from app.research.compare_synthesizer import CompareSynthesizer
from app.research.runner import ResearchRunner
from app.schemas.research import SessionMessage, SessionRecord
from app.storage.session_store import SqliteSessionStore
from app.storage.sqlite_store import SqliteRunStore
from tests.conftest import REPO_ROOT, FakeBrowserSession, FakeOllama, page_raw
from tests.test_api_and_store import api_client  # noqa: F401 — fixture reuse

SITE_A = "http://127.0.0.1:9001"
SITE_B = "http://127.0.0.1:9002"


# ------------------------------------------------------------ API surface
class FakeRunner:
    def __init__(self, session_store):
        self._sessions = session_store

    async def run_message(self, session, message, cancel_event=None, resume_event=None):
        await asyncio.sleep(0.05)
        session.status = "completed"
        session.messages.append(SessionMessage(role="assistant", content="done", created_at="t"))
        self._sessions.save(session)
        return session


async def test_session_creation_reports_the_effective_hop_depth(api_client):  # noqa: F811
    """Глубина приходила из процесса API, и её невидимость сорвала A/B: два прогона одной
    и той же команды разошлись (2 против 3), а увидеть это можно было только в
    `config_json` записи прогона (doc 26 § T-3f-1). Теперь она возвращается числом и её
    можно задать на сессию."""
    client, app = api_client

    default = (await client.post("/sessions", json={})).json()
    assert default["max_depth"] == app.state.settings.max_depth

    explicit = (await client.post("/sessions", json={"max_depth": 3})).json()
    assert explicit["max_depth"] == 3
    sid = explicit["session_id"]
    assert (await client.get(f"/sessions/{sid}")).json()["config"]["max_depth"] == 3

    # Вне диапазона — отказ схемой, а не молча принятая ерунда.
    assert (await client.post("/sessions", json={"max_depth": 99})).status_code == 422


async def test_sessions_api_lifecycle(api_client):  # noqa: F811
    client, app = api_client
    app.state.research_runner_factory = lambda: FakeRunner(app.state.session_store)

    sid = (await client.post("/sessions", json={"title": "t"})).json()["session_id"]
    assert (await client.get(f"/sessions/{sid}")).json()["status"] == "active"
    assert (await client.post("/sessions/nope/messages", json={"content": "x"})).status_code == 404

    r = await client.post(f"/sessions/{sid}/messages", json={"content": "дизайн https://a.com https://b.com"})
    assert r.status_code == 202
    for _ in range(50):
        session = (await client.get(f"/sessions/{sid}")).json()
        if session["status"] not in ("active", "running_tools", "comparing"):
            break
        await asyncio.sleep(0.02)
    assert session["status"] == "completed"
    listing = (await client.get("/sessions")).json()
    assert listing["sessions"][0]["session_id"] == sid
    # cancel по завершённой — 409; delete — ok
    assert (await client.post(f"/sessions/{sid}/cancel")).status_code == 409
    assert (await client.delete(f"/sessions/{sid}")).status_code == 200
    assert (await client.get(f"/sessions/{sid}")).status_code == 404


async def test_session_busy_cancel_and_delete_guards(api_client):  # noqa: F811
    client, app = api_client

    class WaitingRunner:
        def __init__(self, store):
            self._sessions = store

        async def run_message(self, session, message, cancel_event=None, resume_event=None):
            session.status = "running_tools"
            self._sessions.save(session)
            for _ in range(100):  # ждём cancel ~2 s
                if cancel_event is not None and cancel_event.is_set():
                    break
                await asyncio.sleep(0.02)
            session.status = "failed"
            session.messages.append(SessionMessage(role="assistant", content="canceled", created_at="t"))
            self._sessions.save(session)
            return session

    app.state.research_runner_factory = lambda: WaitingRunner(app.state.session_store)
    sid = (await client.post("/sessions", json={})).json()["session_id"]
    assert (
        await client.post(f"/sessions/{sid}/messages", json={"content": "x https://a.com"})
    ).status_code == 202
    await asyncio.sleep(0.1)
    # busy: второй message и delete → 409
    assert (await client.post(f"/sessions/{sid}/messages", json={"content": "y"})).status_code == 409
    assert (await client.delete(f"/sessions/{sid}")).status_code == 409
    r = await client.post(f"/sessions/{sid}/cancel")
    assert r.status_code == 202
    for _ in range(50):
        session = (await client.get(f"/sessions/{sid}")).json()
        if session["status"] not in ("running_tools", "comparing"):
            break
        await asyncio.sleep(0.02)
    assert session["status"] == "failed"
    assert (await client.post("/sessions/nope/cancel")).status_code == 404


# --------------------------------------------------------- deep e2e (mock)
def _uc2_pages() -> dict[str, dict]:
    guide = (
        "Football betting guide. Odds formats explained with examples. " * 40
        + "FAQ: how to read odds? What is value betting? League tables included."
    )
    basics = "Betting basics. Short overview of football betting. " * 6
    return {
        f"{SITE_A}/": page_raw(
            title="Alpha Blog",
            text="Welcome to alpha " * 30,
            links=[(f"{SITE_A}/blog/football-betting-guide", "Betting guide")],
        ),
        f"{SITE_A}/blog/football-betting-guide": page_raw(
            title="Complete Football Betting Guide", text=guide
        ),
        f"{SITE_B}/": page_raw(
            title="Beta Blog",
            text="Welcome to beta " * 30,
            links=[(f"{SITE_B}/blog/betting-basics", "Betting basics")],
        ),
        f"{SITE_B}/blog/betting-basics": page_raw(title="Betting Basics", text=basics),
    }


async def test_uc2_e2e_article_compare_on_mocks(tmp_path):
    """UC-2: 2 блога → content_search crawl → article в synth → compare winner."""
    settings = Settings(data_dir=REPO_ROOT / "data", runs_dir_override=tmp_path / "runs", site_cooldown_s=0.0)
    run_store = SqliteRunStore(settings.runs_dir)
    session_store = SqliteSessionStore(settings.runs_dir)
    browser_pages = _uc2_pages()

    synth_a = {
        "summary": "Alpha guide is complete",
        "facts": [],
        "article": {
            "url": f"{SITE_A}/blog/football-betting-guide",
            "title": "Complete Football Betting Guide",
            "word_count": 2400,
            "headings": ["Odds", "FAQ"],
            "main_text_excerpt": "Odds formats explained with examples",
        },
        "not_found": [],
    }
    synth_b = {
        "summary": "Beta basics is short",
        "facts": [],
        "article": {
            "url": f"{SITE_B}/blog/betting-basics",
            "title": "Betting Basics",
            "word_count": 300,
            "headings": [],
            "main_text_excerpt": "Short overview of football betting",
        },
        "not_found": [],
    }
    compare_reply = {
        "narrative": "Alpha wins: 'Odds formats explained with examples', FAQ present.",
        "winner": {"url": SITE_A, "label": "127.0.0.1:9001", "reason": "FAQ + examples"},
        "rankings": [
            {"url": SITE_A, "score": 92, "summary": "full"},
            {"url": SITE_B, "score": 40, "summary": "thin"},
        ],
        "dimensions": [{"name": "depth_sections", "scores": {"127.0.0.1:9001": 9, "127.0.0.1:9002": 3}}],
    }
    llm = FakeOllama(
        [
            {"action": "navigate", "url": f"{SITE_A}/blog/football-betting-guide", "reasoning": "guide"},
            {"action": "stop", "reasoning": "article found"},
            synth_a,
            {"action": "navigate", "url": f"{SITE_B}/blog/betting-basics", "reasoning": "basics"},
            {"action": "stop", "reasoning": "article found"},
            synth_b,
            compare_reply,
        ]
    )

    def orchestrator_factory() -> CrawlOrchestrator:
        return CrawlOrchestrator(
            settings=settings,
            browser=FakeBrowserSession(browser_pages),
            navigator=Navigator(llm, settings),  # type: ignore[arg-type]
            synthesizer=Synthesizer(llm, settings),  # type: ignore[arg-type]
            llm_client=llm,  # type: ignore[arg-type]
            store=run_store,
            hints=__import__("app.navigation.path_hints", fromlist=["PathHints"]).PathHints.load(
                REPO_ROOT / "data" / "navigation"
            ),
        )

    runner = ResearchRunner(
        settings=settings,
        run_store=run_store,
        session_store=session_store,
        orchestrator_factory=orchestrator_factory,
        compare=CompareSynthesizer(llm, settings),
    )  # type: ignore[arg-type]
    session = SessionRecord(id="uc2", created_at="t")
    session_store.save(session)
    session = await runner.run_message(
        session, f"найди статью про ставки на футбол, у кого полнее: {SITE_A} {SITE_B}"
    )

    assert session.research_intent == "comparative_content"
    assert session.status == "completed"
    run_a = run_store.get(session.run_ids[0])
    assert run_a.intent == "content_search"
    assert run_a.result.article and run_a.result.article.word_count == 2400
    comparison = session.comparison_result
    assert comparison.winner and comparison.winner.start_url == SITE_A
    assert comparison.rankings[0].score == 92
    # compare-промпт получил article-блоки обоих сайтов
    compare_prompt = llm.calls[-1]["user"]
    assert "ARTICLE: Complete Football Betting Guide" in compare_prompt
    assert "ARTICLE: Betting Basics" in compare_prompt
    report = (session_store.artifacts_dir("uc2") / "comparison_report.md").read_text()
    assert "depth_sections" in report
