"""Tier 1/2/3 действия на сайте (doc 25): click/fill/handoff по element_index.

Вынесено из loop.py ради ≤500 LOC (doc 18), как attended.py. Держит orchestrator
тонким: одна развилка в ACT. **I-H10/I-H11/I-H12 проверяются enforcer'ом ДО
вызова** — здесь исполнение (или handoff человеку) + re-observe той же страницы.
"""

from __future__ import annotations

import logging
from typing import Any

from app.browser.base import BrowserSession
from app.contracts.rules.navigation import label_is_destructive
from app.orchestrator.attended import AttendedGate, StepCapture, page_probe, reobserve_in_place
from app.schemas.run import RunRecord
from app.schemas.snapshot import AgentAction, InteractiveElement, PageSnapshot

logger = logging.getLogger(__name__)

# Пауза после DOM-действия — только чтобы страница успела перерисоваться. Раньше
# здесь стоял rate_limit_ms (вежливость к СЕРВЕРУ), но click/fill запросов не
# делают, и каждое поле стоило лишнюю секунду.
DOM_SETTLE_MS = 250

# Анти-залипание на элементе. fill тем же значением второй раз бессмыслен (живой
# прогон Tier 3: три fill в одно поле), а click по одному элементу законно
# повторяется — «показать ещё», пагинация.
REPEAT_LIMITS = {"fill": 1, "fill_form": 1, "click": 3}


def action_signature(action: AgentAction) -> tuple[Any, ...]:
    """Идентичность действия для анти-залипания: что и по каким целям делаем."""
    if action.action == "fill_form":
        return ("fill_form", tuple((f.element_index, f.value) for f in action.fields))
    return (action.action, action.element_index, action.value or "")


def repeats_too_often(record: RunRecord, repeats: dict[tuple[Any, ...], int], action: AgentAction) -> bool:
    """Повтор того же действия по тем же целям исчерпал лимит → ACT останавливается.

    Живёт рядом с `REPEAT_LIMITS` и `action_signature`, а не в машине состояний: лимиты
    и признак повтора — одна тема, и разнесёнными они уже расходились.
    """
    signature = action_signature(action)
    repeats[signature] = repeats.get(signature, 0) + 1
    if repeats[signature] <= REPEAT_LIMITS.get(action.action, 2):
        return False
    record.metadata["action_loop_guard"] = f"{action.action} повторён {repeats[signature]}× — остановка ACT"
    return True


async def _fill_form(
    browser: BrowserSession,
    record: RunRecord,
    action: AgentAction,
    current: PageSnapshot,
    *,
    origin: str,
    step_index: int,
    snapshots: list[PageSnapshot],
    visited: set[str],
    capture: StepCapture | None = None,
) -> PageSnapshot | None:
    """Заполнить все поля формы за один шаг и один раз перечитать страницу.

    Пополевой `fill` стоил вызова nav-модели на каждое поле (живой прогон Tier 3:
    7.5 + 3.8 + 3.6 s на три поля) — здесь LLM решает один раз. I-H11 проверил
    каждое поле пачки ДО вызова; сбой одного поля не отменяет остальные.
    """
    for field in action.fields:
        try:
            await browser.fill_element(field.element_index, field.value)
        except Exception as exc:
            logger.warning(
                "fill_form field #%s failed at %s (%s: %s)",
                field.element_index,
                current.url,
                type(exc).__name__,
                str(exc)[:120],
            )
            record.metadata.setdefault("action_errors", []).append(
                f"fill_form #{field.element_index}: {str(exc)[:120]}"
            )
    await browser.wait(DOM_SETTLE_MS)
    return await reobserve_in_place(
        browser,
        record,
        origin=origin,
        step_index=step_index,
        snapshots=snapshots,
        visited=visited,
        note=f"Tier 2: re-observe after fill_form ({len(action.fields)} field(s))",
        capture=capture,
    )


async def _handoff_to_human(
    browser: BrowserSession,
    record: RunRecord,
    el: InteractiveElement,
    current: PageSnapshot,
    *,
    origin: str,
    step_index: int,
    snapshots: list[PageSnapshot],
    visited: set[str],
    gate: AttendedGate | None,
    capture: StepCapture | None = None,
) -> PageSnapshot | None:
    """Tier 3 (I-H12): агент кнопку не жмёт — пауза, жмёт человек, читаем исход.

    `None` = продолжать нельзя: человек не завершил шаг либо закрыл окно.
    """
    desc = f"«{el.label}» на {current.url}"
    if gate is not None:
        # Окно человеку показываем ДО паузы: до этого прогон мог идти headless
        # (doc 24 § Видимость окна). После не прячем — человек работает со страницей.
        await browser.reveal()
    if gate is None or not await gate.handoff_action(record, desc, page_probe(browser)):
        return None  # человек не завершил handoff → стоп
    # Окно к этому моменту могло быть закрыто (человек передумал и закрыл его —
    # нормальный поступок): тогда run заканчивается со внятной пометкой, а не
    # падает TargetClosedError'ом из середины ACT.
    try:
        await browser.wait(DOM_SETTLE_MS)
        record.metadata["handoff_done"] = desc  # больше необратимых шагов не делаем
        return await reobserve_in_place(
            browser,
            record,
            origin=origin,
            step_index=step_index,
            snapshots=snapshots,
            visited=visited,
            note=f"Tier 3 handoff: re-observe after human action #{el.index}",
            capture=capture,
        )
    except Exception as exc:
        logger.warning(
            "handoff: страница недоступна после resume (%s: %s)",
            type(exc).__name__,
            str(exc)[:120],
        )
        record.metadata["handoff_result"] = "browser closed before result was read"
        return None


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
    gate: AttendedGate | None = None,
    destructive_signals: tuple[str, ...] = (),
    capture: StepCapture | None = None,
) -> PageSnapshot | None:
    """Tier 1/2/3 (doc 25): click/fill по element_index, затем re-observe без goto.

    Tier 3 (destructive-элемент, I-H12): агент НЕ кликает — handoff-пауза, кнопку
    жмёт человек сам в видимом браузере, после resume читаем исход. Tier 2
    (submit): attended-подтверждение в чате → кликает агент. `None` → человек
    не подтвердил/не завершил (сигнал остановки). Enforcer отработал до вызова.
    """
    if action.action == "fill_form":  # Tier 2: вся форма за одно решение LLM
        return await _fill_form(
            browser,
            record,
            action,
            current,
            origin=origin,
            step_index=step_index,
            snapshots=snapshots,
            visited=visited,
            capture=capture,
        )
    idx = action.element_index
    if idx is None:  # контракт: сюда попадают только действия с element_index
        logger.warning("%s without element_index at %s — skipped", action.action, current.url)
        return current
    els = current.interactive_elements
    el = els[idx] if idx is not None and 0 <= idx < len(els) else None
    if (
        action.action == "click" and el is not None and label_is_destructive(el.label, destructive_signals)
    ):  # Tier 3 (I-H12)
        return await _handoff_to_human(
            browser,
            record,
            el,
            current,
            origin=origin,
            step_index=step_index,
            snapshots=snapshots,
            visited=visited,
            gate=gate,
            capture=capture,
        )
    if action.action == "click" and el is not None and _is_submit(el):
        desc = f"submit «{el.label or 'форма'}» на {current.url}"
        if gate is not None:
            await browser.reveal()  # человек должен видеть, что подтверждает
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
    await browser.wait(DOM_SETTLE_MS)
    return await reobserve_in_place(
        browser,
        record,
        origin=origin,
        step_index=step_index,
        snapshots=snapshots,
        visited=visited,
        note=f"Tier: re-observe after {action.action} #{idx}",
        capture=capture,
    )
