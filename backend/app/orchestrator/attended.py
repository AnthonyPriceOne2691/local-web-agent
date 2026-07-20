"""Attended-режим (Phase 5, doc 24): человек проходит anti-bot challenge, агент продолжает.

**Не** обход детекта: агент упирается в Cloudflare/captcha, ставит run в
`waiting_user`, ждёт, пока пользователь пройдёт проверку в видимом браузере и
нажмёт resume. После resume challenge-снапшот выбрасывается, страница
переобсёрвивается (DOM уже настоящий). Логика вынесена из loop.py (≤500 LOC,
doc 18) и держит orchestrator тонким: одна развилка на границе OBSERVE.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Protocol

from app.browser.base import BrowserSession
from app.observer.snapshot import build_snapshot
from app.orchestrator.states import State
from app.schemas.run import CrawlStep, RunRecord
from app.schemas.snapshot import PageSnapshot
from app.storage.run_store import RunStore


class AttendedGate(Protocol):
    async def try_clear(
        self, record: RunRecord, snapshot: PageSnapshot,
        snapshots: list[PageSnapshot], visited: set[str],
    ) -> bool: ...

    async def confirm_action(self, record: RunRecord, description: str) -> bool: ...

    async def handoff_action(self, record: RunRecord, description: str) -> bool: ...


class EventAttendedGate:
    """Пауза на challenge → ожидание resume_event с таймаутом → сброс для повторного захода."""

    def __init__(self, resume_event: asyncio.Event, store: RunStore, *, timeout_s: float):
        self._resume = resume_event
        self._store = store
        self._timeout_s = timeout_s

    async def try_clear(
        self, record: RunRecord, snapshot: PageSnapshot,
        snapshots: list[PageSnapshot], visited: set[str],
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

    async def handoff_action(self, record: RunRecord, description: str) -> bool:
        """Tier 3 (doc 25): handoff — агент подготовил необратимый шаг, **кнопку жмёт
        человек сам** в видимом браузере; агент не кликает ни до, ни после. True —
        человек завершил (re-observe покажет исход), False — таймаут."""
        return await self._pause_for_user(record, "handoff", description)

    async def _pause_for_user(self, record: RunRecord, kind: str, description: str) -> bool:
        """Общая пауза Tier 2/3: `waiting_user` + resume-event, что и challenge
        (kind → SSE challenge_wait → kind-aware карточка в Chat UI)."""
        self._resume.clear()
        record.status = "waiting_user"
        record.metadata["challenge"] = {
            "url": record.current_url, "kind": kind,
            "action": description, "since": datetime.now(UTC).isoformat(),
        }
        self._store.save(record)  # SSE увидит через poll → challenge_wait
        try:
            await asyncio.wait_for(self._resume.wait(), timeout=self._timeout_s)
        except TimeoutError:
            record.metadata.pop("challenge", None)
            record.status = "running"
            self._store.save(record)
            return False
        record.metadata.pop("challenge", None)
        record.status = "running"
        self._store.save(record)
        return True


async def reobserve_in_place(
    browser: BrowserSession, record: RunRecord, *,
    origin: str, step_index: int,
    snapshots: list[PageSnapshot], visited: set[str],
    note: str = "attended: re-observe after resume",
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
    record.steps.append(CrawlStep(index=step_index, state=State.OBSERVE, url=snap.url, note=note))
    return snap
