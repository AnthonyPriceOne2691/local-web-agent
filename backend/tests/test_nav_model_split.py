"""Маршрутизация nav-решений: лёгкая модель на DOM, тяжёлая на смысл (doc 16).

Замер 2026-07-31 показал асимметрию: `qwen3:8b` вдвое быстрее на решениях,
замкнутых на текущей странице, и в 3 прогонах из 3 хуже на выборе ссылки по
смыслу (`G-H2` + лишний хоп в 404). Тесты держат это правило и его эскалацию.
"""

from __future__ import annotations

from app.config import Settings
from app.llm.model_router import NavRouting, last_dom_action_url, pick_nav_model
from app.llm.navigator import Navigator
from app.llm.synthesizer import Synthesizer
from app.navigation.path_hints import PathHints
from app.orchestrator.loop import CrawlOrchestrator
from app.schemas.snapshot import InteractiveElement, PageSnapshot
from app.storage.sqlite_store import SqliteRunStore
from tests.conftest import REPO_ROOT, FakeBrowserSession, FakeOllama, page_raw
from tests.test_orchestrator import ORIGIN, record_for

HEAVY, LIGHT = "heavy:14b", "light:8b"
ACTION_TASK = "заполни форму заказа: имя Антон — и нажми «Оплатить заказ»"
CONTENT_TASK = "Найди статью про ставки на футбол и скажи, у кого самая полная"
SYNTH_MIN = {"summary": "ok", "facts": [], "not_found": []}


def _routing() -> NavRouting:
    return NavRouting.load(Settings(data_dir=REPO_ROOT / "data", nav_model=HEAVY, nav_light_model=LIGHT))


def _page(*, elements: list[InteractiveElement] | None = None, url: str = f"{ORIGIN}/") -> PageSnapshot:
    return PageSnapshot(url=url, title="T", main_text="text " * 30, interactive_elements=elements or [])


FORM = [
    InteractiveElement(index=0, kind="text", label="Имя", input_type="text"),
    InteractiveElement(index=1, kind="submit", label="Оплатить заказ", input_type="submit"),
]


# --- pick_nav_model: таблица решений (чистая функция) ---


def _pick(**kw) -> str:
    base = dict(
        heavy=HEAVY,
        light=LIGHT,
        task=ACTION_TASK,
        snapshot=_page(elements=FORM),
        last_dom_url=None,
        action_keywords=_routing().action_keywords,
    )
    return pick_nav_model(**{**base, **kw})


def test_action_task_on_page_with_form_goes_light():
    assert _pick() == LIGHT


def test_content_task_goes_heavy_even_with_elements():
    # Поисковая строка на блоге не делает решение локальным: выбирать всё равно ссылку.
    assert _pick(task=CONTENT_TASK) == HEAVY


def test_page_without_elements_goes_heavy():
    assert _pick(snapshot=_page()) == HEAVY


def test_disabled_elements_do_not_count_as_actionable():
    els = [InteractiveElement(index=0, kind="button", label="Оплатить", disabled=True)]
    assert _pick(snapshot=_page(elements=els)) == HEAVY


def test_mid_interaction_goes_light_even_for_content_task():
    # Уже кликали/заполняли на этой же странице → следующее решение тоже про её DOM.
    assert _pick(task=CONTENT_TASK, last_dom_url=f"{ORIGIN}/") == LIGHT


def test_dom_action_on_other_page_does_not_leak():
    assert _pick(task=CONTENT_TASK, last_dom_url=f"{ORIGIN}/other") == HEAVY


def test_replan_escalates_to_heavy():
    assert _pick(replanning=True) == HEAVY


def test_light_not_configured_keeps_heavy():
    assert _pick(light="") == HEAVY


def test_light_not_configured_ignores_replan_and_elements():
    assert _pick(light="", replanning=True, snapshot=_page()) == HEAVY


# --- last_dom_action_url: где кончается интеракция ---


def test_last_dom_action_url_finds_latest_fill():
    steps = [("OBSERVE", "", f"{ORIGIN}/"), ("ACT", "fill_form", f"{ORIGIN}/")]
    assert last_dom_action_url(steps) == f"{ORIGIN}/"


def test_navigate_resets_interaction():
    steps = [
        ("ACT", "click", f"{ORIGIN}/a"),
        ("ACT", "navigate", f"{ORIGIN}/a"),
        ("OBSERVE", "", f"{ORIGIN}/b"),
    ]
    assert last_dom_action_url(steps) is None


def test_no_dom_action_yet():
    assert last_dom_action_url([("OBSERVE", "", f"{ORIGIN}/")]) is None


# --- прогрев: греем ту модель, что будет решать первый шаг ---


def test_first_step_model_light_for_action_task():
    assert _routing().first_step_model(ACTION_TASK) == LIGHT


def test_first_step_model_heavy_for_content_task():
    assert _routing().first_step_model(CONTENT_TASK) == HEAVY


def test_first_step_model_heavy_when_light_disabled():
    routing = NavRouting.load(Settings(data_dir=REPO_ROOT / "data", nav_model=HEAVY, nav_light_model=""))
    assert routing.first_step_model(ACTION_TASK) == HEAVY


# --- интеграция в loop: какая модель реально пошла в chat() ---


def _orchestrator(tmp_path, browser, replies, *, light: str = LIGHT):
    settings = Settings(data_dir=REPO_ROOT / "data", nav_model=HEAVY, nav_light_model=light)
    llm = FakeOllama(replies)
    orch = CrawlOrchestrator(
        settings=settings,
        browser=browser,
        navigator=Navigator(llm, settings),  # type: ignore[arg-type]
        synthesizer=Synthesizer(llm, settings),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        store=SqliteRunStore(tmp_path / "runs"),
        hints=PathHints.load(REPO_ROOT / "data" / "navigation"),
    )
    return orch, llm


def _form_site() -> FakeBrowserSession:
    return FakeBrowserSession(
        {
            f"{ORIGIN}/": page_raw(
                title="Заказ",
                text="Оформление заказа " * 30,
                interactive=[
                    {"index": 0, "kind": "text", "label": "Имя", "input_type": "text"},
                    {"index": 1, "kind": "button", "label": "Показать детали"},
                ],
            )
        }
    )


def _nav_models(llm: FakeOllama) -> list[str]:
    """Модели, которыми принимались решения навигатора (без синтеза)."""
    return [c["model"] for c in llm.calls if c.get("schema") is not None]


async def test_loop_uses_light_model_for_form_task(tmp_path):
    orch, llm = _orchestrator(
        tmp_path,
        _form_site(),
        [
            {"action": "fill", "element_index": 0, "value": "Антон", "reasoning": "имя"},
            {"action": "stop", "reasoning": "готово"},
            SYNTH_MIN,
        ],
    )
    await orch.run(record_for(f"{ORIGIN}/", task=ACTION_TASK, allow_private=True))
    assert _nav_models(llm)[0] == LIGHT
    assert llm.warmed == [LIGHT]  # прогрели ту модель, что решала первый шаг


async def test_loop_escalates_to_heavy_after_hard_violation(tmp_path):
    orch, llm = _orchestrator(
        tmp_path,
        _form_site(),
        [
            # I-H11: индекса 5 в списке нет → hard violation, replan на тяжёлой
            {"action": "fill", "element_index": 5, "value": "x", "reasoning": "мимо списка"},
            {"action": "stop", "reasoning": "сдаюсь"},
            SYNTH_MIN,
        ],
    )
    await orch.run(record_for(f"{ORIGIN}/", task=ACTION_TASK, allow_private=True))
    models = _nav_models(llm)
    assert models[0] == LIGHT and models[1] == HEAVY


async def test_loop_keeps_heavy_when_light_disabled(tmp_path):
    orch, llm = _orchestrator(
        tmp_path,
        _form_site(),
        [{"action": "stop", "reasoning": "ничего не надо"}, SYNTH_MIN],
        light="",
    )
    await orch.run(record_for(f"{ORIGIN}/", task=ACTION_TASK, allow_private=True))
    assert set(_nav_models(llm)) == {HEAVY}
    assert llm.warmed == [HEAVY]


async def test_both_nav_models_unloaded_before_synthesis(tmp_path):
    orch, llm = _orchestrator(
        tmp_path,
        _form_site(),
        [{"action": "stop", "reasoning": "готово"}, SYNTH_MIN],
    )
    await orch.run(record_for(f"{ORIGIN}/", task=ACTION_TASK, allow_private=True))
    assert llm.unloaded == [HEAVY, LIGHT]  # лёгкая не держит RAM во время синтеза
