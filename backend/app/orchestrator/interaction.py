"""Tier 1/2/3 действия на сайте (doc 25): click/fill/handoff по element_index.

Вынесено из loop.py ради ≤500 LOC (doc 18), как attended.py. Держит orchestrator
тонким: одна развилка в ACT. **I-H10/I-H11/I-H12 проверяются enforcer'ом ДО
вызова** — здесь исполнение (или handoff человеку) + re-observe той же страницы.
"""

from __future__ import annotations

import logging

from app.browser.base import BrowserSession
from app.contracts.rules.navigation import label_is_destructive
from app.orchestrator.attended import AttendedGate, reobserve_in_place
from app.schemas.run import RunRecord
from app.schemas.snapshot import AgentAction, InteractiveElement, PageSnapshot

logger = logging.getLogger(__name__)


def _is_submit(el: InteractiveElement) -> bool:
    return "submit" in (
        (getattr(el, "kind", "") or "").lower(),
        (getattr(el, "input_type", "") or "").lower(),
    )


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
    gate: AttendedGate | None = None,
    destructive_signals: tuple[str, ...] = (),
) -> PageSnapshot | None:
    """Tier 1/2/3 (doc 25): click/fill по element_index, затем re-observe без goto.

    Tier 3 (destructive-элемент, I-H12): агент НЕ кликает — handoff-пауза, кнопку
    жмёт человек сам в видимом браузере, после resume читаем исход. Tier 2
    (submit): attended-подтверждение в чате → кликает агент. `None` → человек
    не подтвердил/не завершил (сигнал остановки). Enforcer отработал до вызова.
    """
    idx = action.element_index
    if idx is None:  # контракт: сюда попадают только действия с element_index
        logger.warning("%s without element_index at %s — skipped", action.action, current.url)
        return current
    els = current.interactive_elements
    el = els[idx] if idx is not None and 0 <= idx < len(els) else None
    if (
        action.action == "click" and el is not None and label_is_destructive(el.label, destructive_signals)
    ):  # Tier 3 (I-H12)
        desc = f"«{el.label}» на {current.url}"
        if gate is None or not await gate.handoff_action(record, desc):
            return None  # человек не завершил handoff → стоп
        # человек нажал (или отказался) САМ — агент не кликает, только читает исход
        await browser.wait(rate_ms)
        return await reobserve_in_place(
            browser,
            record,
            origin=origin,
            step_index=step_index,
            snapshots=snapshots,
            visited=visited,
            note=f"Tier 3 handoff: re-observe after human action #{idx}",
        )
    if action.action == "click" and el is not None and _is_submit(el):
        desc = f"submit «{el.label or 'форма'}» на {current.url}"
        if gate is None or not await gate.confirm_action(record, desc):
            return None  # человек не подтвердил submit → стоп
    try:
        if action.action == "fill":
            await browser.fill_element(idx, action.value)
        else:
            await browser.click_element(idx)
    except Exception as exc:
        logger.warning(
            "%s on element #%s failed at %s (%s: %s)",
            action.action,
            idx,
            current.url,
            type(exc).__name__,
            str(exc)[:120],
        )
        record.metadata.setdefault("action_errors", []).append(f"{action.action} #{idx}: {str(exc)[:120]}")
    await browser.wait(rate_ms)
    return await reobserve_in_place(
        browser,
        record,
        origin=origin,
        step_index=step_index,
        snapshots=snapshots,
        visited=visited,
        note=f"Tier: re-observe after {action.action} #{idx}",
    )
