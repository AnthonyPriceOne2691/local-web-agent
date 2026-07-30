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


# --- фиксы, найденные живым прогоном (2026-07-28) ---


def test_snapshot_exposes_field_value_but_never_password():
    """Агент должен видеть УЖЕ заполненные поля, иначе залипает на первом.
    Значение password не собирается никогда (I-H3/I-H11)."""
    from app.observer.snapshot import build_snapshot

    raw = page_raw(
        title="Order",
        text="checkout " * 30,
        interactive=[
            {"kind": "text", "input_type": "text", "label": "Имя", "value": "Антон"},
            {"kind": "text", "input_type": "text", "label": "Адрес", "value": ""},
            {"kind": "password", "input_type": "password", "label": "Пароль", "value": ""},
        ],
    )
    snap = build_snapshot(raw, page_url=f"{ORIGIN}/", origin=ORIGIN)
    assert snap.interactive_elements[0].value == "Антон"  # заполнено → видно агенту
    assert snap.interactive_elements[1].value == ""
    assert snap.interactive_elements[2].value == ""  # password — пусто всегда


def test_navigator_prompt_marks_filled_fields():
    from app.llm.navigator import _interactive_block
    from app.schemas.snapshot import PageSnapshot

    snap = PageSnapshot(
        url=f"{ORIGIN}/",
        interactive_elements=[
            InteractiveElement(index=0, kind="text", label="Имя", value="Антон"),
            InteractiveElement(index=1, kind="text", label="Адрес"),
        ],
    )
    block = _interactive_block(snap)
    assert 'already filled: "Антон"' in block  # модель видит, что поле готово
    assert block.splitlines()[1].endswith("Адрес")  # пустое — без пометки


async def test_repeated_fill_stops_acting(tmp_path):
    """Живой прогон: модель трижды заполняла одно поле. Страховка — loop guard."""
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Order",
                text="Checkout form here " * 30,
                interactive=[{"kind": "text", "input_type": "text", "label": "Имя"}],
            ),
        }
    )
    same_fill = {"action": "fill", "element_index": 0, "value": "Антон", "reasoning": "имя"}
    orch, _, _ = make_orchestrator(tmp_path, site, [same_fill, same_fill, same_fill, SYNTH_MIN])
    record = await orch.run(record_for(f"{ORIGIN}/", task="заполни форму"))
    assert len(site.filled) == 1  # повтор того же значения в то же поле не исполнен
    assert "повторён" in record.metadata.get("action_loop_guard", "")


# --- fill_form: вся форма за одно решение LLM (ускорение, 2026-07-28) ---


async def test_fill_form_fills_all_fields_in_one_step(tmp_path):
    """Пополевой fill стоил вызова модели на каждое поле — batch решает один раз."""
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Order",
                text="Checkout form here " * 30,
                interactive=[
                    {"kind": "text", "input_type": "text", "label": "Имя"},
                    {"kind": "text", "input_type": "email", "label": "Email"},
                    {"kind": "text", "input_type": "text", "label": "Адрес"},
                ],
            ),
        }
    )
    orch, _, llm = make_orchestrator(
        tmp_path,
        site,
        [
            {
                "action": "fill_form",
                "fields": [
                    {"element_index": 0, "value": "Антон"},
                    {"element_index": 1, "value": "a@b.c"},
                    {"element_index": 2, "value": "Москва"},
                ],
                "reasoning": "заполняю форму заказа целиком",
            },
            {"action": "stop", "reasoning": "готово"},
            SYNTH_MIN,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/", task="оформи заказ"))
    assert site.filled == [(0, "Антон"), (1, "a@b.c"), (2, "Москва")]
    # три поля — ОДИН nav-вызов (плюс второй на stop) вместо трёх
    nav_calls = [c for c in llm.calls if "INTERACTIVE ELEMENTS" in c.get("user", "")]
    assert len(nav_calls) == 2
    assert any("fill_form (3 field(s))" in (s.note or "") for s in record.steps)


async def test_fill_form_with_password_field_rejected_whole_batch(tmp_path):
    """I-H11: password нельзя протащить прицепом к валидным полям."""
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Login form",
                text="Form here " * 30,
                interactive=[
                    {"kind": "text", "input_type": "text", "label": "Логин"},
                    {"kind": "password", "input_type": "password", "label": "Пароль"},
                ],
            ),
        }
    )
    orch, _, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {
                "action": "fill_form",
                "fields": [
                    {"element_index": 0, "value": "anton"},
                    {"element_index": 1, "value": "secret"},  # password → вся пачка reject
                ],
                "reasoning": "войти",
            },
            {"action": "stop", "reasoning": "не могу"},
            SYNTH_MIN,
        ],
    )
    record = await orch.run(record_for(f"{ORIGIN}/"))
    assert site.filled == []  # ни одно поле не заполнено, включая безопасное
    assert [v for s in record.steps for v in s.violations if v.constraint_id == "I-H11"]


def test_element_tags_depend_on_mode():
    """Живой прогон: submit был помечен «do NOT click» ВСЕГДА, поэтому в attended
    агент не мог дойти до кнопки заказа и по кругу перезаполнял форму."""
    from app.llm.navigator import _interactive_block
    from app.schemas.snapshot import PageSnapshot

    snap = PageSnapshot(
        url=f"{ORIGIN}/",
        interactive_elements=[
            InteractiveElement(index=0, kind="button", input_type="submit", label="Оплатить заказ"),
            InteractiveElement(index=1, kind="password", input_type="password", label="Пароль"),
        ],
    )
    signals = _enforcer().destructive_signals

    unattended = _interactive_block(snap, attended=False, destructive=signals)
    assert "do NOT click" in unattended.splitlines()[0]  # без человека — нельзя

    attended = _interactive_block(snap, attended=True, destructive=signals)
    # Просим ВЫБРАТЬ шаг: формулировка «человек нажмёт» читалась моделью как
    # «действие не нужно», и она переставала его предлагать (живой прогон).
    assert "PICK THIS" in attended.splitlines()[0]
    assert "hands the final press to a human" in attended.splitlines()[0]
    assert "do NOT click" not in attended.splitlines()[0]
    # password human-only в обоих режимах
    assert "human-only" in attended.splitlines()[1] and "human-only" in unattended.splitlines()[1]


async def test_repeated_fill_form_stops_acting(tmp_path):
    """Повтор пачки — тоже залипание: guard покрывает fill_form, не только fill."""
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Order",
                text="Checkout form here " * 30,
                interactive=[
                    {"kind": "text", "input_type": "text", "label": "Имя"},
                    {"kind": "text", "input_type": "text", "label": "Адрес"},
                ],
            ),
        }
    )
    batch = {
        "action": "fill_form",
        "fields": [{"element_index": 0, "value": "Антон"}, {"element_index": 1, "value": "Москва"}],
        "reasoning": "форма",
    }
    orch, _, _ = make_orchestrator(tmp_path, site, [batch, batch, batch, SYNTH_MIN])
    record = await orch.run(record_for(f"{ORIGIN}/", task="оформи заказ"))
    assert site.filled == [(0, "Антон"), (1, "Москва")]  # пачка исполнена ровно раз
    assert "повторён" in record.metadata.get("action_loop_guard", "")


async def test_handoff_survives_browser_closed_by_human(tmp_path):
    """Человек может закрыть окно вместо нажатия — это не повод падать трейсбеком."""

    class ClosedAfterResume(FakeBrowserSession):
        async def wait(self, ms: int) -> None:
            raise RuntimeError("Target page, context or browser has been closed")

    site = ClosedAfterResume(
        {
            f"{ORIGIN}/": page_raw(
                title="Order",
                text="Checkout form here " * 30,
                interactive=[{"kind": "button", "input_type": "submit", "label": "Оплатить заказ"}],
            ),
        }
    )
    orch, store, _ = make_orchestrator(
        tmp_path,
        site,
        [{"action": "click", "element_index": 0, "reasoning": "pay"}, SYNTH_MIN],
    )
    resume = asyncio.Event()
    gate = EventAttendedGate(resume, store, timeout_s=5.0)
    record = record_for(f"{ORIGIN}/", task="оплати заказ", attended=True)
    task = asyncio.create_task(orch.run(record, attended_gate=gate))
    for _ in range(300):
        if record.status == "waiting_user":
            break
        await asyncio.sleep(0.01)
    resume.set()  # человек вернулся, но окно уже закрыл
    result = await task
    assert result.status != "failed"  # run завершился штатно, без краша
    assert record.metadata.get("handoff_result") == "browser closed before result was read"
    assert site.clicked_indices == []  # агент кнопку так и не нажал


async def test_after_handoff_agent_stops_acting(tmp_path):
    """Один необратимый шаг за прогон: после handoff агент фиксирует исход.

    Живой прогон: после оплаты форма исчезла, и агент потянулся к единственной
    оставшейся кнопке — «Удалить корзину». I-H12 его остановил, но лезть туда он
    вообще не должен.
    """
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Order",
                text="Заказ принят WX9-1337 " * 20,
                interactive=[
                    {"kind": "button", "input_type": "submit", "label": "Оплатить заказ"},
                    {"kind": "button", "label": "Удалить корзину"},
                ],
            ),
        }
    )
    orch, store, _ = make_orchestrator(
        tmp_path,
        site,
        [
            {"action": "click", "element_index": 0, "reasoning": "оплатить"},
            {"action": "click", "element_index": 1, "reasoning": "а теперь удалить"},
            SYNTH_MIN,
        ],
    )
    resume = asyncio.Event()
    gate = EventAttendedGate(resume, store, timeout_s=5.0)
    record = record_for(f"{ORIGIN}/", task="оформи и оплати заказ", attended=True)
    task = asyncio.create_task(orch.run(record, attended_gate=gate))
    for _ in range(300):
        if record.status == "waiting_user":
            break
        await asyncio.sleep(0.01)
    resume.set()  # человек нажал «Оплатить заказ» сам
    await task
    assert record.metadata.get("handoff_done")
    # второй destructive-клик даже не запрашивался: после handoff идём в синтез
    assert record.metadata.get("challenge") is None
    assert site.clicked_indices == []
