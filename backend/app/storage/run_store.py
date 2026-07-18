"""RunStore Protocol (doc 12). Phase 1 — flat JSON; Phase 2 — SqliteRunStore
(единственная реализация; legacy JSON импортируется при первом старте)."""

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

    def active_run_id(self) -> str | None: ...

    def delete(self, run_id: str) -> bool: ...
