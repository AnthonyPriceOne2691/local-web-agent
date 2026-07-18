"""Cookie-dismiss D-11 (doc 22): detect → hide → click reject-first; статусы; 1 клик/сайт."""

from __future__ import annotations

import pytest

from app.browser.consent import ConsentHandler, _normalize_selector
from app.schemas.run import RunConfig, RunRecord
from tests.conftest import REPO_ROOT, FakeBrowserSession, page_raw

ORIGIN = "http://127.0.0.1:8901"


@pytest.fixture(scope="module")
def handler() -> ConsentHandler:
    return ConsentHandler.load(REPO_ROOT / "data" / "navigation")


def _browser(detects: list[bool], click: str | None = None) -> FakeBrowserSession:
    b = FakeBrowserSession({})
    b.consent_js_detects = detects
    b.consent_click_result = click
    return b


async def test_no_banner_means_none(handler):
    assert await handler.dismiss(_browser([False])) == "none"


async def test_hide_succeeds(handler):
    # detect=True → hide → re-detect=False
    assert await handler.dismiss(_browser([True, False])) == "hidden"


async def test_click_reject_fallback_and_accept_mode(handler):
    b = _browser([True, True], click="#onetrust-reject-all-handler")
    assert await handler.dismiss(b) == "clicked_reject"
    assert "#onetrust-reject-all-handler" in b.click_attempts[0]

    b = _browser([True, True], click="#onetrust-accept-btn-handler")
    assert await handler.dismiss(b, click_mode="accept") == "clicked_accept"


async def test_click_budget_and_modes(handler):
    # click уже использован на сайте → failed без попытки
    b = _browser([True, True], click="#x")
    assert await handler.dismiss(b, site_click_used=True) == "failed"
    assert b.click_attempts == []
    # hide_only не кликает
    b = _browser([True, True], click="#x")
    assert await handler.dismiss(b, mode="hide_only") == "failed"
    assert b.click_attempts == []
    # never — ноль работы
    b = _browser([True])
    assert await handler.dismiss(b, mode="never") == "none"


async def test_orchestrator_dismisses_before_screenshot(tmp_path):
    """Интеграция: SPA fallback скриншот → consent hide + metadata."""
    from tests.test_orchestrator import make_orchestrator

    browser = FakeBrowserSession({f"{ORIGIN}/": page_raw(title="SPA", text="tiny")})
    browser.consent_js_detects = [True, False]  # detect → hidden
    orch, _, _ = make_orchestrator(tmp_path, browser, [
        {"action": "stop", "reasoning": "done"},
        {"summary": "n/a", "facts": [], "not_found": [{"key": "x", "reason": "spa"}]},
    ])
    record = RunRecord(id="consent-run",
                       config=RunConfig(start_url=f"{ORIGIN}/", task="Find the price"))
    record = await orch.run(record)
    assert record.metadata["consent"][f"{ORIGIN}/"] == "hidden"
    assert browser.screenshots  # скриншот снят после dismissal


def test_wildcard_selector_normalized():
    assert _normalize_selector("#sp_message_container_*") == "[id^='sp_message_container_']"
    assert _normalize_selector(".fc-consent-root") == ".fc-consent-root"


def test_selectors_yaml_parses(handler):
    assert handler._hide_selectors and handler._reject and handler._accept
    assert any("onetrust" in s for s in handler._hide_selectors)
