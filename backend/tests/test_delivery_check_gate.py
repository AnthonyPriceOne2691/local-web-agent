"""Характеризационные тесты `scripts/delivery_check.py`.

Написаны ДО разбора сложности `main()` (47 при пороге 10) и пиннят наблюдаемое
поведение: exit code и текст сообщений. Рефакторинг обязан оставить их зелёными —
иначе он поменял гейт, а не форму кода.

Гейт запускается процессом с `--root` на фикстуру: так проверяется настоящая
граница (аргументы + вывод + код возврата), а не внутренние функции.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "scripts" / "delivery_check.py"

STATUS_OK_S = """# Active delivery status

- **slug:** demo
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
- **phase:** implement
- **builder:** agent:claude-code
- **verifier:** human:anthony
- **ci-oracles:** tooling
- **waivers:** —
"""


def run_gate(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), "--root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def make_repo(tmp_path: Path, status: str | None, **files: str) -> Path:
    """Мини-репозиторий поставки: CONSTITUTION + active/ с нужными файлами."""
    (tmp_path / "delivery" / "active").mkdir(parents=True)
    (tmp_path / "delivery" / "CONSTITUTION.md").write_text("constitution", encoding="utf-8")
    if status is not None:
        (tmp_path / "delivery" / "active" / "STATUS.md").write_text(status, encoding="utf-8")
    for name, body in files.items():
        (tmp_path / "delivery" / "active" / f"{name}.md").write_text(body, encoding="utf-8")
    return tmp_path


def test_class_s_with_tasks_passes(tmp_path: Path) -> None:
    root = make_repo(tmp_path, STATUS_OK_S, tasks="mini-spec")
    done = run_gate(root)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "0 error(s)" in done.stdout


def test_class_s_without_tasks_fails(tmp_path: Path) -> None:
    """Class S на implement обязан иметь mini-spec — иначе поставки нет на бумаге."""
    root = make_repo(tmp_path, STATUS_OK_S)
    done = run_gate(root)
    assert done.returncode == 1
    assert "missing active/tasks.md (mini-spec)" in done.stderr


def test_missing_constitution_and_active(tmp_path: Path) -> None:
    done = run_gate(tmp_path)
    assert done.returncode == 1
    assert "missing delivery/CONSTITUTION.md" in done.stderr
    assert "missing delivery/active/" in done.stderr


def test_template_placeholders_are_not_values(tmp_path: Path) -> None:
    """«class: S | M | L» — незаполненный шаблон, а не выбранный класс S."""
    status = STATUS_OK_S.replace("- **class:** S", "- **class:** S | M | L").replace(
        "- **phase:** implement", "- **phase:** <specify|plan>"
    )
    root = make_repo(tmp_path, status, tasks="mini-spec")
    done = run_gate(root)
    assert done.returncode == 1
    assert "phase not filled in" in done.stderr
    assert "class not resolved" in done.stderr


def test_class_m_requires_spec_plan_and_human_ok(tmp_path: Path) -> None:
    status = STATUS_OK_S.replace("- **class:** S", "- **class:** M")
    root = make_repo(tmp_path, status, tasks="mini-spec")
    done = run_gate(root)
    assert done.returncode == 1
    assert "missing active/spec.md" in done.stderr
    assert "missing active/plan.md" in done.stderr
    assert "human_ok_spec is not yes (stop-gate §3.3)" in done.stderr


def test_class_l_requires_human_ok_plan(tmp_path: Path) -> None:
    status = STATUS_OK_S.replace("- **class:** S", "- **class:** L") + "- **human_ok_spec:** yes\n"
    root = make_repo(tmp_path, status, tasks="t", spec="s", plan="p")
    done = run_gate(root)
    assert done.returncode == 1
    assert "human_ok_plan is not yes (stop-gate §3.3)" in done.stderr


def test_handoff_requires_verdict_and_metrics(tmp_path: Path) -> None:
    status = STATUS_OK_S.replace("- **phase:** implement", "- **phase:** handoff")
    root = make_repo(tmp_path, status, tasks="t", **{"verify-report": "# Verify\n\nVerifier: human:x\n"})
    done = run_gate(root)
    assert done.returncode == 1
    assert "lacks 'READY FOR HANDOFF' verdict" in done.stderr
    assert "'Harness metrics'" in done.stderr


def test_verifier_equal_builder_blocks_class_m(tmp_path: Path) -> None:
    """§5.2: «сам построил, сам принял» — для M/L это ошибка, не пожелание."""
    status = (
        STATUS_OK_S.replace("- **class:** S", "- **class:** M")
        .replace("- **phase:** implement", "- **phase:** verify")
        .replace("- **verifier:** human:anthony", "- **verifier:** agent:claude-code")
        + "- **human_ok_spec:** yes\n"
    )
    root = make_repo(
        tmp_path,
        status,
        tasks="t",
        spec="s",
        plan="p",
        **{"eval-smoke": "e", "verify-report": "# Verify\n"},
    )
    done = run_gate(root)
    assert done.returncode == 1
    assert "verifier == builder" in done.stderr


def test_ci_oracles_weak_warns_but_passes_class_s(tmp_path: Path) -> None:
    status = STATUS_OK_S.replace("- **ci-oracles:** tooling", "- **ci-oracles:** weak")
    root = make_repo(tmp_path, status, tasks="t")
    done = run_gate(root)
    assert done.returncode == 0
    assert "ci-oracles: weak" in done.stdout


def test_require_ci_rejects_weak(tmp_path: Path) -> None:
    status = STATUS_OK_S.replace("- **ci-oracles:** tooling", "- **ci-oracles:** weak")
    root = make_repo(tmp_path, status, tasks="t")
    done = run_gate(root, "--require-ci")
    assert done.returncode == 1
    assert "--require-ci" in done.stderr


@pytest.mark.parametrize(
    "flag,expected", [("--require-spec", "spec.md missing"), ("--require-verify", "verify-report.md missing")]
)
def test_require_flags(tmp_path: Path, flag: str, expected: str) -> None:
    root = make_repo(tmp_path, STATUS_OK_S, tasks="t")
    done = run_gate(root, flag)
    assert done.returncode == 1
    assert expected in done.stderr
