"""Пауза Tier 3: агент замечает действие человека сам, но осторожно.

Находка живого прогона: человек нажал необратимую кнопку и ждал, а агент стоял —
он не следит за страницей, сигналом служит только resume. Требовать от человека
второе подтверждение того, что он уже сделал руками, — лишний шаг.

Осторожность здесь важнее удобства, поэтому проверяется обе стороны:
изменение засчитывается только когда держится два опроса подряд (страница дёргается
сама: дозагрузка, баннер, редирект), а явный resume по-прежнему сильнее опроса.
"""

from __future__ import annotations

import asyncio

from app.orchestrator.attended import EventAttendedGate
from app.schemas.run import RunConfig, RunRecord


class FakeStore:
    def __init__(self) -> None:
        self.saves = 0

    def save(self, record: RunRecord) -> None:  # запись не нужна — считаем вызовы
        self.saves += 1


def make_gate(resume: asyncio.Event, *, timeout_s: float = 1.0, poll_s: float = 0.01):
    return EventAttendedGate(resume, FakeStore(), timeout_s=timeout_s, poll_s=poll_s)  # type: ignore[arg-type]


def record_for() -> RunRecord:
    return RunRecord(id="r1", config=RunConfig(start_url="http://127.0.0.1:8908/", task="оплати заказ"))


def probe_of(values: list[str]):
    """Зонд, выдающий подписи по очереди; последняя повторяется дальше."""

    async def probe() -> str:
        return values.pop(0) if len(values) > 1 else values[0]

    return probe


async def test_stable_page_change_continues_without_resume() -> None:
    """Человек нажал кнопку — страница изменилась и осталась такой: продолжаем сами."""
    record = record_for()
    gate = make_gate(asyncio.Event())
    probe = probe_of(["before", "after", "after", "after"])

    ok = await gate.handoff_action(record, "«Оплатить заказ»", probe)

    assert ok is True
    assert record.metadata["handoff_resolved_by"] == "page_change"
    assert "challenge" not in record.metadata, "карточка паузы обязана исчезнуть"


async def test_flickering_page_does_not_count_as_human_action() -> None:
    """Страница дёргается сама (баннер, дозагрузка) — это не действие человека.

    Без такой проверки агент зафиксировал бы исход, которого ещё нет.
    """
    record = record_for()
    gate = make_gate(asyncio.Event(), timeout_s=0.2, poll_s=0.01)
    flicker = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"] * 5

    async def probe() -> str:
        return flicker.pop(0) if flicker else "z"

    ok = await gate.handoff_action(record, "«Оплатить заказ»", probe)

    assert ok is False, "мигание не должно засчитываться как завершённый шаг"
    assert record.metadata["handoff_resolved_by"] == "timeout"


async def test_explicit_resume_still_wins() -> None:
    """Человек подтвердил в интерфейсе — продолжаем, даже если страница не менялась."""
    record = record_for()
    resume = asyncio.Event()
    gate = make_gate(resume, timeout_s=2.0, poll_s=0.01)

    async def press_later() -> None:
        await asyncio.sleep(0.02)
        resume.set()

    presser = asyncio.create_task(press_later())
    ok = await gate.handoff_action(record, "«Оплатить заказ»", probe_of(["same"]))
    await presser

    assert ok is True
    assert record.metadata["handoff_resolved_by"] == "resume"


async def test_timeout_without_any_signal() -> None:
    record = record_for()
    gate = make_gate(asyncio.Event(), timeout_s=0.05, poll_s=0.01)

    ok = await gate.handoff_action(record, "«Оплатить заказ»", probe_of(["same"]))

    assert ok is False
    assert record.metadata["handoff_resolved_by"] == "timeout"


async def test_broken_probe_does_not_break_the_pause() -> None:
    """Человек закрыл окно или ушёл со страницы — пауза продолжает ждать resume."""
    record = record_for()
    resume = asyncio.Event()
    gate = make_gate(resume, timeout_s=1.0, poll_s=0.01)

    async def probe() -> str:
        raise RuntimeError("target closed")

    async def press_later() -> None:
        await asyncio.sleep(0.03)
        resume.set()

    presser = asyncio.create_task(press_later())
    ok = await gate.handoff_action(record, "«Оплатить заказ»", probe)
    await presser

    assert ok is True
    assert record.metadata["handoff_resolved_by"] == "resume"


async def test_confirm_submit_has_no_autodetect() -> None:
    """Tier 2 остаётся строго на подтверждении: там человек отвечает, а не действует.

    Автодетект здесь означал бы «страница моргнула — считаем, что разрешил».
    """
    record = record_for()
    gate = make_gate(asyncio.Event(), timeout_s=0.05, poll_s=0.01)

    ok = await gate.confirm_action(record, "submit «Отправить»")

    assert ok is False
    assert record.metadata["confirm_submit_resolved_by"] == "timeout"
