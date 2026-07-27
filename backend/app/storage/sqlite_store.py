"""SqliteRunStore — Phase 2 (doc 12): SQLite WAL + artifacts, run lock производный от БД.

Интерфейс RunStore сохранён с Phase 1; JSON-файлы Phase 1 импортируются при первом
старте (data/runs/*.json → БД, файлы уезжают в data/runs/legacy_json/).
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.schemas.run import RunRecord

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_runs (
    id            TEXT PRIMARY KEY,
    task          TEXT NOT NULL,
    start_url     TEXT NOT NULL,
    config_json   TEXT NOT NULL,
    status        TEXT NOT NULL,
    intent        TEXT NOT NULL DEFAULT 'generic',
    current_url   TEXT NOT NULL DEFAULT '',
    pages_visited INTEGER NOT NULL DEFAULT 0,
    result_json   TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT NOT NULL DEFAULT '',
    started_at    TEXT NOT NULL DEFAULT '',
    finished_at   TEXT,
    session_id    TEXT
);
CREATE TABLE IF NOT EXISTS crawl_steps (
    run_id                TEXT NOT NULL REFERENCES crawl_runs(id) ON DELETE CASCADE,
    seq                   INTEGER NOT NULL,
    step_index            INTEGER NOT NULL,
    state                 TEXT NOT NULL,
    url                   TEXT NOT NULL DEFAULT '',
    action                TEXT NOT NULL DEFAULT '',
    target_url            TEXT,
    llm_reasoning         TEXT NOT NULL DEFAULT '',
    note                  TEXT NOT NULL DEFAULT '',
    contract_violations   TEXT NOT NULL DEFAULT '[]',
    duration_ms           INTEGER NOT NULL DEFAULT 0,
    screenshot_paths_json TEXT NOT NULL DEFAULT '{}',
    llm_stats_json        TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON crawl_runs(started_at DESC);
CREATE TABLE IF NOT EXISTS research_sessions (
    id                     TEXT PRIMARY KEY,
    title                  TEXT NOT NULL DEFAULT '',
    status                 TEXT NOT NULL,
    research_intent        TEXT,
    config_json            TEXT NOT NULL DEFAULT '{}',
    messages_json          TEXT NOT NULL DEFAULT '[]',
    run_ids_json           TEXT NOT NULL DEFAULT '[]',
    comparison_result_json TEXT,
    created_at             TEXT NOT NULL DEFAULT '',
    finished_at            TEXT
);
"""

_FINAL_STATUSES = ("completed", "partial", "not_found", "blocked", "failed", "canceled")


class SqliteRunStore:
    def __init__(self, runs_dir: Path):
        self._dir = runs_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db = runs_dir / "app.db"
        with self._conn() as con:
            con.executescript(_SCHEMA)
            con.execute("PRAGMA journal_mode=WAL")
        self._import_legacy_json()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self._db, timeout=5.0)  # busy_timeout 5 s (doc 12)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys=ON")
            yield con
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------- RunStore
    def save(self, record: RunRecord) -> None:
        with self._conn() as con:
            con.execute(
                """INSERT INTO crawl_runs (id, task, start_url, config_json, status, intent,
                       current_url, pages_visited, result_json, metadata_json, error_message,
                       started_at, finished_at, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       status=excluded.status, intent=excluded.intent,
                       current_url=excluded.current_url, pages_visited=excluded.pages_visited,
                       result_json=excluded.result_json, metadata_json=excluded.metadata_json,
                       error_message=excluded.error_message, started_at=excluded.started_at,
                       finished_at=excluded.finished_at, session_id=excluded.session_id""",
                (
                    record.id, record.config.task, record.config.start_url,
                    record.config.model_dump_json(), record.status, record.intent,
                    record.current_url, record.pages_visited,
                    record.result.model_dump_json() if record.result else None,
                    json.dumps(record.metadata, ensure_ascii=False), record.error_message,
                    record.started_at, record.finished_at, record.session_id,
                ),
            )
            con.executemany(
                """INSERT OR REPLACE INTO crawl_steps (run_id, seq, step_index, state, url,
                       action, target_url, llm_reasoning, note, contract_violations,
                       duration_ms, screenshot_paths_json, llm_stats_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        record.id, seq, s.index, s.state, s.url, s.action, s.target_url,
                        s.reasoning, s.note,
                        json.dumps([v.model_dump() for v in s.violations], ensure_ascii=False),
                        s.duration_ms, json.dumps(s.screenshot_paths),
                        json.dumps(s.llm_stats, ensure_ascii=False),
                    )
                    for seq, s in enumerate(record.steps)
                ],
            )
        if record.result is not None and record.status in _FINAL_STATUSES:
            path = self.artifacts_dir(record.id) / "result.json"
            path.write_text(record.result.model_dump_json(indent=2), encoding="utf-8")

    def get(self, run_id: str) -> RunRecord | None:
        with self._conn() as con:
            run = con.execute("SELECT * FROM crawl_runs WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                return None
            steps = con.execute(
                "SELECT * FROM crawl_steps WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        return _record_from_rows(run, steps)

    def list_ids(self) -> list[str]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT id FROM crawl_runs ORDER BY started_at DESC, id DESC"
            ).fetchall()
        return [r["id"] for r in rows]

    def artifacts_dir(self, run_id: str) -> Path:
        path = self._dir / "artifacts" / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def startup_sweep(self) -> int:
        """Zombie runs после рестарта (doc 12): running/waiting_user → failed(orphaned).

        waiting_user (attended-пауза, Phase 5) после рестарта тоже зомби —
        resume_event потерян, ждать нечего."""
        with self._conn() as con:
            cur = con.execute(
                "UPDATE crawl_runs SET status='failed', error_message='orphaned: backend restart' "
                "WHERE status IN ('running', 'waiting_user')"
            )
            return cur.rowcount

    # -------------------------------------------------- Phase 2 extensions
    def active_run_id(self) -> str | None:
        """Run lock производный от БД (D-12, doc 12): нет running/waiting_user → свободен.

        waiting_user держит лок — браузер открыт, ждём человека (attended, Phase 5)."""
        with self._conn() as con:
            row = con.execute(
                "SELECT id FROM crawl_runs WHERE status IN ('running', 'waiting_user') LIMIT 1"
            ).fetchone()
        return row["id"] if row else None

    def runs_for_session(self, session_id: str) -> list[str]:
        """run_ids сессии в порядке старта (list_session_runs tool, doc 24)."""
        with self._conn() as con:
            rows = con.execute(
                "SELECT id FROM crawl_runs WHERE session_id = ? ORDER BY started_at",
                (session_id,),
            ).fetchall()
        return [r["id"] for r in rows]

    def delete(self, run_id: str) -> bool:
        """Удаляет запись + artifacts (doc 12 § Retention)."""
        with self._conn() as con:
            cur = con.execute("DELETE FROM crawl_runs WHERE id = ?", (run_id,))
        removed = cur.rowcount > 0
        artifacts = self._dir / "artifacts" / run_id
        if artifacts.is_dir():
            shutil.rmtree(artifacts, ignore_errors=True)
        return removed

    # ------------------------------------------------------------ internals
    def _import_legacy_json(self) -> None:
        """Phase 1 flat-файлы → БД; оригиналы уезжают в legacy_json/ (одноразово)."""
        legacy_files = [p for p in self._dir.glob("*.json") if p.is_file()]
        if not legacy_files:
            return
        backup = self._dir / "legacy_json"
        backup.mkdir(exist_ok=True)
        for path in legacy_files:
            try:
                record = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
                if self.get(record.id) is None:
                    self.save(record)
            except Exception as exc:
                # Файл всё равно уезжает в legacy_json/ — без лога потеря run'а
                # выглядела бы как «его никогда не было».
                logger.warning("legacy run %s not imported (%s: %s) — moved to %s",
                               path.name, type(exc).__name__, exc, backup.name)
            path.rename(backup / path.name)


def _record_from_rows(run: sqlite3.Row, steps: list[sqlite3.Row]) -> RunRecord:
    return RunRecord.model_validate(
        {
            "id": run["id"],
            "config": json.loads(run["config_json"]),
            "status": run["status"],
            "session_id": run["session_id"],
            "intent": run["intent"],
            "pages_visited": run["pages_visited"],
            "current_url": run["current_url"],
            "result": json.loads(run["result_json"]) if run["result_json"] else None,
            "metadata": json.loads(run["metadata_json"]),
            "error_message": run["error_message"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "steps": [
                {
                    "index": s["step_index"],
                    "state": s["state"],
                    "url": s["url"],
                    "action": s["action"],
                    "target_url": s["target_url"],
                    "reasoning": s["llm_reasoning"],
                    "note": s["note"],
                    "violations": json.loads(s["contract_violations"]),
                    "duration_ms": s["duration_ms"],
                    "screenshot_paths": json.loads(s["screenshot_paths_json"]),
                    "llm_stats": json.loads(s["llm_stats_json"]),
                }
                for s in steps
            ],
        }
    )
