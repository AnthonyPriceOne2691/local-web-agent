"""Скриншот шага снимается и после интеракции, а не только на первом OBSERVE.

Находка живого прогона Tier 3: при `capture_screenshots: "always"` снимок был
сделан один раз — на входной странице. Re-observe после `fill_form`, click и после
handoff проходили без снимка, хотя именно они показывают, **что человек и агент
сделали со страницей**. В Phase 7 скриншот шага был главным средством диагностики
(«видно глазами, что реально было на странице»), поэтому пробел значимый.
"""

from __future__ import annotations

from tests.conftest import FakeBrowserSession, page_raw
from tests.test_orchestrator import ORIGIN, SYNTH_OK, make_orchestrator, record_for


def form_page() -> FakeBrowserSession:
    return FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Заказ",
                text="Заполните форму и оплатите заказ " * 20,
                interactive=[
                    {"kind": "text", "input_type": "text", "label": "Имя"},
                    {"kind": "button", "label": "Показать детали"},
                ],
            )
        }
    )


async def test_screenshot_after_fill_form(tmp_path) -> None:
    browser = form_page()
    orch, _, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {
                "action": "fill_form",
                "fields": [{"element_index": 0, "value": "Антон"}],
                "reasoning": "заполняю форму",
            },
            {"action": "stop", "reasoning": "готово"},
            SYNTH_OK,
        ],
    )

    record = await orch.run(record_for(f"{ORIGIN}/", task="заполни форму", capture_screenshots="always"))

    shots = [s for s in record.steps if s.state == "OBSERVE" and s.screenshot_paths]
    notes = [s.note for s in record.steps if s.state == "OBSERVE"]
    assert len(shots) >= 2, f"после fill_form снимка нет; шаги OBSERVE: {notes}"
    assert any("fill_form" in (s.note or "") for s in shots), "снимок обязан быть у шага интеракции"
    assert len(browser.screenshots) >= 2


async def test_screenshot_after_click(tmp_path) -> None:
    browser = form_page()
    orch, _, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "click", "element_index": 1, "reasoning": "раскрываю детали"},
            {"action": "stop", "reasoning": "готово"},
            SYNTH_OK,
        ],
    )

    record = await orch.run(
        record_for(f"{ORIGIN}/", task="нажми показать детали", capture_screenshots="always")
    )

    after_click = [s for s in record.steps if "after click" in (s.note or "")]
    assert after_click, "шаг re-observe после click отсутствует"
    assert after_click[0].screenshot_paths, "у re-observe после click нет скриншота"


async def test_never_mode_still_captures_nothing(tmp_path) -> None:
    """Режим «никогда» остаётся честным: починка не должна включать съёмку тайком."""
    browser = form_page()
    orch, _, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "click", "element_index": 1, "reasoning": "раскрываю детали"},
            {"action": "stop", "reasoning": "готово"},
            SYNTH_OK,
        ],
    )

    record = await orch.run(
        record_for(f"{ORIGIN}/", task="нажми показать детали", capture_screenshots="never")
    )

    assert browser.screenshots == []
    assert all(not s.screenshot_paths for s in record.steps)
