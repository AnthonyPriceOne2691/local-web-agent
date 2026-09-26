"""Tier 3 на фикстурах формы заказа: английская копия ведёт себя как русская.

Английский кадр демо («агент остановился перед необратимой кнопкой») снимается на
`store_checkout_en` (8909), русский канон — `store_checkout` (8908). Копия имеет
смысл, только если защита видит её так же: I-H12 узнаёт обе кнопки как
необратимые, без человека клик отклоняется, с человеком — пауза handoff, и агент
не нажимает ничего, включая «Delete cart» после оплаты.

Элементы берутся из САМИХ html-файлов фикстур, а не переписываются в тест руками:
переименуй кнопку в безобидную («Continue») — тест покраснеет. Модели и сети нет:
навигатор скриптован, браузер фейковый.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from html.parser import HTMLParser

import pytest

from app.config import Settings
from app.contracts.context import ActionContext
from app.contracts.enforcer import ContractEnforcer
from app.contracts.rules.navigation import label_is_destructive
from app.orchestrator.attended import EventAttendedGate
from app.schemas.snapshot import AgentAction, InteractiveElement
from tests.conftest import REPO_ROOT, FakeBrowserSession, page_raw
from tests.test_orchestrator import ORIGIN, make_orchestrator, record_for

SITES = REPO_ROOT / "tests" / "fixtures" / "sites"
FIXTURES_SERVER = REPO_ROOT / "scripts" / "spike" / "fixtures_server.py"
SYNTH_MIN = {"summary": "done", "facts": [], "not_found": []}
# Задачи показа: русская — из живого exit-прогона Phase 7, английская — из DEMO.md.
TASKS = {
    "store_checkout": "оформи заказ на WX-9: имя/email/адрес, доведи до оплаты",
    "store_checkout_en": "Order the WX-9 widget: fill in name, email and address, and take it through to payment",
}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _CheckoutPage(HTMLParser):
    """Страница так, как её видит OBSERVE_JS (`observer/snapshot.py`): подпись поля —
    placeholder (или name), подпись кнопки — её текст; submit — только кнопка ВНУТРИ
    формы, кнопка вне формы — обычная JS-кнопка. Текст — видимое содержимое <main>
    (блок с display:none не читается, как и у innerText)."""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.text: list[str] = []
        self.elements: list[dict[str, str]] = []
        self._tag = ""
        self._in_main = self._in_form = False
        self._hidden_depth = 0
        self._button: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        at = {k: v or "" for k, v in attrs}
        self._tag = tag
        hides = self._hidden_depth or "display:none" in at.get("style", "").replace(" ", "")
        if hides and tag not in _VOID:  # у void-тега нет закрывающего — глубину не трогает
            self._hidden_depth += 1
        self._in_main |= tag == "main"
        self._in_form |= tag == "form"
        if tag == "input" and at.get("type") != "hidden":
            itype = at.get("type") or "text"
            label = at.get("placeholder") or at.get("name", "")
            self.elements.append(
                {"kind": itype, "input_type": itype, "label": label, "name": at.get("name", "")}
            )
        elif tag == "button":
            submit = (at.get("type") or "submit") == "submit" and self._in_form
            self._button = {"kind": "button", "input_type": "submit" if submit else "button", "label": ""}

    def handle_endtag(self, tag: str) -> None:
        if self._hidden_depth:
            self._hidden_depth -= 1
        self._in_main &= tag != "main"
        self._in_form &= tag != "form"
        if tag == "button" and self._button is not None:
            self._button["label"] = " ".join(self._button["label"].split())
            self.elements.append(self._button)
            self._button = None

    def handle_data(self, data: str) -> None:
        if self._tag == "title" and not self.title:
            self.title = data.strip()
        if self._button is not None:
            self._button["label"] += data
        if self._in_main and not self._hidden_depth and data.strip():
            self.text.append(" ".join(data.split()))


def _page(site: str) -> _CheckoutPage:
    page = _CheckoutPage()
    page.feed((SITES / site / "index.html").read_text(encoding="utf-8"))
    return page


def _site(site: str) -> FakeBrowserSession:
    page = _page(site)
    raw = page_raw(title=page.title, text=" ".join(page.text), interactive=page.elements)
    return FakeBrowserSession({f"{ORIGIN}/": raw})


def _enforcer() -> ContractEnforcer:
    return ContractEnforcer.load(Settings(data_dir=REPO_ROOT / "data").contracts_dir)


def _unattended_click(element: dict[str, str]) -> str | None:
    """constraint_id жёсткого нарушения на клике без человека (None — клик разрешён)."""
    ctx = ActionContext(
        origin=ORIGIN,
        start_url=f"{ORIGIN}/",
        current_url=f"{ORIGIN}/",
        interactive_elements=[InteractiveElement(index=0, **element)],
    )
    hard, _ = _enforcer().validate_click(AgentAction(action="click", element_index=0), ctx)
    return hard.constraint_id if hard else None


def _buttons(site: str) -> dict[str, dict[str, str]]:
    """Две кнопки формы заказа: оплата (submit в форме) и очистка корзины (вне формы)."""
    by_type = {el["input_type"]: el for el in _page(site).elements if el["kind"] == "button"}
    assert set(by_type) == {"submit", "button"}, f"{site}: ожидались кнопка оплаты и кнопка корзины"
    return {"pay": by_type["submit"], "delete": by_type["button"]}


# --- порт: английская копия не сдвигает русскую ---


def test_english_checkout_is_served_on_8909_without_moving_8908():
    """8908 держат smoke S5 и все записи живых прогонов Tier 3; 8909 назван в DEMO.md."""
    done = subprocess.run(
        [sys.executable, str(FIXTURES_SERVER), "--print"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    urls = json.loads(done.stdout)
    assert urls["store_checkout"] == "http://127.0.0.1:8908/"
    assert urls["store_checkout_en"] == "http://127.0.0.1:8909/"


# --- I-H12: те же сигналы необратимости ---


@pytest.mark.parametrize("site", sorted(TASKS))
@pytest.mark.parametrize("button", ["pay", "delete"])
def test_checkout_buttons_are_irreversible(site: str, button: str):
    """Обе кнопки узнаются словарём `destructive_signals`, без человека клик — reject."""
    el = _buttons(site)[button]
    assert label_is_destructive(el["label"], _enforcer().destructive_signals), (
        f"{site}: «{el['label']}» не узнана как необратимая — английский кадр показал бы клик агента"
    )
    assert _unattended_click(el) == "I-H12"


def test_english_copy_mirrors_the_russian_page():
    """Копия, а не другая страница: те же элементы в том же порядке, те же пометки
    необратимости, тот же номер заказа в подтверждении."""
    signals = _enforcer().destructive_signals
    ru, en = _page("store_checkout"), _page("store_checkout_en")

    def shape(page: _CheckoutPage) -> list[tuple[str, str, bool]]:
        return [
            (e["kind"], e["input_type"], label_is_destructive(e["label"], signals)) for e in page.elements
        ]

    assert shape(en) == shape(ru)
    html = (SITES / "store_checkout_en" / "index.html").read_text(encoding="utf-8")
    assert "Order received" in html and "WX9-1337" in html and "$59 charged" in html


# --- петля: пауза handoff, агент не жмёт ни оплату, ни корзину ---


@pytest.mark.parametrize("site", sorted(TASKS))
async def test_pay_button_is_handed_to_the_human(tmp_path, site: str):
    """Зеркало `test_handoff_pause_human_clicks_agent_does_not` и
    `test_after_handoff_agent_stops_acting` на реальной разметке фикстуры."""
    elements = _page(site).elements
    pay = next(i for i, e in enumerate(elements) if e["input_type"] == "submit")
    delete = next(i for i, e in enumerate(elements) if e["kind"] == "button" and i != pay)
    browser = _site(site)
    orch, store, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "click", "element_index": pay, "reasoning": "the task asks to pay"},
            {"action": "click", "element_index": delete, "reasoning": "and now clear the cart"},
            SYNTH_MIN,
        ],
    )
    resume = asyncio.Event()
    record = record_for(f"{ORIGIN}/", task=TASKS[site], attended=True)
    task = asyncio.create_task(
        orch.run(record, attended_gate=EventAttendedGate(resume, store, timeout_s=5.0))
    )
    for _ in range(300):  # ждём handoff-паузу
        if record.status == "waiting_user":
            break
        await asyncio.sleep(0.01)

    challenge = record.metadata["challenge"]
    assert challenge["kind"] == "handoff"  # жмёт человек, а не confirm_submit, где нажал бы агент
    assert elements[pay]["label"] in challenge["action"]
    resume.set()  # человек нажал кнопку сам
    await task

    assert browser.clicked_indices == []  # ни оплата, ни «удалить корзину»
    assert record.metadata.get("handoff_done")
    assert record.metadata.get("challenge") is None  # второй необратимый шаг не запрашивался
