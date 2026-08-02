"""Инварианты `CrawlOrchestrator.run()` — тесты ПЕРЕД разбором сложности.

`run()` — 30 ветвлений и 160 statements, и в нём сходится всё: границы отмены,
ранняя остановка, attended-паузы, тиры действий, анти-залипание, финализация. Часть
инвариантов уже покрыта (G-S1 — `test_orchestrator_edges`, attended —
`test_attended`, handoff и повторы fill — `test_tier3_handoff`); здесь закрываются
**пробелы**, чтобы разбор не мог тихо потерять ветку:

* отмена на границе OBSERVE и на границе PLAN (раньше проверялась только отмена
  перед синтезом);
* анти-залипание для `click` (для `fill`/`fill_form` тесты были, у click другой лимит);
* падение в середине прогона → `failed` с именем типа исключения и закрытым браузером;
* фиксация конца прогона: результат, длительность, отчёт.

Тесты обязаны быть зелёными **до** рефакторинга — иначе они описывают не то, что есть.
"""

from __future__ import annotations

import asyncio

from app.orchestrator.interaction import REPEAT_LIMITS
from tests.conftest import FakeBrowserSession, page_raw
from tests.test_orchestrator import ORIGIN, SYNTH_OK, make_orchestrator, record_for


class RevealingSite(FakeBrowserSession):
    """Каждый click «подгружает» новую ссылку — как настоящая кнопка «показать ещё».

    Статичная фикстура для этого не годится: без новых релевантных ссылок раньше
    срабатывает ранняя остановка G-S1 (три страницы подряд без новизны), и до
    анти-залипания дело не доходит вовсе. Это не обход проверки, а её условие:
    залипание проверяется там, где страница честно меняется.
    """

    def __init__(self) -> None:
        super().__init__(
            {
                f"{ORIGIN}/": page_raw(
                    title="Home",
                    text="Свежие статьи про оплату " * 30,
                    links=[(f"{ORIGIN}/article-0", "Как оплатить заказ")],
                    interactive=[{"kind": "button", "label": "Показать ещё"}],
                )
            }
        )
        self._revealed = 0

    async def click_element(self, index: int) -> None:
        await super().click_element(index)
        self._revealed += 1
        page = self.pages[f"{ORIGIN}/"]
        page["links"] = [
            *page["links"],
            {"href": f"{ORIGIN}/article-{self._revealed}", "text": "Как оплатить заказ"},
        ]


async def test_cancel_before_observe_stops_without_navigating(tmp_path) -> None:
    """Отмена до первого OBSERVE: браузер не ходит никуда, синтез не зовётся."""
    browser = FakeBrowserSession({f"{ORIGIN}/": page_raw(title="Home", text="words " * 60)})
    orch, store, llm = make_orchestrator(tmp_path, browser, [])
    cancel = asyncio.Event()
    cancel.set()

    record = await orch.run(record_for(f"{ORIGIN}/"), cancel_event=cancel)

    assert record.status == "canceled"
    assert record.metadata.get("canceled_by_user") is True
    assert browser.visited_log == [], "отмена на границе OBSERVE не должна пускать навигацию"
    assert llm.calls == [], "ни навигатор, ни синтезатор не зовутся после отмены"
    assert store.get(record.id).status == "canceled", "статус обязан попасть в БД"


async def test_cancel_between_observe_and_plan_skips_llm(tmp_path) -> None:
    """Отмена, выставленная после первого OBSERVE, ловится границей перед PLAN."""
    browser = FakeBrowserSession({f"{ORIGIN}/": page_raw(title="Home", text="words " * 60)})
    cancel = asyncio.Event()

    original_snapshot = browser.raw_snapshot

    async def snapshot_then_cancel():  # type: ignore[no-untyped-def]
        raw = await original_snapshot()
        cancel.set()  # человек нажал «отменить», пока страница читалась
        return raw

    browser.raw_snapshot = snapshot_then_cancel  # type: ignore[method-assign]
    orch, _, llm = make_orchestrator(tmp_path, browser, [])

    record = await orch.run(record_for(f"{ORIGIN}/"), cancel_event=cancel)

    assert record.status == "canceled"
    assert llm.calls == [], "PLAN не должен стартовать после отмены"
    assert browser.closed is True, "браузер закрывается и на отменённом прогоне"


async def test_repeated_click_stops_acting(tmp_path) -> None:
    """click законно повторяется, но выше лимита — это залипание, а не пагинация."""
    browser = RevealingSite()
    click = {"action": "click", "element_index": 0, "reasoning": "показать ещё"}
    # На один больше лимита: последний повтор обязан остановить ACT.
    replies = [click] * (REPEAT_LIMITS["click"] + 2) + [SYNTH_OK]
    orch, _, _ = make_orchestrator(tmp_path, browser, replies)

    record = await orch.run(record_for(f"{ORIGIN}/", task="покажи все статьи про оплату"))

    guard = record.metadata.get("action_loop_guard", "")
    assert "click" in guard, f"ожидался стоп по анти-залипанию, метаданные: {record.metadata}"
    assert len(browser.clicked_indices) == REPEAT_LIMITS["click"], (
        "кликов должно быть ровно по лимиту: превышение и есть сигнал залипания"
    )


async def test_crash_mid_run_fails_with_type_name_and_closes_browser(tmp_path) -> None:
    """Сбой в середине: статус failed, имя типа в сообщении (M-H4), браузер закрыт."""
    browser = FakeBrowserSession({f"{ORIGIN}/": page_raw(title="Home", text="words " * 60)})

    async def boom():  # type: ignore[no-untyped-def]
        raise TimeoutError()  # str(TimeoutError()) пуст — сообщение обязано остаться читаемым

    browser.raw_snapshot = boom  # type: ignore[method-assign]
    orch, store, _ = make_orchestrator(tmp_path, browser, [])

    record = await orch.run(record_for(f"{ORIGIN}/"))

    assert record.status == "failed"
    assert record.error_message == "TimeoutError"
    assert record.finished_at is not None
    assert browser.closed is True
    assert store.get(record.id).status == "failed"


async def test_finalize_fills_result_and_writes_report(tmp_path) -> None:
    """Конец прогона: результат заполнен из записи, отчёт лежит в артефактах."""
    browser = FakeBrowserSession({f"{ORIGIN}/contact": page_raw(title="Contact", text="Call +1 555 " * 40)})
    orch, store, _ = make_orchestrator(
        tmp_path, browser, [{"action": "stop", "reasoning": "хватит"}, SYNTH_OK]
    )

    record = await orch.run(record_for(f"{ORIGIN}/contact"))

    assert record.status == "completed"
    assert record.result is not None
    assert record.result.run_id == record.id
    assert record.result.start_url == f"{ORIGIN}/contact"
    assert record.result.pages_visited == 1
    assert record.result.duration_seconds >= 0
    assert record.metadata.get("violations_total") == 0
    report = store.artifacts_dir(record.id) / "report.md"
    assert report.is_file() and report.read_text(encoding="utf-8").strip()
