#!/usr/bin/env python3
"""Hard limit ≤ 500 LOC на файл в backend/app/ и cli/ (doc 18). Spike — исключение."""

from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 500
ROOT = Path(__file__).resolve().parents[1]
SCOPES = [ROOT / "backend" / "app", ROOT / "cli"]


def main() -> int:
    offenders = []
    for scope in SCOPES:
        for path in scope.rglob("*.py"):
            loc = sum(1 for _ in path.open(encoding="utf-8"))
            if loc > LIMIT:
                offenders.append((path.relative_to(ROOT), loc))
    if offenders:
        for path, loc in offenders:
            print(f"FAIL {path}: {loc} LOC > {LIMIT}")
        return 1
    print(f"OK: all modules ≤ {LIMIT} LOC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
