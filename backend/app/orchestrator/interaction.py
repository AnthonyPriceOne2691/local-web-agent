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


def _is_submit(el) -> bool:
    return "submit" in ((getattr(el, "kind", "") or "").lower(),
                        (getattr(el, "input_type", "") or "").lower())


async def act_on_element(
    browser: BrowserSession,
    record: RunRecord,
    action: AgentAction,
    current: PageSnapshot,
    *,
    origin: str,
    step_index: int,
    snapshots: list[PageSnapshot],
    visited: set[str],
    rate_ms: int,
    gate=None,
) -> PageSnapshot | None:
    """Tier 1/2 (doc 25): click/fill по element_index, затем re-observe без goto.

    Submit-элемент (Tier 2) требует attended-подтверждения человека: `None` →
    не подтверждено (сигнал остановки). Enforcer уже проверил I-H10/I-H11 до вызова.
    """
    idx = action.element_index
    els = current.interactive_elements
    el = els[idx] if idx is not None and 0 <= idx < len(els) else None
    if action.action == "click" and el is not None and _is_submit(el):
        desc = f"submit «{el.label or 'форма'}» на {current.url}"
        if gate is None or not await gate.confirm_action(record, desc):
            return None  # человек не подтвердил submit → стоп
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
