"""LLM-планнер Phase 4 (doc 24 § Planner): контракты M-H1..M-H3, фоллбеки,
llm-путь раннера (follow-up reply / re-compare / list runs)."""

from __future__ import annotations

from app.config import Settings
from app.research.compare_synthesizer import CompareSynthesizer
from app.research.llm_planner import FALLBACK_REPLY, LlmPlanner
from app.research.runner import ResearchRunner
from app.schemas.extraction import ExtractionResult, Fact
from app.schemas.research import ComparisonResult, Ranking, SessionRecord
from app.schemas.run import RunConfig, RunRecord
from app.storage.session_store import SqliteSessionStore
from app.storage.sqlite_store import SqliteRunStore
from tests.conftest import REPO_ROOT, FakeOllama


def _settings(tmp_path) -> Settings:
    return Settings(data_dir=REPO_ROOT / "data", runs_dir_override=tmp_path / "runs",
                    site_cooldown_s=0.0)


def _stores(settings):
    return SqliteRunStore(settings.runs_dir), SqliteSessionStore(settings.runs_dir)


def _finished_run(run_id: str, url: str, summary: str) -> RunRecord:
    return RunRecord(
        id=run_id, config=RunConfig(start_url=url, task="t"), status="completed",
        started_at="t", pages_visited=2,
        result=ExtractionResult(start_url=url, summary=summary,
                                facts=[Fact(key="k", value="v", label="K")]))


def _session_with_runs(run_store, session_store) -> SessionRecord:
    run_store.save(_finished_run("run-a", "http://a.example", "A is blue"))
    run_store.save(_finished_run("run-b", "http://b.example", "B is red"))
    session = SessionRecord(id="s1", created_at="t", run_ids=["run-a", "run-b"],
                            comparison_result=ComparisonResult(
                                rubric="design_diff",
                                rankings=[Ranking(url="http://a.example", score=90)]))
    session_store.save(session)
    return session


def _runner(settings, run_store, session_store, llm) -> ResearchRunner:
    return ResearchRunner(
        settings=settings, run_store=run_store, session_store=session_store,
        orchestrator_factory=lambda: None,
        compare=CompareSynthesizer(llm, settings),  # type: ignore[arg-type]
        planner=LlmPlanner(llm, settings))  # type: ignore[arg-type]


# ----------------------------------------------------------- planner unit
async def test_planner_enforces_m_contracts(tmp_path):
    """M-H1 неизвестный tool, M-H3 чужой URL/run_id — отбрасываются."""
    settings = _settings(tmp_path)
    run_store, session_store = _stores(settings)
    session = _session_with_runs(run_store, session_store)
    llm = FakeOllama([{
        "plan": [
            {"name": "run_shell", "args": {"cmd": "rm -rf /"}},               # M-H1
            {"name": "crawl_site", "args": {"url": "http://evil.example"}},   # M-H3: не в allowed
            {"name": "get_run_result", "args": {"run_id": "fake-run"}},       # M-H3: чужой id
            {"name": "get_run_result", "args": {"run_id": "run-a"}},
            {"name": "compare_results", "args": {"run_ids": ["run-a", "fake"],
                                                 "rubric": "nonsense"}},
        ],
        "reply": "",
    }])
    planner = LlmPlanner(llm, settings)  # type: ignore[arg-type]

    decision = await planner.plan(session, "сравни ещё раз", run_store=run_store)
    names = [c.name for c in decision.plan]
    assert names == ["get_run_result", "compare_results"]
    compare = decision.plan[-1]
    assert compare.args["run_ids"] == ["run-a"]          # выдуманный id вычищен
    assert compare.args["rubric"] == "generic_merge"     # неизвестная рубрика → дефолт
    # промпт получил контекст: runs, comparison, allowed urls
    prompt = llm.calls[0]["user"]
    assert "run-a | http://a.example | completed" in prompt
    assert "http://a.example: 90" in prompt


async def test_planner_invalid_json_falls_back(tmp_path):
    settings = _settings(tmp_path)
    run_store, session_store = _stores(settings)
    session = _session_with_runs(run_store, session_store)
    planner = LlmPlanner(FakeOllama(["oops not json"]), settings)  # type: ignore[arg-type]

    decision = await planner.plan(session, "???", run_store=run_store)
    assert decision.plan == [] and decision.reply == FALLBACK_REPLY


async def test_planner_allows_urls_from_history(tmp_path):
    """crawl_site по URL из прошлых сообщений сессии (замена/повтор) — валиден."""
    settings = _settings(tmp_path)
    run_store, session_store = _stores(settings)
    session = _session_with_runs(run_store, session_store)
    from app.schemas.research import SessionMessage

    session.messages.append(SessionMessage(role="user",
                                           content="смотри http://c.example", created_at="t"))
    llm = FakeOllama([{"plan": [{"name": "crawl_site",
                                 "args": {"url": "http://c.example", "max_pages": 99}}],
                       "reply": ""}])
    planner = LlmPlanner(llm, settings)  # type: ignore[arg-type]

    decision = await planner.plan(session, "прогони его ещё раз", run_store=run_store)
    assert [c.name for c in decision.plan] == ["crawl_site"]
    assert decision.plan[0].args["max_pages"] == 12  # clamp


# ------------------------------------------------------- runner llm path
async def test_runner_reply_without_tools(tmp_path):
    """Follow-up вопрос → план пуст, ответ из reply; LLM-план один вызов."""
    settings = _settings(tmp_path)
    run_store, session_store = _stores(settings)
    session = _session_with_runs(run_store, session_store)
    llm = FakeOllama([{"plan": [], "reply": "Победил a.example: 90 баллов."}])
    runner = _runner(settings, run_store, session_store, llm)

    session = await runner.run_message(session, "кто победил и почему?")
    assert session.status == "completed"
    assert session.messages[-1].role == "assistant"
    assert "Победил a.example" in session.messages[-1].content
    assert len(llm.calls) == 1  # только планнер, без compare/crawl


async def test_runner_llm_recompare_from_store(tmp_path):
    """Re-compare прошлых runs по другой рубрике — без новых crawl'ов."""
    settings = _settings(tmp_path)
    run_store, session_store = _stores(settings)
    session = _session_with_runs(run_store, session_store)
    llm = FakeOllama([
        {"plan": [{"name": "compare_results",
                   "args": {"run_ids": ["run-a", "run-b"],
                            "comparison_task": "who is more complete",
                            "rubric": "content_completeness"}}], "reply": ""},
        {"narrative": "A fuller than B",
         "winner": {"url": "http://a.example", "label": "a", "reason": "more facts"},
         "rankings": [{"url": "http://a.example", "score": 80, "summary": "ok"},
                      {"url": "http://b.example", "score": 40, "summary": "thin"}],
         "dimensions": []},
    ])
    runner = _runner(settings, run_store, session_store, llm)

    session = await runner.run_message(session, "а теперь сравни по полноте контента")
    assert session.status == "completed"
    comparison = session.comparison_result
    assert comparison.rubric == "content_completeness"
    assert comparison.winner and comparison.winner.run_id == "run-a"
    # tool-note M-S1 нет для compare (status=comparing), но compare-промпт получил оба сайта
    compare_prompt = llm.calls[-1]["user"]
    assert "http://a.example" in compare_prompt and "http://b.example" in compare_prompt
    report = session_store.artifacts_dir("s1") / "comparison_report.md"
    assert report.is_file()


async def test_recompare_after_recrawl_drops_stale_excluded(tmp_path):
    """Re-crawl того же URL: старый failed-run не светится в excluded (UX M-H4)."""
    settings = _settings(tmp_path)
    run_store, session_store = _stores(settings)
    session = _session_with_runs(run_store, session_store)
    failed_old = RunRecord(id="run-c-old", status="failed", started_at="t",
                           config=RunConfig(start_url="http://c.example", task="t"),
                           error_message="ReadTimeout")
    run_store.save(failed_old)
    run_store.save(_finished_run("run-c-new", "http://c.example", "C is green"))
    session.run_ids += ["run-c-old", "run-c-new"]
    session_store.save(session)
    llm = FakeOllama([
        {"plan": [{"name": "compare_results",
                   "args": {"run_ids": ["run-a", "run-b", "run-c-old", "run-c-new"],
                            "rubric": "design_diff"}}], "reply": ""},
        {"narrative": "ok", "winner": None,
         "rankings": [{"url": "http://a.example", "score": 80, "summary": ""},
                      {"url": "http://b.example", "score": 60, "summary": ""},
                      {"url": "http://c.example", "score": 40, "summary": ""}],
         "dimensions": []},
    ])
    runner = _runner(settings, run_store, session_store, llm)

    session = await runner.run_message(session, "пересравни всё")
    comparison = session.comparison_result
    assert comparison.excluded == []          # старый failed перекрыт новым run'ом
    assert comparison.status == "completed"   # не partial
    assert len(comparison.rankings) == 3


async def test_runner_llm_list_runs_block(tmp_path):
    settings = _settings(tmp_path)
    run_store, session_store = _stores(settings)
    session = _session_with_runs(run_store, session_store)
    llm = FakeOllama([{"plan": [{"name": "list_session_runs", "args": {}}],
                       "reply": "Вот что уже сделано:"}])
    runner = _runner(settings, run_store, session_store, llm)

    session = await runner.run_message(session, "что уже сделано?")
    reply = session.messages[-1].content
    assert reply.startswith("Вот что уже сделано:")
    assert "run-a: http://a.example — completed" in reply
    assert session.messages[-2].role == "tool"  # M-S1 note


async def test_runner_rules_fast_path_skips_llm(tmp_path):
    """URLs в сообщении → rules-путь, планнер не вызывается (fast-path doc 24)."""
    settings = _settings(tmp_path)
    run_store, session_store = _stores(settings)
    session = SessionRecord(id="s2", created_at="t")
    session_store.save(session)
    llm = FakeOllama([])

    class BoomPlanner:
        async def plan(self, *a, **k):  # noqa: ANN002, ANN003
            raise AssertionError("planner must not be called when URLs present")

    runner = ResearchRunner(
        settings=settings, run_store=run_store, session_store=session_store,
        orchestrator_factory=lambda: _InstantOrchestrator(run_store),
        compare=CompareSynthesizer(llm, settings),  # type: ignore[arg-type]
        planner=BoomPlanner())  # type: ignore[arg-type]

    session = await runner.run_message(session, "глянь дизайн http://x.example")
    assert session.status == "completed"  # single_site: ответ из единственного result


async def test_runner_no_planner_keeps_phase3_behavior(tmp_path):
    settings = _settings(tmp_path)
    run_store, session_store = _stores(settings)
    session = SessionRecord(id="s3", created_at="t")
    session_store.save(session)
    runner = ResearchRunner(
        settings=settings, run_store=run_store, session_store=session_store,
        orchestrator_factory=lambda: None,
        compare=CompareSynthesizer(FakeOllama([]), settings))  # type: ignore[arg-type]

    session = await runner.run_message(session, "нет урлов")
    assert session.status == "failed"
    assert "no URLs" in session.messages[-1].content


class _InstantOrchestrator:
    def __init__(self, store):
        self._store = store

    async def run(self, record, cancel_event=None):
        record.status = "completed"
        record.result = ExtractionResult(summary="instant", facts=[])
        self._store.save(record)
        return record
