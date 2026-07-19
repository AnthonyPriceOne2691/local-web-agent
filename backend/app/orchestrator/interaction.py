"""Tier 1 действия на сайте (doc 25): автономный click по не-submit элементу.

Вынесено из loop.py ради ≤500 LOC (doc 18), как attended.py. Держит orchestrator
тонким: одна развилка в ACT. **I-H10 (click-safety) проверяется enforcer'ом ДО
вызова** — здесь только исполнение клика + re-observe той же страницы.
"""

from __future__ import annotations

from app.browser.base import BrowserSession
from app.orchestrator.attended import reobserve_in_place
from app.schemas.run import RunRecord
from app.schemas.snapshot import PageSnapshot


async def click_and_reobserve(
    browser: BrowserSession,
    record: RunRecord,
    *,
    index: int,
    origin: str,
    step_index: int,
    snapshots: list[PageSnapshot],
    visited: set[str],
    rate_ms: int,
) -> PageSnapshot:
    """Клик по интерактивному элементу #index, затем re-observe той же страницы
    БЕЗ goto (DOM изменился, URL — нет). Возвращает новый снапшот для PLAN."""
    try:
        await browser.click_element(index)
    except Exception as exc:  # noqa: BLE001 — неудачный клик не валит run
        record.metadata.setdefault("click_errors", []).append(f"#{index}: {str(exc)[:120]}")
    await browser.wait(rate_ms)
    return await reobserve_in_place(
        browser, record, origin=origin, step_index=step_index,
        snapshots=snapshots, visited=visited,
        note=f"Tier 1: re-observe after click #{index}",
    )
