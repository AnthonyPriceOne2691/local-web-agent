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

from app.schemas.run import RunRecord
from app.schemas.snapshot import PageSnapshot
from app.storage.run_store import RunStore


class AttendedGate(Protocol):
    async def try_clear(
        self, record: RunRecord, snapshot: PageSnapshot,
        snapshots: list[PageSnapshot], visited: set[str],
    ) -> bool: ...


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
