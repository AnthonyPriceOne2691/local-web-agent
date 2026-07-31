"""Видимость окна браузера: только когда без человека нельзя (doc 24 § Видимость окна).

Требование владельца после real-site прогона: «браузер не должен висеть перед
глазами без надобности». До этой поставки `attended` означал сразу две вещи —
«человек доступен» и «headless=False на весь прогон», поэтому окно висело весь
прогон, даже когда никакой проверки не появлялось (а в том прогоне её не было вовсе).
"""

from __future__ import annotations

from app.config import Settings
from app.llm.model_router import NavRouting
from tests.conftest import REPO_ROOT, FakeBrowserSession, page_raw
from tests.test_orchestrator import ORIGIN, make_orchestrator, record_for

SYNTH_MIN = {"summary": "ok", "facts": [], "not_found": []}


def _routing() -> NavRouting:
    return NavRouting.load(Settings(data_dir=REPO_ROOT / "data"))


# --- правило: ожидается ли участие человека по формулировке задачи ---


def test_action_task_expects_human():
    r = _routing()
    assert r.expects_human_action("заполни форму заказа и нажми «Оплатить»") is True
    assert r.expects_human_action("fill in the checkout form and pay") is True


def test_research_task_does_not_expect_human():
    r = _routing()
    assert r.expects_human_action("Find the getting started guide and tell me whose is fuller") is False
    assert r.expects_human_action("опиши дизайн этих сайтов") is False


# --- прогон без пауз: окно не показывается ни разу ---


async def test_quiet_run_never_shows_the_window(tmp_path):
    site = FakeBrowserSession({f"{ORIGIN}/": page_raw(title="Docs", text="Getting started " * 40)})
    orch, _store, _llm = make_orchestrator(
        tmp_path, site, [{"action": "stop", "reasoning": "enough"}, SYNTH_MIN]
    )
    await orch.run(
        record_for(f"{ORIGIN}/", task="Find the getting started guide", allow_private=True, attended=True)
    )
    # attended=True, но проверок не было → окно не нужно
    assert site.revealed == 0
    assert site.headless is True


async def test_action_task_opens_the_window_upfront(tmp_path):
    """Для задачи-действия окно нужно сразу: перезапуск потерял бы заполненную форму."""
    site = FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Order",
                text="Order form " * 40,
                interactive=[{"index": 0, "kind": "text", "label": "Имя", "input_type": "text"}],
            )
        }
    )
    orch, _store, _llm = make_orchestrator(
        tmp_path, site, [{"action": "stop", "reasoning": "done"}, SYNTH_MIN]
    )
    await orch.run(
        record_for(
            f"{ORIGIN}/",
            task="заполни форму заказа: имя Антон",
            allow_private=True,
            attended=True,
        )
    )
    assert site.headless is False


async def test_unattended_run_is_always_headless(tmp_path):
    """Без человека окно бессмысленно, даже на задаче-действии."""
    site = FakeBrowserSession({f"{ORIGIN}/": page_raw(title="Order", text="Order form " * 40)})
    orch, _store, _llm = make_orchestrator(
        tmp_path, site, [{"action": "stop", "reasoning": "done"}, SYNTH_MIN]
    )
    await orch.run(record_for(f"{ORIGIN}/", task="заполни форму заказа", allow_private=True, attended=False))
    assert site.headless is True
    assert site.revealed == 0
