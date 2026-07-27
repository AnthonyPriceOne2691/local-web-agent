"""Markdown report (doc 05): Findings/Design/Not found/Appendix; blocked-ветка."""

from __future__ import annotations

from app.reporting.markdown import build_report
from app.schemas.extraction import Evidence, ExtractionResult, Fact, NotFound
from app.schemas.run import RunConfig, RunRecord
from app.schemas.snapshot import PageSnapshot, ScreenshotRef

URL = "https://x.com/"


def _record(**meta) -> RunRecord:
    rec = RunRecord(
        id="r1", config=RunConfig(start_url=URL, task="Find the price"), status="completed", pages_visited=2
    )
    rec.metadata.update(meta)
    return rec


def test_full_report_sections():
    rec = _record(
        vision_calls_total=2,
        vision_pages_analyzed=1,
        vision_failures=1,
        vision_skipped_pages=["https://x.com/blog"],
    )
    rec.result = ExtractionResult(
        status="completed",
        summary="Price found.",
        facts=[
            Fact(
                key="price",
                label="Price",
                value="$49/mo",
                confidence="high",
                evidence=[
                    Evidence(url=URL, quote="only $49/mo"),
                    Evidence(url=URL, quote="", source="vision"),
                ],
            )
        ],
        not_found=[NotFound(key="phone", reason="absent")],
    )
    snap = PageSnapshot(
        url=URL,
        main_text="x",
        screenshots=[
            ScreenshotRef(profile="desktop", relative_path="screenshots/001.png", width=1440, height=900)
        ],
        vision_insights=[
            {
                "status": "ok",
                "profile": "desktop",
                "description": "Blue pricing card with $49/mo",
                "design": {"colors_approx": ["#2563eb"], "layout": "3 cards"},
            },
            {"status": "failed", "profile": "mobile", "error": "timeout"},
        ],
    )
    report = build_report(rec, [snap])
    assert "# Crawl Report: Find the price" in report
    assert "**Vision:** 1 pages/2 calls" in report
    assert "### Price (high) · source: both" in report
    assert '> "only $49/mo"' in report
    assert "_Vision (desktop): Blue pricing card" in report
    assert "## Design analysis" in report and "#2563eb" in report
    assert "![desktop](screenshots/001.png)" in report
    assert "- phone: absent" in report
    assert "## Appendix: vision diagnostics" in report
    assert "| https://x.com/blog | — | skipped | page cap |" in report


def test_blocked_report_short():
    rec = _record(blocked_by="captcha")
    rec.status = "blocked"
    rec.result = None
    report = build_report(rec, [])
    assert "Run ended without findings: captcha" in report
    assert "## Findings" not in report


def test_plain_dom_report_omits_design_and_appendix():
    rec = _record()
    rec.result = ExtractionResult(
        status="completed",
        summary="ok",
        facts=[Fact(key="k", value="v", confidence="medium", evidence=[Evidence(url=URL, quote="v here")])],
    )
    report = build_report(rec, [PageSnapshot(url=URL, main_text="v here")])
    assert "## Design analysis" not in report
    assert "Appendix" not in report
