"""Phase 3 юниты: session store, meta-agent (URL/intent/план), compare synthesizer."""

from __future__ import annotations

from app.config import Settings
from app.research.compare_synthesizer import CompareSynthesizer, build_sites_block
from app.research.meta_agent import (
    build_plan,
    classify_research_intent,
    parse_urls,
    strip_urls,
)
from app.schemas.extraction import Article, ExtractionResult, Fact
from app.schemas.research import ComparisonResult, SessionMessage, SessionRecord
from app.storage.session_store import SqliteSessionStore
from app.storage.sqlite_store import SqliteRunStore
from tests.conftest import REPO_ROOT, FakeOllama

# ------------------------------------------------------------ session store


def test_session_store_roundtrip_sweep_delete(tmp_path):
    SqliteRunStore(tmp_path / "runs")  # создаёт схему app.db
    store = SqliteSessionStore(tmp_path / "runs")
    rec = SessionRecord(id="s1", title="compare", status="running_tools",
                        research_intent="comparative_design", run_ids=["r1", "r2"],
                        created_at="2026-07-18T00:00:00")
    rec.messages.append(SessionMessage(role="user", content="hi", created_at="t"))
    rec.comparison_result = ComparisonResult(narrative="x wins")
    store.save(rec)
    loaded = store.get("s1")
    assert loaded and loaded.run_ids == ["r1", "r2"]
    assert loaded.messages[0].content == "hi"
    assert loaded.comparison_result.narrative == "x wins"
    assert store.list_ids() == ["s1"]
    # sweep: running_tools → failed + canceled_by_restart
    assert store.startup_sweep() == 1
    swept = store.get("s1")
    assert swept.status == "failed" and swept.config.canceled_by_restart is True
    assert store.delete("s1") is True and store.get("s1") is None


def test_run_store_session_link(tmp_path):
    from app.schemas.run import RunConfig, RunRecord

    store = SqliteRunStore(tmp_path / "runs")
    for i, sid in enumerate(["sX", "sX", None]):
        store.save(RunRecord(id=f"r{i}", session_id=sid, status="completed",
                             config=RunConfig(start_url="https://x.com", task="t"),
                             started_at=f"2026-07-18T0{i}:00:00"))
    assert store.runs_for_session("sX") == ["r0", "r1"]
    assert store.get("r0").session_id == "sX"


# -------------------------------------------------------------- meta-agent


def test_parse_urls_dedupe_cap_and_strip():
    msg = ("Вот 4 сайта: https://a.com, https://b.com/x, https://a.com и "
           "https://c.com/page?q=1 — сравни дизайн.")
    urls = parse_urls(msg)
    assert urls == ["https://a.com", "https://b.com/x", "https://c.com/page?q=1"]
    assert parse_urls(msg, max_sites=2) == ["https://a.com", "https://b.com/x"]  # M-H2
    assert "https://" not in strip_urls(msg)
    assert "сравни дизайн" in strip_urls(msg)


def test_parse_urls_uncapped_returns_all():
    msg = " ".join(f"https://s{i}.com" for i in range(15))
    assert len(parse_urls(msg, max_sites=None)) == 15  # None → без cap (runner предупредит)
    assert len(parse_urls(msg)) == 10  # default cap M-H2


def test_research_intent_matrix():
    assert classify_research_intent("опиши дизайн, чем отличаются", 4) == "comparative_design"
    assert classify_research_intent("find the most complete article about betting",
                                    3) == "comparative_content"
    assert classify_research_intent("у кого статья полнее", 2) == "comparative_content"
    assert classify_research_intent("find pricing on each", 3) == "multi_site_research"
    assert classify_research_intent("anything", 1) == "single_site"


def test_build_plan_uc1_uc2():
    urls = ["https://a.com", "https://b.com"]
    plan = build_plan("comparative_design", urls, "describe design")
    assert [c.name for c in plan] == ["crawl_site", "crawl_site", "compare_results"]
    assert plan[0].args["intent"] == "design_audit" and plan[0].args["max_pages"] == 6  # UC-1
    assert plan[0].args["vision_enabled"] == "always"
    assert plan[-1].args["rubric"] == "design_diff"

    plan = build_plan("comparative_content", urls, "find betting article")
    assert plan[0].args["intent"] == "content_search" and plan[0].args["max_pages"] == 12
    assert plan[-1].args["rubric"] == "content_completeness"

    solo = build_plan("single_site", ["https://a.com"], "t")
    assert [c.name for c in solo] == ["crawl_site"]  # без compare


# ------------------------------------------------------ compare synthesizer


def _res(url: str, run_id: str, *, summary: str = "",
         article: Article | None = None) -> tuple[str, ExtractionResult]:
    return run_id, ExtractionResult(
        run_id=run_id, start_url=url, summary=summary or f"summary {url}",
        facts=[Fact(key="k", value="v")], article=article)


async def test_compare_maps_run_ids_and_drops_invented_sites():
    settings = Settings(data_dir=REPO_ROOT / "data")
    reply = {
        "narrative": "a.com полнее: «...»",
        "winner": {"url": "https://a.com", "label": "a.com", "reason": "FAQ + таблицы"},
        "rankings": [
            {"url": "https://a.com", "score": 91, "summary": "full"},
            {"url": "b.com", "score": 55, "summary": "thin"},          # по label — резолвится
            {"url": "https://evil.invented.com", "score": 99, "summary": "fake"},
        ],
        "dimensions": [{"name": "depth_sections", "scores": {"a.com": 9, "b.com": 4}}],
    }
    llm = FakeOllama([reply])
    cs = CompareSynthesizer(llm, settings)  # type: ignore[arg-type]
    inputs = [_res("https://a.com", "run-a"), _res("https://b.com", "run-b")]
    result, _ = await cs.compare(task="у кого полнее", rubric_id="content_completeness",
                                 inputs=inputs)
    assert result.status == "completed"
    assert result.winner.run_id == "run-a" and result.winner.start_url == "https://a.com"
    assert [r.run_id for r in result.rankings] == ["run-a", "run-b"]  # invented site отброшен
    assert "content_completeness" in result.rubric
    # rubric текст дошёл до промпта
    assert "depth_sections" in llm.calls[0]["user"]
    assert "ARTICLE" not in build_sites_block(inputs)  # article нет — блока нет


async def test_compare_article_block_and_invalid_json_fallback():
    settings = Settings(data_dir=REPO_ROOT / "data")
    article = Article(url="https://a.com/blog/x", title="Guide", word_count=2800,
                      headings=["Intro", "FAQ"], main_text_excerpt="betting odds " * 50)
    block = build_sites_block([_res("https://a.com", "run-a", article=article)])
    assert "ARTICLE: Guide" in block and "betting odds" in block

    llm = FakeOllama(["not json", "still not json"])
    cs = CompareSynthesizer(llm, settings)  # type: ignore[arg-type]
    result, _ = await cs.compare(task="t", rubric_id="generic_merge",
                                 inputs=[_res("https://a.com", "run-a"),
                                         _res("https://b.com", "run-b")])
    assert result.status == "failed"
    assert len(llm.calls) == 2  # 1 retry


async def test_compare_wide_ctx_for_many_sites():
    settings = Settings(data_dir=REPO_ROOT / "data")
    llm = FakeOllama([{"narrative": "ok", "rankings": [], "dimensions": []}])
    cs = CompareSynthesizer(llm, settings)  # type: ignore[arg-type]
    inputs = [_res(f"https://s{i}.com", f"run-{i}") for i in range(4)]
    await cs.compare(task="t", rubric_id="design_diff", inputs=inputs)
    assert llm.calls[0]["num_ctx"] == 24576  # N > 3 (doc 16/20)
