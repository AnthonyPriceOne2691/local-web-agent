"""Характеризационные тесты гейт-скриптов OKF и stack-selftest.

Как и у `delivery_check`, написаны ДО разбора сложности и пиннят наблюдаемое
поведение: exit code и ключевые строки вывода. Скрипты вызываются процессами —
проверяется граница, а не внутренние функции.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OKF_VALIDATE = REPO / "scripts" / "okf_validate.py"
OKF_SYNC = REPO / "scripts" / "okf_sync_gate.py"
SELFTEST = REPO / "scripts" / "stack_selftest.py"

CONCEPT = """---
type: Policy
title: Demo
---

# Purpose

Текст концепта.
"""


def run(script: Path, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None):
    import os

    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
    )


def make_bundle(tmp_path: Path, **files: str) -> Path:
    bundle = tmp_path / "knowledge"
    (bundle / "engineering").mkdir(parents=True)
    for rel, body in files.items():
        target = bundle / rel.replace("__", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return bundle


# --- okf_validate ----------------------------------------------------------


def test_valid_bundle_passes(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, **{"index.md": "okf_version: 1\n", "engineering__a.md": CONCEPT})
    done = run(OKF_VALIDATE, str(bundle))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "0 error(s)" in done.stdout


def test_concept_without_frontmatter_is_error(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, **{"index.md": "okf_version: 1\n", "engineering__a.md": "# no fm\n"})
    done = run(OKF_VALIDATE, str(bundle))
    assert done.returncode == 1
    assert "missing YAML frontmatter" in done.stderr


def test_concept_without_type_is_error(tmp_path: Path) -> None:
    bundle = make_bundle(
        tmp_path, **{"index.md": "okf_version: 1\n", "engineering__a.md": "---\ntitle: x\n---\n\n# P\n"}
    )
    done = run(OKF_VALIDATE, str(bundle))
    assert done.returncode == 1
    assert "missing non-empty type" in done.stderr


def test_missing_index_and_broken_link_are_warnings(tmp_path: Path) -> None:
    """Мягкие правила остаются мягкими: предупреждение не роняет прогон."""
    concept = CONCEPT + "\nСм. [нет](/engineering/ghost.md)\n"
    bundle = make_bundle(tmp_path, **{"engineering__a.md": concept})
    done = run(OKF_VALIDATE, str(bundle))
    assert done.returncode == 0
    assert "missing root index.md" in done.stdout
    assert "broken bundle link /engineering/ghost.md" in done.stdout


def test_missing_bundle_dir_is_error(tmp_path: Path) -> None:
    done = run(OKF_VALIDATE, str(tmp_path / "nope"))
    assert done.returncode == 1
    assert "bundle root not a directory" in done.stderr


def test_log_without_dated_headings_warns(tmp_path: Path) -> None:
    bundle = make_bundle(
        tmp_path,
        **{"index.md": "okf_version: 1\n", "log.md": "# Log\n\nбез дат\n", "engineering__a.md": CONCEPT},
    )
    done = run(OKF_VALIDATE, str(bundle))
    assert done.returncode == 0
    assert "no ## YYYY-MM-DD headings" in done.stdout


# --- okf_sync_gate --check-stale -------------------------------------------


def test_stale_after_in_the_past_fails(tmp_path: Path) -> None:
    concept = "---\ntype: Policy\nstale_after: 2000-01-01\nimplementation:\n  - app/x.py\n---\n\n# P\n"
    make_bundle(tmp_path, **{"index.md": "okf_version: 1\n", "engineering__a.md": concept})
    done = run(OKF_SYNC, "--check-stale", cwd=tmp_path)
    assert done.returncode == 1
    assert "stale_after 2000-01-01 is in the past" in done.stderr


def test_fresh_bundle_freshness_ok(tmp_path: Path) -> None:
    concept = "---\ntype: Policy\nimplementation:\n  - app/x.py\n---\n\n# P\n"
    make_bundle(tmp_path, **{"index.md": "okf_version: 1\n", "engineering__a.md": concept})
    done = run(OKF_SYNC, "--check-stale", cwd=tmp_path)
    assert done.returncode == 0
    assert "freshness OK" in done.stdout


def test_no_bundle_is_skip_not_failure(tmp_path: Path) -> None:
    """Гейт без bundle молчит и пропускает — иначе он ронял бы чужие репозитории."""
    done = run(OKF_SYNC, "--check-stale", cwd=tmp_path)
    assert done.returncode == 0
    assert "skip" in done.stdout


# --- stack_selftest --------------------------------------------------------


def test_selftest_reports_missing_canon_dir(tmp_path: Path) -> None:
    done = run(SELFTEST, str(tmp_path / "nope"))
    assert done.returncode != 0 or "not" in (done.stdout + done.stderr).lower()
