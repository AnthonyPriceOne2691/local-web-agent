"""Tier 3 handoff (doc 25): I-H12 destructive-click + handoff-пауза (человек жмёт сам).

Агент необратимую кнопку не нажимает никогда: unattended → reject (enforcer),
attended → пауза kind=handoff → человек кликает в видимом браузере → resume →
re-observe читает исход. Ни в одной ветке `click_element` не вызывается.
"""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.contracts.context import ActionContext
from app.contracts.enforcer import ContractEnforcer
from app.contracts.rules.navigation import click_not_destructive, label_is_destructive
from app.orchestrator.attended import EventAttendedGate
from app.schemas.snapshot import AgentAction, InteractiveElement
from tests.conftest import REPO_ROOT, FakeBrowserSession, page_raw
from tests.test_orchestrator import ORIGIN, make_orchestrator, record_for

SYNTH_MIN = {"summary": "done", "facts": [], "not_found": []}


def _enforcer() -> ContractEnforcer:
    return ContractEnforcer.load(Settings(data_dir=REPO_ROOT / "data").contracts_dir)


def _ctx(elements: list[InteractiveElement], attended: bool = False) -> ActionContext:
    return ActionContext(
        origin=ORIGIN,
        start_url=f"{ORIGIN}/",
        current_url=f"{ORIGIN}/",
        interactive_elements=elements,
        attended=attended,
    )


# --- I-H12 (enforcer) ---


def test_destructive_signals_loaded_from_contract():
    signals = _enforcer().destructive_signals
    assert "buy" in signals and "оплат" in signals  # словарь из crawl.contract.yaml


def test_click_destructive_unattended_rejected():
    els = [InteractiveElement(index=0, kind="button", input_type="submit", label="Оплатить заказ")]
    hard, _ = _enforcer().validate_click(AgentAction(action="click", element_index=0), _ctx(els))
    assert hard is not None and hard.constraint_id == "I-H12"  # не I-H10: destructive первым


def test_click_destructive_bare_button_rejected_unattended():
    """Bare button («Удалить корзину») раньше был Tier 1 safe — I-H12 закрывает."""
    els = [InteractiveElement(index=0, kind="button", label="Удалить корзину")]
    hard, _ = _enforcer().validate_click(AgentAction(action="click", element_index=0), _ctx(els))
    assert hard is not None and hard.constraint_id == "I-H12"


def test_click_destructive_attended_passes_validation():
    """Attended: enforcer пропускает — ACT свернёт клик в handoff (жмёт человек)."""
    els = [InteractiveElement(index=0, kind="button", input_type="submit", label="Buy now")]
    hard, _ = _enforcer().validate_click(
        AgentAction(action="click", element_index=0), _ctx(els, attended=True)
    )
    assert hard is None


def test_click_safe_button_not_affected():
    els = [InteractiveElement(index=0, kind="button", label="Show more")]
    hard, _ = _enforcer().validate_click(AgentAction(action="click", element_index=0), _ctx(els))
    assert hard is None


def test_fill_not_affected_by_destructive_check():
    """I-H12 — только click: fill в поле «Название заказа» валиден (текст, I-H11)."""
    els = [InteractiveElement(index=0, kind="text", input_type="text", label="Адрес заказа")]
    v = click_not_destructive(
        "I-H12",
        {"destructive_signals": ["заказ"]},
        AgentAction(action="fill", element_index=0, value="x"),
        _ctx(els),
    )
    assert v is None
    hard, _ = _enforcer().validate_fill(
        AgentAction(action="fill", element_index=0, value="ул. Пушкина"), _ctx(els)
    )
    assert hard is None


def test_label_matcher_casefold_substring():
    assert label_is_destructive("Place ORDER now", ("place order",))
    assert label_is_destructive("Оплатить", ("оплат",))
    assert not label_is_destructive("Show more", ("buy", "pay"))
    assert not label_is_destructive("", ("buy",))


# --- loop-интеграция: handoff ---


def _checkout_site() -> FakeBrowserSession:
    return FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Order",
                text="Checkout form here " * 30,
                interactive=[{"kind": "button", "input_type": "submit", "label": "Оплатить заказ"}],
            ),
        }
    )


async def test_handoff_pause_human_clicks_agent_does_not(tmp_path):
    site = _checkout_site()
    orch, store, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "click", "element_index": 0, "reasoning": "pay per task"},
            {"action": "stop", "reasoning": "done"},
            SYNTH_MIN,
        ],
    )
    resume = asyncio.Event()
    gate = EventAttendedGate(resume, store, timeout_s=5.0)
    record = record_for(f"{ORIGIN}/", task="оформи заказ и доведи до оплаты", attended=True)
    task = asyncio.create_task(orch.run(record, attended_gate=gate))
    for _ in range(300):  # ждём handoff-паузу
        if record.status == "waiting_user":
            break
        await asyncio.sleep(0.01)
    challenge = record.metadata["challenge"]
    assert challenge["kind"] == "handoff"  # не confirm_submit: жмёт человек, не агент
    assert "Оплатить заказ" in challenge["action"]
    resume.set()  # человек нажал кнопку сам и вернулся
    await task
    assert site.clicked_indices == []  # агент НЕ кликал ни до, ни после
    assert any("handoff" in (s.note or "") for s in record.steps)  # re-observe исхода


async def test_handoff_timeout_stops_without_click(tmp_path):
    site = _checkout_site()
    orch, store, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "click", "element_index": 0, "reasoning": "pay"},
            SYNTH_MIN,
        ],
    )
    gate = EventAttendedGate(asyncio.Event(), store, timeout_s=0.05)  # никто не придёт
    record = record_for(f"{ORIGIN}/", task="оплати", attended=True)
    result = await orch.run(record, attended_gate=gate)
    assert site.clicked_indices == []
    assert result.status in ("completed", "partial", "not_found", "failed")


async def test_destructive_unattended_rejected_in_loop(tmp_path):
    site = _checkout_site()
    orch, _, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "click", "element_index": 0, "reasoning": "pay"},  # I-H12 → reject
            {"action": "stop", "reasoning": "cannot"},
            SYNTH_MIN,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert site.clicked_indices == []
    ih12 = [v for s in record.steps for v in s.violations if v.constraint_id == "I-H12"]
    assert ih12 and "attended" in ih12[0].message
