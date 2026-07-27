"""Tier 1 click (doc 25): I-H10 click-safety (enforcer) + loop-интеграция.

Клик по не-submit элементу разрешён автономно; submit/password → Tier 2 (reject).
"""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.contracts.context import ActionContext
from app.contracts.enforcer import ContractEnforcer
from app.contracts.rules.navigation import click_target_safe
from app.orchestrator.attended import EventAttendedGate
from app.schemas.snapshot import AgentAction, InteractiveElement
from tests.conftest import REPO_ROOT, FakeBrowserSession, page_raw
from tests.test_orchestrator import ORIGIN, make_orchestrator, record_for

SYNTH_MIN = {"summary": "read the page", "facts": [], "not_found": []}


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


# --- schema ---


def test_agent_action_click_schema():
    a = AgentAction.model_validate({"action": "click", "element_index": 3, "reasoning": "expand"})
    assert a.action == "click" and a.element_index == 3


# --- I-H10 click-safety (enforcer) ---


def test_click_safe_button_passes():
    els = [InteractiveElement(index=0, kind="button", label="Show more")]
    hard, _ = _enforcer().validate_click(AgentAction(action="click", element_index=0), _ctx(els))
    assert hard is None


def test_click_submit_blocked_as_tier2():
    els = [InteractiveElement(index=0, kind="submit", label="Send", input_type="submit")]
    hard, _ = _enforcer().validate_click(AgentAction(action="click", element_index=0), _ctx(els))
    assert hard is not None and hard.constraint_id == "I-H10"


def test_click_password_blocked():
    els = [InteractiveElement(index=0, kind="password", input_type="password")]
    hard, _ = _enforcer().validate_click(AgentAction(action="click", element_index=0), _ctx(els))
    assert hard is not None and hard.constraint_id == "I-H10"


def test_click_index_out_of_range_blocked():
    hard, _ = _enforcer().validate_click(AgentAction(action="click", element_index=7), _ctx([]))
    assert hard is not None and "out of range" in hard.message


def test_navigate_not_affected_by_click_check():
    v = click_target_safe("I-H10", {}, AgentAction(action="navigate", url=f"{ORIGIN}/x"), _ctx([]))
    assert v is None


# --- loop integration ---


async def test_click_executes_and_reobserves(tmp_path):
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Article",
                text="Intro paragraph " * 40,
                interactive=[{"kind": "button", "label": "Show more"}],
            ),
        }
    )
    orch, _, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "click", "element_index": 0, "reasoning": "reveal hidden content"},
            {"action": "stop", "reasoning": "done"},
            SYNTH_MIN,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/", task="read the article"))
    assert site.clicked_indices == [0]  # клик выполнен
    assert any(s.action == "click" for s in record.steps)


async def test_click_on_submit_rejected_then_replan(tmp_path):
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Form",
                text="Contact form here " * 30,
                interactive=[{"kind": "submit", "label": "Send", "input_type": "submit"}],
            ),
        }
    )
    orch, _, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "click", "element_index": 0, "reasoning": "submit form"},  # I-H10 → reject
            {"action": "stop", "reasoning": "cannot proceed"},
            SYNTH_MIN,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert site.clicked_indices == []  # клик заблокирован enforcer'ом до Playwright
    ih10 = [v for s in record.steps for v in s.violations if v.constraint_id == "I-H10"]
    assert ih10  # violation зафиксирован


# --- I-H11 fill-safety (Tier 2) ---


def test_fill_text_field_passes():
    els = [InteractiveElement(index=0, kind="text", input_type="text", label="Search")]
    hard, _ = _enforcer().validate_fill(AgentAction(action="fill", element_index=0, value="hi"), _ctx(els))
    assert hard is None


def test_fill_password_blocked():
    els = [InteractiveElement(index=0, kind="password", input_type="password")]
    hard, _ = _enforcer().validate_fill(
        AgentAction(action="fill", element_index=0, value="secret"), _ctx(els)
    )
    assert hard is not None and hard.constraint_id == "I-H11"  # креды вводит человек


def test_fill_non_text_blocked():
    els = [InteractiveElement(index=0, kind="button", label="Send")]
    hard, _ = _enforcer().validate_fill(AgentAction(action="fill", element_index=0, value="x"), _ctx(els))
    assert hard is not None and hard.constraint_id == "I-H11"


async def test_fill_executes(tmp_path):
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Search",
                text="Search page here " * 30,
                interactive=[{"kind": "text", "input_type": "text", "label": "q"}],
            ),
        }
    )
    orch, _, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "fill", "element_index": 0, "value": "football", "reasoning": "type query"},
            {"action": "stop", "reasoning": "done"},
            SYNTH_MIN,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/", task="search the site"))
    assert site.filled == [(0, "football")]  # fill выполнен
    assert any(s.action == "fill" for s in record.steps)


async def test_fill_password_rejected_in_loop(tmp_path):
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Login",
                text="Login page here " * 30,
                interactive=[{"kind": "password", "input_type": "password"}],
            ),
        }
    )
    orch, _, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "fill", "element_index": 0, "value": "secret", "reasoning": "type password"},
            {"action": "stop", "reasoning": "cannot"},
            SYNTH_MIN,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert site.filled == []  # enforcer заблокировал fill в password (I-H11)
    assert [v for s in record.steps for v in s.violations if v.constraint_id == "I-H11"]


# --- Tier 2 submit под attended-подтверждением ---


def test_click_submit_allowed_when_attended():
    els = [InteractiveElement(index=0, kind="button", input_type="submit", label="Search")]
    hard, _ = _enforcer().validate_click(
        AgentAction(action="click", element_index=0), _ctx(els, attended=True)
    )
    assert hard is None  # submit разрешён enforcer'ом (подтверждение — в ACT)


def test_click_submit_blocked_without_attended():
    els = [InteractiveElement(index=0, kind="button", input_type="submit", label="Search")]
    hard, _ = _enforcer().validate_click(
        AgentAction(action="click", element_index=0), _ctx(els, attended=False)
    )
    assert hard is not None and hard.constraint_id == "I-H10"


def _submit_site():
    return FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Form",
                text="Search form here " * 30,
                interactive=[{"kind": "button", "input_type": "submit", "label": "Search"}],
            ),
        }
    )


async def test_submit_confirmed_executes(tmp_path):
    site = _submit_site()
    orch, store, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "click", "element_index": 0, "reasoning": "submit search"},
            {"action": "stop", "reasoning": "done"},
            SYNTH_MIN,
        ],
    )
    resume = asyncio.Event()
    gate = EventAttendedGate(resume, store, timeout_s=5.0)
    record = record_for(f"{ORIGIN}/", task="search", attended=True)
    task = asyncio.create_task(orch.run(record, attended_gate=gate))
    for _ in range(300):  # ждём паузу на подтверждение
        if record.status == "waiting_user":
            break
        await asyncio.sleep(0.01)
    assert record.metadata["challenge"]["kind"] == "confirm_submit"
    resume.set()  # человек подтвердил
    await task
    assert site.clicked_indices == [0]  # submit выполнен ПОСЛЕ подтверждения


async def test_submit_declined_stops(tmp_path):
    site = _submit_site()
    orch, store, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "click", "element_index": 0, "reasoning": "submit"},
            SYNTH_MIN,
        ],
    )
    resume = asyncio.Event()  # никто не подтвердит
    gate = EventAttendedGate(resume, store, timeout_s=0.05)
    record = record_for(f"{ORIGIN}/", task="search", attended=True)
    result = await orch.run(record, attended_gate=gate)
    assert site.clicked_indices == []  # без подтверждения submit НЕ выполнен
    assert result.status in ("completed", "partial", "not_found", "failed")
