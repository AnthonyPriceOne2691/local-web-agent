"""Attended-режим (Phase 5, doc 24): человек проходит anti-bot challenge, агент продолжает.

**Не** обход детекта: агент упирается в Cloudflare/captcha, ставит run в
`waiting_user`, ждёт, пока пользователь пройдёт проверку в видимом браузере и
нажмёт resume. После resume challenge-снапшот выбрасывается, страница
переобсёрвивается (DOM уже настоящий). Логика вынесена из loop.py (≤500 LOC,
doc 18) и держит orchestrator тонким: одна развилка на границе OBSERVE.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from app.browser.base import BrowserSession
from app.observer.snapshot import build_snapshot
from app.orchestrator.states import State
from app.schemas.run import CrawlStep, RunRecord
from app.schemas.snapshot import PageSnapshot
from app.storage.run_store import RunStore

logger = logging.getLogger(__name__)


async def pause_with_window(browser: BrowserSession, pause: Awaitable[bool], *, hide_after: bool) -> bool:
    """Показать окно человеку, дождаться его, при возможности снова спрятать.

    Требование владельца после real-site прогона: без надобности окно перед глазами
    не висит (doc 24 § Видимость окна). Для challenge и логина прятать безопасно —
    cookie уже получен; для submit и Tier 3 окно остаётся, потому что человек
    продолжает работать со страницей.
    """
    if await browser.reveal():
        logger.info("browser window revealed for the human (page reopened)")
    try:
        return await pause
    finally:
        if hide_after:
            await browser.conceal()


# Подпись открытой страницы: URL + отпечаток текста. Нужна, чтобы заметить, что
# человек уже сделал свой шаг, и не заставлять его подтверждать это второй раз.
PageProbe = Callable[[], Awaitable[str]]
# «Сними скриншот этого шага» — стадии интеракции не знают про store (см. capture.py).
StepCapture = Callable[[RunRecord, PageSnapshot, int], Awaitable[None]]


class AttendedGate(Protocol):
    async def try_clear(
        self,
        record: RunRecord,
        snapshot: PageSnapshot,
        snapshots: list[PageSnapshot],
        visited: set[str],
    ) -> bool: ...

    async def confirm_action(self, record: RunRecord, description: str) -> bool: ...

    async def handoff_action(
        self, record: RunRecord, description: str, probe: PageProbe | None = None
    ) -> bool: ...


class EventAttendedGate:
    """Пауза на challenge → ожидание resume_event с таймаутом → сброс для повторного захода."""

    def __init__(
        self,
        resume_event: asyncio.Event,
        store: RunStore,
        *,
        timeout_s: float,
        poll_s: float = 2.0,
    ):
        self._resume = resume_event
        self._store = store
        self._timeout_s = timeout_s
        self._poll_s = poll_s  # как часто смотреть, не сделал ли человек свой шаг

    async def try_clear(
        self,
        record: RunRecord,
        snapshot: PageSnapshot,
        snapshots: list[PageSnapshot],
        visited: set[str],
    ) -> bool:
        """True — пользователь прошёл проверку (продолжаем); False — таймаут (blocked)."""
        self._resume.clear()  # до объявления паузы — иначе resume между save и clear теряется
        record.status = "waiting_user"
        record.metadata["challenge"] = {
            "url": snapshot.url,
            "kind": snapshot.status,  # captcha
            "since": datetime.now(UTC).isoformat(),
        }
        self._store.save(record)  # SSE увидит через poll → challenge_wait
        try:
            await asyncio.wait_for(self._resume.wait(), timeout=self._timeout_s)
        except TimeoutError:
            record.metadata["challenge_timeout"] = True
            record.status = "running"  # loop проставит blocked ниже
            self._store.save(record)
            return False
        # человек прошёл — выкидываем challenge-снапшот, разрешаем повторный OBSERVE
        record.status = "running"
        record.metadata.pop("challenge", None)
        record.metadata["challenge_cleared"] = record.metadata.get("challenge_cleared", 0) + 1
        if snapshot in snapshots:
            snapshots.remove(snapshot)
        visited.discard(snapshot.url)
        record.pages_visited = len(visited)
        self._store.save(record)
        return True

    async def confirm_action(self, record: RunRecord, description: str) -> bool:
        """Tier 2 (doc 25): пауза на подтверждение действия (submit) — человек жмёт resume.
        True — подтвердил (агент выполняет), False — таймаут (не выполняем)."""
        return await self._pause_for_user(record, "confirm_submit", description)

    async def handoff_action(
        self, record: RunRecord, description: str, probe: PageProbe | None = None
    ) -> bool:
        """Tier 3 (doc 25): handoff — агент подготовил необратимый шаг, **кнопку жмёт
        человек сам** в видимом браузере; агент не кликает ни до, ни после. True —
        человек завершил (re-observe покажет исход), False — таймаут.

        `probe` (если передан) даёт агенту заметить нажатие самому: человек и так
        сделал действие на странице, требовать от него второе подтверждение — лишний
        шаг. Явный resume при этом никуда не девается и срабатывает раньше опроса.
        """
        return await self._pause_for_user(record, "handoff", description, probe)

    async def _pause_for_user(
        self, record: RunRecord, kind: str, description: str, probe: PageProbe | None = None
    ) -> bool:
        """Общая пауза Tier 2/3: `waiting_user` + resume-event, что и challenge
        (kind → SSE challenge_wait → kind-aware карточка в Chat UI)."""
        self._resume.clear()
        record.status = "waiting_user"
        record.metadata["challenge"] = {
            "url": record.current_url,
            "kind": kind,
            "action": description,
            "since": datetime.now(UTC).isoformat(),
        }
        self._store.save(record)  # SSE увидит через poll → challenge_wait
        outcome = await self._wait_for_human(probe)
        record.metadata.pop("challenge", None)
        record.metadata[f"{kind}_resolved_by"] = outcome  # видно, чем кончилась пауза
        record.status = "running"
        self._store.save(record)
        return outcome != "timeout"

    async def _wait_for_human(self, probe: PageProbe | None) -> str:
        """`resume` · `page_change` · `timeout`.

        Изменение страницы засчитывается только если оно **держится** два опроса
        подряд: страница может дёрнуться сама (дозагрузка, баннер, редирект), и
        принять это за действие человека — значит зафиксировать исход, которого ещё
        нет. Явный resume проверяется первым и всегда сильнее опроса.
        """
        clock = asyncio.get_running_loop().time
        deadline = clock() + self._timeout_s
        baseline = await _read_probe(probe)
        pending: str | None = None
        while clock() < deadline:
            if await self._resume_within(min(self._poll_s, max(deadline - clock(), 0.0))):
                return "resume"
            current = await _read_probe(probe)
            if current is None or current == baseline:
                continue
            if pending == current:  # то же самое изменение второй раз — это не мигание
                return "page_change"
            pending = current
        return "timeout"

    async def _resume_within(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._resume.wait(), timeout=seconds)
        except TimeoutError:
            return False
        return True


def page_probe(browser: BrowserSession) -> PageProbe:
    """Подпись открытой страницы: URL + длина и хэш основного текста.

    Дёшево (одно чтение DOM) и достаточно, чтобы отличить «страница ответила на
    действие человека» от «ничего не произошло». Точность тут не нужна: решение
    всё равно подтверждается вторым опросом.
    """

    async def probe() -> str:
        raw = await browser.raw_snapshot()
        text = str(raw.get("main_text") or "")
        digest = hashlib.blake2s(text.encode("utf-8", "replace"), digest_size=8).hexdigest()
        return f"{browser.page_url()}|{len(text)}|{digest}"

    return probe


async def _read_probe(probe: PageProbe | None) -> str | None:
    """Подпись страницы или None, если снять её нельзя.

    Человек мог закрыть окно или уйти со страницы в момент опроса — это не повод
    ронять паузу: возвращаем None и продолжаем ждать resume или таймаут.
    """
    if probe is None:
        return None
    try:
        return await probe()
    except Exception as exc:  # silent-ok: диагностика в логе, пауза продолжается
        logger.debug("page probe failed during pause (%s)", type(exc).__name__)
        return None


async def reobserve_in_place(
    browser: BrowserSession,
    record: RunRecord,
    *,
    origin: str,
    step_index: int,
    snapshots: list[PageSnapshot],
    visited: set[str],
    note: str = "attended: re-observe after resume",
    capture: StepCapture | None = None,
) -> PageSnapshot:
    """OBSERVE текущей открытой страницы БЕЗ повторного goto.

    Используется после resume (attended, doc 24) и после Tier 1 click (doc 25):
    повторный goto заново упёрся бы в CF challenge / потерял бы результат клика —
    читаем уже открытую страницу на месте.
    """
    raw = await browser.raw_snapshot()
    url = browser.page_url() or record.current_url
    snap = build_snapshot(raw, page_url=url, origin=origin)
    snapshots.append(snap)
    visited.add(snap.url)
    record.pages_visited = len(visited)
    record.current_url = snap.url
    if capture is not None:
        await capture(record, snap, step_index)
    record.steps.append(
        CrawlStep(
            index=step_index,
            state=State.OBSERVE,
            url=snap.url,
            note=note,
            screenshot_paths={s.profile: s.relative_path for s in snap.screenshots},
        )
    )
    return snap
