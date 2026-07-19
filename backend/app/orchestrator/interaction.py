"""Tier 1 действия на сайте (doc 25): автономный click по не-submit элементу.

Вынесено из loop.py ради ≤500 LOC (doc 18), как attended.py. Держит orchestrator
тонким: одна развилка в ACT. **I-H10 (click-safety) проверяется enforcer'ом ДО
вызова** — здесь только исполнение клика + re-observe той же страницы.
"""

from __future__ import annotations

from app.browser.base import BrowserSession
from app.orchestrator.attended import reobserve_in_place
from app.schemas.run import RunRecord
from app.schemas.snapshot import AgentAction, PageSnapshot


async def act_on_element(
    browser: BrowserSession,
    record: RunRecord,
    action: AgentAction,
    *,
    origin: str,
    step_index: int,
    snapshots: list[PageSnapshot],
    visited: set[str],
    rate_ms: int,
) -> PageSnapshot:
    """Tier 1/2 (doc 25): click (Tier 1) или fill (Tier 2) по element_index, затем
    re-observe той же страницы БЕЗ goto (DOM изменился, URL — нет). Enforcer уже
    проверил I-H10/I-H11 до вызова. Возвращает новый снапшот для PLAN."""
    idx = action.element_index
    try:
        if action.action == "fill":
            await browser.fill_element(idx, action.value)
        else:
            await browser.click_element(idx)
    except Exception as exc:  # noqa: BLE001 — неудачное действие не валит run
        record.metadata.setdefault("action_errors", []).append(
            f"{action.action} #{idx}: {str(exc)[:120]}")
    await browser.wait(rate_ms)
    return await reobserve_in_place(
        browser, record, origin=origin, step_index=step_index,
        snapshots=snapshots, visited=visited,
        note=f"Tier: re-observe after {action.action} #{idx}",
    )
