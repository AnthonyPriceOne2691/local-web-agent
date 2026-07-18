"""RunStore — Phase 1: flat JSON в data/runs/{id}.json + artifacts/ (doc 12).
SQLite — Phase 2; интерфейс сохранится."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.schemas.run import RunRecord


class RunStore(Protocol):
    def save(self, record: RunRecord) -> None: ...

    def get(self, run_id: str) -> RunRecord | None: ...

    def list_ids(self) -> list[str]: ...

    def artifacts_dir(self, run_id: str) -> Path: ...

    def startup_sweep(self) -> int: ...


class JsonRunStore:
    def __init__(self, runs_dir: Path):
        self._dir = runs_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self._dir / f"{run_id}.json"

    def save(self, record: RunRecord) -> None:
        self._path(record.id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def get(self, run_id: str) -> RunRecord | None:
        path = self._path(run_id)
        if not path.is_file():
            return None
        return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_ids(self) -> list[str]:
        return sorted((p.stem for p in self._dir.glob("*.json")), reverse=True)

    def artifacts_dir(self, run_id: str) -> Path:
        path = self._dir / "artifacts" / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def startup_sweep(self) -> int:
        """Zombie runs после рестарта (doc 12): running → failed(orphaned)."""
        swept = 0
        for run_id in self.list_ids():
            record = self.get(run_id)
            if record and record.status == "running":
                record.status = "failed"
                record.error_message = "orphaned: backend restart"
                self.save(record)
                swept += 1
        return swept
