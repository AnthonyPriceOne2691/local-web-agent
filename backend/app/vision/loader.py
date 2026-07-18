"""VisionLoader (doc 23) — shield для файлового доступа (doc 13 § Mode: Vision batch).

V-H1 allowlist (только пути из PageSnapshot.screenshots данного run) · V-H2 no
traversal/symlink escape · V-H3 размер ≤ 5 MB · V-H4 валидный profile.
Параметры — из data/contracts/vision.contract.yaml.
"""

from __future__ import annotations

import base64
from pathlib import Path

from app.contracts.loader import ContractSpec, load_contract

DEFAULT_MAX_PNG_BYTES = 5 * 1024 * 1024
DEFAULT_PROFILES = ("desktop", "tablet", "mobile")


class VisionLoadError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class VisionLoader:
    def __init__(self, artifacts_root: Path, spec: ContractSpec | None = None):
        self._root = artifacts_root.resolve()
        params = {r.check: r.params for r in spec.invariants_hard} if spec else {}
        self._max_bytes = int(params.get("file_size_ceiling", {}).get("max", DEFAULT_MAX_PNG_BYTES))
        self._profiles = tuple(params.get("profile_allowed", {}).get("allowed", DEFAULT_PROFILES))

    @classmethod
    def load(cls, artifacts_root: Path, contracts_dir: Path) -> VisionLoader:
        return cls(artifacts_root, load_contract(contracts_dir / "vision.contract.yaml"))

    @property
    def allowed_profiles(self) -> tuple[str, ...]:
        return self._profiles

    def resolve(self, run_id: str, relative_path: str, *, allowlist: set[str]) -> Path:
        """V-H1 + V-H2: путь из snapshot-allowlist, строго внутри artifacts/{run_id}."""
        if relative_path not in allowlist:
            raise VisionLoadError("path_not_in_snapshot")  # V-H1
        if relative_path.startswith(("/", "~")) or ".." in Path(relative_path).parts:
            raise VisionLoadError("path_traversal")  # V-H2
        run_dir = (self._root / run_id).resolve()
        full = (run_dir / relative_path).resolve()
        if not full.is_relative_to(run_dir):  # symlink escape
            raise VisionLoadError("path_traversal")
        return full

    def read_base64(self, run_id: str, relative_path: str, *, allowlist: set[str]) -> str:
        path = self.resolve(run_id, relative_path, allowlist=allowlist)
        if not path.is_file():
            raise VisionLoadError("file_missing")
        if path.stat().st_size > self._max_bytes:
            raise VisionLoadError("file_too_large")  # V-H3
        return base64.b64encode(path.read_bytes()).decode("ascii")
