#!/usr/bin/env python3
"""Delivery harness checker.

Usage:
  python scripts/delivery_check.py
  python scripts/delivery_check.py --require-spec
  python scripts/delivery_check.py --root DIR      # прогон на фикстуре

Exit 0 = OK (warnings allowed). Exit 1 = errors.

Структура: одна проверка — одна функция, каждая возвращает `Report`
(ошибки + предупреждения). `main()` только собирает контекст и печатает: до
разбора это была одна функция на 123 строки и 50 ветвлений, где условия §2.2
и §3.4 читались вперемешку. Поведение зафиксировано тестами
`backend/tests/test_delivery_check_gate.py` — они писались ДО разбора.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# §3.4; переопределяются строкой в STATUS: "max_files_touched=40 reason=… by=human:…"
DEFAULT_BREAKERS = {"max_files_touched": 25, "max_loc_diff": 800}

# Процессные артефакты не считаются в breaker'ах: spec/plan/tasks и concept'ы —
# это не blast radius кода, а его описание.
BREAKER_EXCLUDE = ("delivery/", "knowledge/")

ALLOWED_PHASES = {"specify", "plan", "tasks", "implement", "verify", "converge", "handoff"}
IMPLEMENT_LIKE = {"implement", "verify", "converge", "handoff"}

# (ошибки, предупреждения) — возвращают все проверки, поэтому их можно складывать.
Report = tuple[list[str], list[str]]
EMPTY: Report = ([], [])


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def git(*args: str) -> str:
    """git с подавлением ошибок: пустая строка = не смог."""
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return ""
    return out.stdout if out.returncode == 0 else ""


def diff_stats(base: str) -> tuple[int, int, int, int] | None:
    """(files, added, deleted, excluded) для base..HEAD; None если ref недоступен."""
    if not git("rev-parse", "--verify", "--quiet", base).strip():
        return None
    merge_base = git("merge-base", base, "HEAD").strip() or base
    files = added = deleted = excluded = 0
    for line in git("diff", "--numstat", f"{merge_base}..HEAD").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, path = parts
        if path.startswith(BREAKER_EXCLUDE):
            excluded += 1
            continue
        files += 1
        added += int(a) if a.isdigit() else 0  # "-" у бинарников
        deleted += int(d) if d.isdigit() else 0
    return files, added, deleted, excluded


def field(status: str, name: str) -> str:
    """Значение поля STATUS: "- **class:** M" -> "M". Inline-комментарий срезается."""
    m = re.search(rf"(?im)^[ \t]*[-*]?[ \t]*\**{name}\**[ \t]*:\**[ \t]*(.*)$", status)
    if not m:
        return ""
    return re.sub(r"<!--.*?-->", "", m.group(1)).strip()


def is_placeholder(value: str) -> bool:
    """Незаполненный шаблон: "<S|M|L>", "S | M | L", "…", пусто.

    Ключевой признак — вертикальная черта: список альтернатив из шаблона не может
    быть выбранным значением. Без этой проверки STATUS с необработанной строкой
    "class: S | M | L" читался бы как class=S, и класс L проезжал бы мимо
    требований spec/plan (§2.2).
    """
    if not value or value in {"…", "...", "-", "TBD", "tbd"}:
        return True
    return "|" in value or value.startswith("<")


@dataclass(frozen=True)
class Shipment:
    """Разобранное состояние активной поставки — вход всех проверок."""

    active: Path
    status: str
    phase: str
    klass: str

    def artifact(self, name: str) -> Path:
        return self.active / f"{name}.md"

    def has(self, name: str) -> bool:
        return self.artifact(name).is_file()


def resolve_phase_class(status: str) -> tuple[str, str, Report]:
    """(phase, class, отчёт). Пустая строка = значение не разобрано."""
    errors: list[str] = []
    warnings: list[str] = []

    raw_phase = field(status, "phase")
    raw_class = field(status, "class")
    phase_m = re.match(r"(?i)^([a-z_]+)", raw_phase) if not is_placeholder(raw_phase) else None
    class_m = re.match(r"(?i)^([SML])\b", raw_class) if not is_placeholder(raw_class) else None
    phase = phase_m.group(1).lower() if phase_m else ""
    klass = class_m.group(1).upper() if class_m else ""

    if is_placeholder(raw_phase):
        errors.append(f"STATUS.md: phase not filled in (template placeholder {raw_phase!r})")
    elif not phase:
        errors.append("STATUS.md: missing phase")
    elif phase not in ALLOWED_PHASES:
        # constitution is project-level file, not active phase
        errors.append(f"STATUS.md: unknown phase '{phase}' (allowed: {', '.join(sorted(ALLOWED_PHASES))})")

    if not klass:
        msg = (
            f"STATUS.md: class not resolved (value {raw_class!r}) — "
            "cannot apply §2.2 artifact gates; write exactly one of S|M|L"
        )
        # На specify класс ещё может уточняться; с plan и дальше это блокер:
        # неизвестный класс = молча отключённые требования spec/plan.
        (warnings if phase == "specify" else errors).append(msg)

    return phase, klass, (errors, warnings)


def check_spec_and_plan(s: Shipment) -> Report:
    """§2.2/§3.3: спека, план и подтверждения человека — по классу поставки."""
    errors: list[str] = []

    if s.klass in {"M", "L"} and s.phase in {"plan", "tasks", *IMPLEMENT_LIKE} and not s.has("spec"):
        errors.append(f"class {s.klass} at phase={s.phase}: missing active/spec.md")

    if s.klass in {"M", "L"} and s.phase in IMPLEMENT_LIKE:
        if not s.has("plan"):
            errors.append(f"class {s.klass} at phase={s.phase}: missing active/plan.md")
        if not s.has("tasks"):
            errors.append(f"class {s.klass} at phase={s.phase}: missing active/tasks.md")
        # §3.3 называет это stop-gate'ом — значит error, не warning.
        if not field(s.status, "human_ok_spec").lower().startswith("yes"):
            errors.append(f"class {s.klass} at phase={s.phase}: human_ok_spec is not yes (stop-gate §3.3)")

    if (
        s.klass == "L"
        and s.phase in IMPLEMENT_LIKE
        and not field(s.status, "human_ok_plan").lower().startswith("yes")
    ):
        errors.append("class L at implement+: human_ok_plan is not yes (stop-gate §3.3)")

    if s.klass == "S" and s.phase in IMPLEMENT_LIKE and not s.has("tasks"):
        errors.append("class S at implement+: missing active/tasks.md (mini-spec)")

    return errors, []


def check_reports(s: Shipment) -> Report:
    """Отчёт о проверке и product-oracles: когда их отсутствие — блокер."""
    errors: list[str] = []
    warnings: list[str] = []

    if not s.has("verify-report"):
        if s.phase == "verify":
            # Фаза в процессе: отчёт ещё пишется — но выйти из неё без него нельзя.
            warnings.append("phase=verify: active/verify-report.md not created yet")
        elif s.phase in {"converge", "handoff"}:
            errors.append(f"phase={s.phase}: missing active/verify-report.md (DoD §3.2.2)")

    if s.klass in {"M", "L"} and s.phase in {"verify", "converge", "handoff"} and not s.has("eval-smoke"):
        errors.append(
            "class M/L at verify+: missing active/eval-smoke.md (product oracles are mandatory, §6.2)"
        )

    return errors, warnings


def check_handoff(s: Shipment) -> Report:
    """На handoff отчёт обязан нести вердикт и метрики (§9.2 / A.10)."""
    if s.phase != "handoff" or not s.has("verify-report"):
        return EMPTY
    errors: list[str] = []
    vr = read(s.artifact("verify-report"))
    if not re.search(r"READY FOR HANDOFF", vr, re.I):
        errors.append("phase=handoff: verify-report.md lacks 'READY FOR HANDOFF' verdict")
    # §9.2: метрики снимаются на handoff. Без гейта ритуал не выполняется.
    if "Harness metrics" not in vr:
        errors.append(
            "phase=handoff: verify-report.md lacks the 'Harness metrics' "
            "block (§9.2 / A.10) — run: python scripts/delivery_metrics.py "
            "--base origin/main --write"
        )
    return errors, []


def check_verifier(s: Shipment) -> Report:
    """§5.2: не сама независимость, но явное заявление о ней.

    Настоящее разделение обеспечивает required review в branch protection
    (CQG §8.5); здесь ловим «сам построил, сам принял».
    """
    if s.phase not in {"verify", "converge", "handoff"} or not s.has("verify-report"):
        return EMPTY
    declared = field(read(s.artifact("verify-report")), "Verifier") or field(s.status, "verifier")
    builder = field(s.status, "builder")
    if is_placeholder(declared):
        return (
            [
                "verify-report.md: Verifier not filled in — Builder must not "
                "accept own work (§5.2); write process:ci | agent:NAME | human:NAME"
            ],
            [],
        )
    if (
        s.klass in {"M", "L"}
        and not is_placeholder(builder)
        and declared.strip().lower() == builder.strip().lower()
    ):
        return (
            [
                f"class {s.klass}: verifier == builder ('{declared}') — §5.2 "
                "requires a different agent/model/human, or process:ci"
            ],
            [],
        )
    return EMPTY


def check_ci(s: Shipment, require_ci: bool) -> Report:
    """§10.4: CI — единственный слой, который агент не может обойти локально."""
    errors: list[str] = []
    warnings: list[str] = []
    ci = field(s.status, "ci-oracles").lower()
    waivers = field(s.status, "waivers").lower()

    if is_placeholder(ci):
        warnings.append("STATUS.md: missing ci-oracles (weak|tooling|deployed) — §10.4")
    elif ci.startswith("weak"):
        if s.klass == "L" and "ci" not in waivers:
            errors.append("class L with ci-oracles: weak and no ci waiver in STATUS (§10.4)")
        else:
            warnings.append(
                "ci-oracles: weak — local gates are bypassable (§10.4); "
                "Verifier must attach a clean-clone run to verify-report.md"
            )
    # 'tooling' — легитимный режим (гейт мержа в репо, серверного нет по тарифу),
    # а не поддавки: см. §10.4. Недопустим только 'weak'.
    if require_ci and not ci.startswith(("deployed", "tooling")):
        errors.append("--require-ci: ci-oracles is neither 'deployed' nor 'tooling'")

    stack = field(s.status, "stack")
    if is_placeholder(stack) or "delivery@" not in stack:
        warnings.append("STATUS.md: missing stack version (e.g. 'delivery@1.11, cqg@1.2, okf@absent')")

    return errors, warnings


def check_breakers(status: str, diff_base: str) -> Report:
    """§3.4: анти-oneshot по объёму поставки."""
    limits = dict(DEFAULT_BREAKERS)
    # Одна и та же форма покрывает и override в circuit_breakers,
    # и human waiver: "max_files_touched=40 reason=… by=human:…".
    for m in re.finditer(r"(max_[a-z_]+)[ \t]*=[ \t]*(\d+)", status):
        if m.group(1) in limits:
            limits[m.group(1)] = int(m.group(2))

    stats = diff_stats(diff_base)
    if stats is None:
        return [], [f"circuit breakers: ref '{diff_base}' unavailable (shallow clone? need full history)"]

    n_files, added, deleted, excluded = stats
    net = abs(added - deleted)
    print(
        f"breakers: files={n_files} net_loc={net} (+{added}/-{deleted}), "
        f"excluded={excluded} ({'|'.join(BREAKER_EXCLUDE)}), "
        f"limits={limits}"
    )
    errors: list[str] = []
    if n_files > limits["max_files_touched"]:
        errors.append(
            f"circuit breaker: files_touched {n_files} > "
            f"{limits['max_files_touched']} — split the PR or add a "
            "human waiver line to STATUS (§3.4)"
        )
    if net > limits["max_loc_diff"]:
        errors.append(
            f"circuit breaker: net loc_diff {net} > "
            f"{limits['max_loc_diff']} — split the PR or add a "
            "human waiver line to STATUS (§3.4)"
        )
    return errors, []


def check_stack_pointers(root: Path, delivery: Path) -> Report:
    """Подключённый слой стека обязан быть виден из конституции."""
    warnings: list[str] = []
    cons = read(delivery / "CONSTITUTION.md")
    if (root / "CODE_QUALITY_GATES.md").is_file() and "CODE_QUALITY_GATES" not in cons:
        warnings.append("CQG present but CONSTITUTION.md has no pointer")
    okf_present = (root / "OKF_KNOWLEDGE_BUNDLE.md").is_file() or (root / "knowledge").is_dir()
    if okf_present and "OKF" not in cons and "knowledge/" not in cons:
        warnings.append("OKF/knowledge present but CONSTITUTION.md has no pointer")
    return [], warnings


def report(errors: list[str], warnings: list[str]) -> int:
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    print(f"delivery_check: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-spec", action="store_true")
    ap.add_argument("--require-verify", action="store_true")
    ap.add_argument(
        "--require-ci",
        action="store_true",
        help="fail unless ci-oracles: deployed (§10.4)",
    )
    ap.add_argument(
        "--diff-base",
        metavar="REF",
        help="check circuit breakers §3.4 against REF (e.g. origin/main)",
    )
    # Корень репозитория параметром — чтобы гейт можно было прогнать на
    # фикстуре, а не только на самом себе. Дефолт прежний: каталог над scripts/.
    ap.add_argument("--root", metavar="DIR", help="repo root (default: this repo)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve() if args.root else ROOT
    delivery = root / "delivery"
    active = delivery / "active"

    errors: list[str] = []
    warnings: list[str] = []

    if not (delivery / "CONSTITUTION.md").is_file():
        errors.append("missing delivery/CONSTITUTION.md")
    if not active.is_dir():
        errors.append("missing delivery/active/")
        return report(errors, warnings)

    status = read(active / "STATUS.md")
    if not status:
        errors.append("missing delivery/active/STATUS.md")
    else:
        phase, klass, parsed = resolve_phase_class(status)
        shipment = Shipment(active=active, status=status, phase=phase, klass=klass)
        checks: list[Report] = [
            parsed,
            check_spec_and_plan(shipment),
            check_reports(shipment),
            check_handoff(shipment),
            check_verifier(shipment),
            check_ci(shipment, args.require_ci),
        ]
        if args.diff_base:
            checks.append(check_breakers(status, args.diff_base))
        for errs, warns in checks:
            errors += errs
            warnings += warns

    if args.require_spec and not (active / "spec.md").is_file():
        errors.append("--require-spec: active/spec.md missing")
    if args.require_verify and not (active / "verify-report.md").is_file():
        errors.append("--require-verify: verify-report.md missing")

    pointer_errors, pointer_warnings = check_stack_pointers(root, delivery)
    errors += pointer_errors
    warnings += pointer_warnings

    return report(errors, warnings)


if __name__ == "__main__":
    sys.exit(main())
