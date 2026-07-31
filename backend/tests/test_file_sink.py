"""File-sink (doc 25 Tier 0, локальный): санитайз имени, коллизии, llm-путь runner'а."""

from __future__ import annotations

from app.config import Settings
from app.research.compare_synthesizer import CompareSynthesizer
from app.research.llm_planner import LlmPlanner
from app.research.runner import ResearchRunner
from app.schemas.extraction import Article, ExtractionResult, Fact
from app.schemas.research import SessionRecord
from app.schemas.run import RunConfig, RunRecord
from app.sinks.content import build_export_content
from app.sinks.file import _safe_name, export_to_file
from app.storage.session_store import SqliteSessionStore
from app.storage.sqlite_store import SqliteRunStore
from tests.conftest import REPO_ROOT, FakeOllama


# ------------------------------------------------------------- sink units
def test_safe_name_strips_paths_and_junk():
    assert _safe_name("../../etc/passwd", "t") == "passwd.md"
    assert _safe_name("/abs/path/report.md", "t") == "report.md"
    assert _safe_name("от чёта?*|.md", "t") == "от чёта.md"
    assert _safe_name(None, "Research: http://a") == "Research httpa.md"
    assert _safe_name("...", "...") == "export.md"  # всё вычищено → дефолт


def test_export_writes_markdown_and_dedupes(tmp_path):
    p1 = export_to_file("Заголовок", "тело", out_dir=tmp_path / "out", filename="doc")
    assert p1.read_text(encoding="utf-8") == "# Заголовок\n\nтело\n"
    p2 = export_to_file("Заголовок", "тело 2", out_dir=tmp_path / "out", filename="doc")
    assert p2.name == "doc-2.md" and p2 != p1  # коллизия → суффикс


def test_build_export_content_article_and_facts():
    art = Article(title="T", url="http://a/x", main_text_excerpt="text body")
    with_article = ExtractionResult(start_url="http://a", summary="s", article=art, facts=[])
    title, body = build_export_content(with_article)
    assert title == "T" and "http://a/x" in body and "text body" in body

    facts_only = ExtractionResult(
        start_url="http://a", summary="s", facts=[Fact(key="k", value="v", label="K")]
    )
    title, body = build_export_content(facts_only, title_override="Custom")
    assert title == "Custom" and "s" in body and "- K: v" in body


# --------------------------------------------------------- runner llm path
def _session_with_run(run_store, session_store) -> SessionRecord:
    run_store.save(
        RunRecord(
            id="run-a",
            config=RunConfig(start_url="http://a.example", task="t"),
            status="completed",
            started_at="t",
            pages_visited=2,
            result=ExtractionResult(
                start_url="http://a.example", summary="A is blue", facts=[Fact(key="k", value="v", label="K")]
            ),
        )
    )
    session = SessionRecord(id="s1", created_at="t", run_ids=["run-a"])
    session_store.save(session)
    return session


def _runner(settings, run_store, session_store, llm) -> ResearchRunner:
    return ResearchRunner(
        settings=settings,
        run_store=run_store,
        session_store=session_store,
        orchestrator_factory=lambda: None,
        compare=CompareSynthesizer(llm, settings),  # type: ignore[arg-type]
        planner=LlmPlanner(llm, settings),
    )  # type: ignore[arg-type]


async def test_runner_llm_export_file(tmp_path):
    """export_file → markdown в artifacts сессии, путь в reply, M-S1 нота."""
    settings = Settings(data_dir=REPO_ROOT / "data", runs_dir_override=tmp_path / "runs", site_cooldown_s=0.0)
    run_store = SqliteRunStore(settings.runs_dir)
    session_store = SqliteSessionStore(settings.runs_dir)
    session = _session_with_run(run_store, session_store)
    llm = FakeOllama(
        [
            {
                "plan": [{"name": "export_file", "args": {"run_id": "run-a", "filename": "итог"}}],
                "reply": "Сохраняю.",
            }
        ]
    )

    session = await _runner(settings, run_store, session_store, llm).run_message(
        session, "сохрани результат в файл"
    )
    saved = session_store.artifacts_dir("s1") / "итог.md"
    assert saved.is_file()
    text = saved.read_text(encoding="utf-8")
    assert "A is blue" in text and text.startswith("# Research: http://a.example")
    assert str(saved) in session.messages[-1].content  # путь в ответе
    assert any(  # M-S1: заметка человеческая, без run=<id>
        m.role == "tool" and "Saving the write-up to a file" in m.content for m in session.messages
    )


async def test_planner_enforces_export_file_run_id(tmp_path):
    """M-H3: чужой run_id для export_file отброшен реестровым enforce."""
    settings = Settings(data_dir=REPO_ROOT / "data", runs_dir_override=tmp_path / "runs", site_cooldown_s=0.0)
    run_store = SqliteRunStore(settings.runs_dir)
    session_store = SqliteSessionStore(settings.runs_dir)
    session = _session_with_run(run_store, session_store)
    llm = FakeOllama(
        [
            {
                "plan": [
                    {"name": "export_file", "args": {"run_id": "fake-run"}},
                    {"name": "export_file", "args": {"run_id": "run-a"}},
                ],
                "reply": "",
            }
        ]
    )
    planner = LlmPlanner(llm, settings)  # type: ignore[arg-type]

    decision = await planner.plan(session, "сохрани в файл", run_store=run_store)
    assert [(c.name, c.args.get("run_id")) for c in decision.plan] == [("export_file", "run-a")]
