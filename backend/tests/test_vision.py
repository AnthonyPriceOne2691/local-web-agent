"""Vision batch (doc 23): loader shield V-H1/H2/H3, selection R0–R3, analyzer, E2E merge."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.schemas.snapshot import PageSnapshot, ScreenshotRef
from app.vision.loader import VisionLoader, VisionLoadError
from app.vision.selection import select_vision_jobs, vision_wanted
from tests.conftest import REPO_ROOT, FakeBrowserSession, FakeOllama, page_raw

ORIGIN = "http://127.0.0.1:8901"


def _shot(profile: str = "desktop", rel: str = "screenshots/001_desktop.png") -> ScreenshotRef:
    return ScreenshotRef(profile=profile, relative_path=rel, width=1440, height=900)


def _snap(url: str, text: str = "x" * 500, *, shots: list[ScreenshotRef] | None = None,
          priority: bool = False) -> PageSnapshot:
    return PageSnapshot(url=url, main_text=text, screenshots=shots or [], priority=priority)


# ------------------------------------------------------------------- loader
def test_loader_shield(tmp_path):
    root = tmp_path / "artifacts"
    png = root / "run1" / "screenshots" / "001_desktop.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(b"PNG" * 10)
    loader = VisionLoader.load(root, REPO_ROOT / "data" / "contracts")
    allow = {"screenshots/001_desktop.png"}

    assert loader.read_base64("run1", "screenshots/001_desktop.png", allowlist=allow)
    with pytest.raises(VisionLoadError, match="path_not_in_snapshot"):  # V-H1
        loader.read_base64("run1", "screenshots/other.png", allowlist=allow)
    with pytest.raises(VisionLoadError, match="path_traversal"):  # V-H2
        loader.read_base64("run1", "../../../etc/passwd",
                           allowlist={"../../../etc/passwd"})
    big = root / "run1" / "screenshots" / "big.png"
    big.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    with pytest.raises(VisionLoadError, match="file_too_large"):  # V-H3
        loader.read_base64("run1", "screenshots/big.png",
                           allowlist={"screenshots/big.png"})
    with pytest.raises(VisionLoadError, match="file_missing"):
        loader.read_base64("run1", "screenshots/gone.png",
                           allowlist={"screenshots/gone.png"})


# ---------------------------------------------------------------- selection
def test_vision_wanted_auto_triggers():
    shots = [_shot()]
    spa = [_snap("u1", text="tiny", shots=shots)]
    rich = [_snap("u1", shots=shots)]
    assert vision_wanted("never", "design_audit", "any", spa) is False
    assert vision_wanted("auto", "design_audit", "audit design", rich) is True
    assert vision_wanted("auto", "pricing", "find price", spa) is True  # empty DOM
    assert vision_wanted("auto", "pricing", "find price", rich) is False  # rich DOM skip
    assert vision_wanted("auto", "pricing", "what does the layout look like", rich) is True
    assert vision_wanted("always", "pricing", "find price", []) is False  # нет скриншотов


def test_selection_key_pages_and_caps():
    home = _snap(f"{ORIGIN}/", shots=[_shot()], priority=False)
    spa = _snap(f"{ORIGIN}/spa", text="tiny",
                shots=[_shot(rel="screenshots/002_desktop.png"),
                       _shot("mobile", "screenshots/002_mobile.png")])
    prio = _snap(f"{ORIGIN}/pricing", shots=[_shot(rel="screenshots/003_desktop.png"),
                                             _shot("mobile", "screenshots/003_mobile.png")],
                 priority=True)
    plain = _snap(f"{ORIGIN}/other", shots=[_shot(rel="screenshots/004_desktop.png")])

    jobs, skipped = select_vision_jobs([home, spa, prio, plain], intent="pricing", mode="auto")
    urls = [j.snapshot.url for j in jobs]
    assert urls[0] == f"{ORIGIN}/"                     # R0 homepage
    assert f"{ORIGIN}/pricing" in urls                 # R1 priority
    assert f"{ORIGIN}/spa" in urls                     # R2 empty DOM
    assert f"{ORIGIN}/other" in skipped                # не key page
    spa_profiles = [j.shot.profile for j in jobs if j.snapshot.url == f"{ORIGIN}/spa"]
    assert spa_profiles == ["desktop"]                 # R2 → desktop only
    prio_profiles = {j.shot.profile for j in jobs if j.snapshot.url == f"{ORIGIN}/pricing"}
    assert prio_profiles == {"desktop", "mobile"}      # priority → desktop+mobile

    # design_audit: все страницы со скриншотами, cap только по calls
    jobs, skipped = select_vision_jobs([home, spa, prio, plain], intent="design_audit",
                                       mode="auto", max_calls=3)
    assert len(jobs) == 3 and not skipped or len(jobs) == 3  # обрезано max_calls


# ----------------------------------------------------------------- analyzer
async def test_analyzer_parses_and_degrades(tmp_path):
    from app.vision.analyzer import VisionAnalyzer

    settings = Settings(data_dir=REPO_ROOT / "data")
    ok_json = {"profile": "desktop", "url": "x", "screen_status": "ok",
               "description": "Pricing page, blue theme",
               "extracted": [{"key": "price", "value": "$49", "confidence": "high"}],
               "design": {"layout": "3 cards"}, "confidence": "high"}
    llm = FakeOllama([ok_json, "not json at all", "still not json"])
    analyzer = VisionAnalyzer(llm, settings)  # type: ignore[arg-type]

    insight = await analyzer.analyze(image_base64="QUJD", task="price", url="u", profile="desktop")
    assert insight.status == "ok" and insight.extracted[0].value == "$49"
    assert llm.calls[0]["images"] == ["QUJD"]

    bad = await analyzer.analyze(image_base64="QUJD", task="price", url="u", profile="mobile")
    assert bad.status == "degraded" and bad.confidence == "low"


# -------------------------------------------------------- orchestrator E2E
async def test_vision_batch_merges_into_synthesis(tmp_path):
    """SPA-страница: vision достаёт цену → R1 видит vision-блок в промпте."""
    from tests.test_orchestrator import make_orchestrator, record_for

    browser = FakeBrowserSession({f"{ORIGIN}/": page_raw(title="SPA", text="tiny")})
    vision_reply = {"profile": "desktop", "url": f"{ORIGIN}/", "screen_status": "ok",
                    "description": "Price card shows $49/mo",
                    "extracted": [{"key": "price", "value": "$49/mo", "confidence": "high"}],
                    "design": {}, "confidence": "high"}
    synth_reply = {"summary": "price found visually",
                   "facts": [{"key": "price", "value": "$49/mo", "confidence": "medium",
                              "evidence": [{"url": f"{ORIGIN}/", "quote": "", "source": "vision"}]}],
                   "not_found": []}
    orch, store, llm = make_orchestrator(tmp_path, browser, [
        {"action": "stop", "reasoning": "spa, nothing to click"},
        vision_reply,
        synth_reply,
    ])
    record = await orch.run(record_for(f"{ORIGIN}/", task="Find the price"))
    assert record.metadata["vision_calls_total"] == 1
    assert record.metadata["vision_failures"] == 0
    # порядок вызовов: nav → vision (с images) → synth (без images, с VISION-блоком)
    assert "images" in llm.calls[1]
    assert "VISION (desktop)" in llm.calls[2]["user"]
    assert "$49/mo" in llm.calls[2]["user"]
    assert record.result.facts and record.result.facts[0].value == "$49/mo"
    steps_states = [s.state for s in record.steps]
    assert "VISION_BATCH" in steps_states
