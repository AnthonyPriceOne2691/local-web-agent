"""Action registry (doc 25): A-H1 membership, A-H2 tier-гейт, prompt_block."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.research import actions
from app.research.actions import registry as registry_mod
from app.research.actions.base import ActionSpec
from app.research.compare_synthesizer import CompareSynthesizer
from app.research.llm_planner import LlmPlanner
from app.research.runner import ResearchRunner
from app.schemas.extraction import ExtractionResult, Fact
from app.schemas.research import SessionRecord
from app.schemas.run import RunConfig, RunRecord
from app.storage.session_store import SqliteSessionStore
from app.storage.sqlite_store import SqliteRunStore
from tests.conftest import REPO_ROOT, FakeOllama

CANONICAL = {"crawl_site", "get_run_result", "list_session_runs",
             "compare_results", "export_gdocs", "export_file"}


def _settings(tmp_path) -> Settings:
    return Settings(data_dir=REPO_ROOT / "data", runs_dir_override=tmp_path / "runs",
                    site_cooldown_s=0.0)


def _session_with_run(run_store, session_store) -> SessionRecord:
    run_store.save(RunRecord(
        id="run-a", config=RunConfig(start_url="http://a.example", task="t"),
        status="completed", started_at="t", pages_visited=2,
        result=ExtractionResult(start_url="http://a.example", summary="A is blue",
                                facts=[Fact(key="k", value="v", label="K")])))
    session = SessionRecord(id="s1", created_at="t", run_ids=["run-a"])
    session_store.save(session)
    return session


def _runner(settings, run_store, session_store, llm) -> ResearchRunner:
    return ResearchRunner(
        settings=settings, run_store=run_store, session_store=session_store,
        orchestrator_factory=lambda: None,
        compare=CompareSynthesizer(llm, settings),  # type: ignore[arg-type]
        planner=LlmPlanner(llm, settings))  # type: ignore[arg-type]


def test_registry_contains_all_layer2_actions():
    assert set(actions.names()) == CANONICAL
    for name in CANONICAL:
        spec = actions.get(name)
        assert spec is not None and spec.name == name
    # structural (поток ведёт runner) vs reply-block (execute в реестре)
    assert actions.get("crawl_site").structural and actions.get("crawl_site").execute is None
    assert actions.get("compare_results").structural
    assert actions.get("export_gdocs").cloud  # A-H4: облако помечено
    assert not actions.get("export_file").cloud  # локальный sink — без consent


def test_register_duplicate_name_fails():
    with pytest.raises(ValueError, match="already registered"):
        actions.register(ActionSpec(name="crawl_site", tier=1, reversible=True))


def test_prompt_block_covers_every_registered_action():
    """Fail fast: у каждого действия есть описание в data/prompts/tools/."""
    block = actions.prompt_block(REPO_ROOT / "data" / "prompts")
    for name in actions.names():
        assert f'"{name}"' in block


def test_planner_system_prompt_includes_registry_tools(tmp_path):
    """Системный meta-промпт собирается из реестра ({TOOLS_BLOCK})."""
    planner = LlmPlanner(FakeOllama([]), _settings(tmp_path))  # type: ignore[arg-type]
    for name in actions.names():
        assert f'"{name}"' in planner._system
    assert "{TOOLS_BLOCK}" not in planner._system


async def test_tier2_action_skipped_without_confirmation(tmp_path, monkeypatch):
    """A-H2/A-H3: действие tier ≥ 2 runner не исполняет — нота вместо execute."""
    executed: list[str] = []

    def _boom(call, ctx):  # noqa: ARG001
        executed.append(call.name)
        return "boom"

    settings = _settings(tmp_path)
    run_store = SqliteRunStore(settings.runs_dir)
    session_store = SqliteSessionStore(settings.runs_dir)
    session = _session_with_run(run_store, session_store)
    llm = FakeOllama([{"plan": [{"name": "dangerous_submit", "args": {}}],
                       "reply": "ok"}])
    runner = _runner(settings, run_store, session_store, llm)  # planner до регистрации
    monkeypatch.setitem(
        registry_mod._REGISTRY, "dangerous_submit",
        ActionSpec(name="dangerous_submit", tier=2, reversible=False, execute=_boom))

    session = await runner.run_message(session, "сделай опасное")
    assert executed == []  # A-H2: не исполнено
    assert any(m.role == "tool" and "требует подтверждения" in m.content
               for m in session.messages)
    assert session.status == "completed"  # сессия не падает


def test_get_run_result_execute_details(tmp_path):
    """Execute-хук get_run_result: summary + факты + article-строка."""
    from app.research.meta_agent import ToolCall
    from app.schemas.extraction import Article

    settings = _settings(tmp_path)
    run_store = SqliteRunStore(settings.runs_dir)
    session_store = SqliteSessionStore(settings.runs_dir)
    session = _session_with_run(run_store, session_store)
    r = run_store.get("run-a")
    r.result.article = Article(url="http://a.example/post", title="Post", word_count=7)
    run_store.save(r)
    ctx = actions.ActionContext(session=session, run_store=run_store, settings=settings)

    spec = actions.get("get_run_result")
    text = spec.execute(ToolCall(name="get_run_result", args={"run_id": "run-a"}), ctx)
    assert "http://a.example (completed): A is blue" in text
    assert "- K: v" in text and "article: Post (7 words)" in text
    missing = spec.execute(ToolCall(name="get_run_result", args={"run_id": "zzz"}), ctx)
    assert missing == "zzz: no result available"


async def test_unknown_action_dropped_by_planner(tmp_path):
    """A-H1/M-H1: незарегистрированное имя не доходит до исполнения."""
    settings = _settings(tmp_path)
    run_store = SqliteRunStore(settings.runs_dir)
    session_store = SqliteSessionStore(settings.runs_dir)
    session = _session_with_run(run_store, session_store)
    llm = FakeOllama([{"plan": [{"name": "run_shell", "args": {"cmd": "rm -rf /"}}],
                       "reply": "готово"}])

    session = await _runner(settings, run_store, session_store, llm).run_message(
        session, "выполни команду")
    assert session.status == "completed"
    assert session.messages[-1].content == "готово"  # план опустел → только reply
    assert all("run_shell" not in m.content for m in session.messages if m.role == "tool")
