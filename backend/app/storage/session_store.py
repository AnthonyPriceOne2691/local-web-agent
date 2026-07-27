"""SqliteSessionStore — research sessions Phase 3 (doc 12, doc 24).

Тот же app.db, что и SqliteRunStore (схему создаёт он). Сообщения храним
в messages_json внутри строки сессии (объёмы диалога малы; отдельная таблица
session_messages из doc 12 — при Chat UI Phase 4, если понадобится).
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from app.schemas.research import SessionRecord


class SessionStore(Protocol):
    def save(self, record: SessionRecord) -> None: ...

    def get(self, session_id: str) -> SessionRecord | None: ...

    def list_ids(self) -> list[str]: ...

    def delete(self, session_id: str) -> bool: ...

    def startup_sweep(self) -> int: ...

    def artifacts_dir(self, session_id: str) -> Path: ...


class SqliteSessionStore:
    def __init__(self, runs_dir: Path):
        self._dir = runs_dir
        self._db = runs_dir / "app.db"

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self._db, timeout=5.0)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def save(self, record: SessionRecord) -> None:
        with self._conn() as con:
            con.execute(
                """INSERT INTO research_sessions (id, title, status, research_intent,
                       config_json, messages_json, run_ids_json, comparison_result_json,
                       created_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       title=excluded.title, status=excluded.status,
                       research_intent=excluded.research_intent,
                       config_json=excluded.config_json, messages_json=excluded.messages_json,
                       run_ids_json=excluded.run_ids_json,
                       comparison_result_json=excluded.comparison_result_json,
                       created_at=excluded.created_at, finished_at=excluded.finished_at""",
                (
                    record.id,
                    record.title,
                    record.status,
                    record.research_intent,
                    record.config.model_dump_json(),
                    _dump_list([m.model_dump() for m in record.messages]),
                    _dump_list(record.run_ids),
                    record.comparison_result.model_dump_json() if record.comparison_result else None,
                    record.created_at,
                    record.finished_at,
                ),
            )

    def get(self, session_id: str) -> SessionRecord | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        import json

        return SessionRecord.model_validate(
            {
                "id": row["id"],
                "title": row["title"],
                "status": row["status"],
                "research_intent": row["research_intent"],
                "config": json.loads(row["config_json"]),
                "messages": json.loads(row["messages_json"]),
                "run_ids": json.loads(row["run_ids_json"]),
                "comparison_result": (
                    json.loads(row["comparison_result_json"]) if row["comparison_result_json"] else None
                ),
                "created_at": row["created_at"],
                "finished_at": row["finished_at"],
            }
        )

    def list_ids(self) -> list[str]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT id FROM research_sessions ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [r["id"] for r in rows]

    def delete(self, session_id: str) -> bool:
        with self._conn() as con:
            cur = con.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
        removed = cur.rowcount > 0
        artifacts = self._dir / "artifacts" / session_id
        if artifacts.is_dir():
            shutil.rmtree(artifacts, ignore_errors=True)
        return removed

    def startup_sweep(self) -> int:
        """Zombie-сессии после рестарта (doc 12): running_tools/comparing → failed."""
        with self._conn() as con:
            cur = con.execute(
                """UPDATE research_sessions
                   SET status='failed',
                       config_json=json_set(config_json, '$.canceled_by_restart', json('true'))
                   WHERE status IN ('running_tools', 'comparing')"""
            )
            return cur.rowcount

    def artifacts_dir(self, session_id: str) -> Path:
        path = self._dir / "artifacts" / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path


def _dump_list(items: list[Any]) -> str:
    import json

    return json.dumps(items, ensure_ascii=False)
