#!/usr/bin/env python3
"""Delivery harness checker.

Usage:
  python scripts/delivery_check.py
  python scripts/delivery_check.py --require-spec

Exit 0 = OK (warnings allowed). Exit 1 = errors.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT / "delivery"
ACTIVE = DELIVERY / "active"

# §3.4; переопределяются строкой в STATUS: "max_files_touched=40 reason=… by=human:…"
DEFAULT_BREAKERS = {"max_files_touched": 25, "max_loc_diff": 800}

# Процессные артефакты не считаются в breaker'ах: spec/plan/tasks и concept'ы —
# это не blast radius кода, а его описание.
BREAKER_EXCLUDE = ("delivery/", "knowledge/")


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


def main() -> int:
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
    args = ap.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    if not (DELIVERY / "CONSTITUTION.md").is_file():
        errors.append("missing delivery/CONSTITUTION.md")
    if not ACTIVE.is_dir():
        errors.append("missing delivery/active/")
        for w in warnings:
            print(f"WARNING: {w}")
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(f"delivery_check: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1

    status = read(ACTIVE / "STATUS.md")
    if not status:
        errors.append("missing delivery/active/STATUS.md")
    else:
        allowed = {
            "specify",
            "plan",
            "tasks",
            "implement",
            "verify",
            "converge",
            "handoff",
        }
        implement_like = {"implement", "verify", "converge", "handoff"}

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
        elif phase not in allowed:
            # constitution is project-level file, not active phase
            errors.append(f"STATUS.md: unknown phase '{phase}' (allowed: {', '.join(sorted(allowed))})")

        if not klass:
            msg = (
                f"STATUS.md: class not resolved (value {raw_class!r}) — "
                "cannot apply §2.2 artifact gates; write exactly one of S|M|L"
            )
            # На specify класс ещё может уточняться; с plan и дальше это блокер:
            # неизвестный класс = молча отключённые требования spec/plan.
            if phase == "specify":
                warnings.append(msg)
            else:
                errors.append(msg)

        spec = ACTIVE / "spec.md"
        plan = ACTIVE / "plan.md"
        tasks = ACTIVE / "tasks.md"
        verify = ACTIVE / "verify-report.md"
        eval_smoke = ACTIVE / "eval-smoke.md"

        spec_required = klass in {"M", "L"} and phase in {"plan", "tasks", *implement_like}
        if spec_required and not spec.is_file():
            errors.append(f"class {klass} at phase={phase}: missing active/spec.md")

        if klass in {"M", "L"} and phase in implement_like:
            if not plan.is_file():
                errors.append(f"class {klass} at phase={phase}: missing active/plan.md")
            if not tasks.is_file():
                errors.append(f"class {klass} at phase={phase}: missing active/tasks.md")
            # §3.3 называет это stop-gate'ом — значит error, не warning.
            if not field(status, "human_ok_spec").lower().startswith("yes"):
                errors.append(f"class {klass} at phase={phase}: human_ok_spec is not yes (stop-gate §3.3)")

        if (
            klass == "L"
            and phase in implement_like
            and not field(status, "human_ok_plan").lower().startswith("yes")
        ):
            errors.append("class L at implement+: human_ok_plan is not yes (stop-gate §3.3)")

        if klass == "S" and phase in implement_like and not tasks.is_file():
            errors.append("class S at implement+: missing active/tasks.md (mini-spec)")

        if not verify.is_file():
            if phase == "verify":
                # Фаза в процессе: отчёт ещё пишется — но выйти из неё без него нельзя.
                warnings.append("phase=verify: active/verify-report.md not created yet")
            elif phase in {"converge", "handoff"}:
                errors.append(f"phase={phase}: missing active/verify-report.md (DoD §3.2.2)")

        smoke_required = klass in {"M", "L"} and phase in {"verify", "converge", "handoff"}
        if smoke_required and not eval_smoke.is_file():
            errors.append(
                "class M/L at verify+: missing active/eval-smoke.md (product oracles are mandatory, §6.2)"
            )

        if phase == "handoff" and verify.is_file():
            vr = read(verify)
            if not re.search(r"READY FOR HANDOFF", vr, re.I):
                errors.append("phase=handoff: verify-report.md lacks 'READY FOR HANDOFF' verdict")
            # §9.2: метрики снимаются на handoff. Без гейта ритуал не выполняется.
            if "Harness metrics" not in vr:
                errors.append(
                    "phase=handoff: verify-report.md lacks the 'Harness metrics' "
                    "block (§9.2 / A.10) — run: python scripts/delivery_metrics.py "
                    "--base origin/main --write"
                )

        # --- Builder ≠ Verifier (§5.2): не сама независимость, но явное заявление
        # о ней. Настоящее разделение обеспечивает required review в branch
        # protection (CQG §8.5); здесь ловим «сам построил, сам принял».
        if phase in {"verify", "converge", "handoff"} and verify.is_file():
            declared = field(read(verify), "Verifier") or field(status, "verifier")
            builder = field(status, "builder")
            if is_placeholder(declared):
                errors.append(
                    "verify-report.md: Verifier not filled in — Builder must not "
                    "accept own work (§5.2); write process:ci | agent:NAME | human:NAME"
                )
            elif (
                klass in {"M", "L"}
                and not is_placeholder(builder)
                and declared.strip().lower() == builder.strip().lower()
            ):
                errors.append(
                    f"class {klass}: verifier == builder ('{declared}') — §5.2 "
                    "requires a different agent/model/human, or process:ci"
                )

        # --- CI (§10.4): единственный слой, который агент не может обойти локально
        ci = field(status, "ci-oracles").lower()
        waivers = field(status, "waivers").lower()
        if is_placeholder(ci):
            warnings.append("STATUS.md: missing ci-oracles (weak|tooling|deployed) — §10.4")
        elif ci.startswith("weak"):
            if klass == "L" and "ci" not in waivers:
                errors.append("class L with ci-oracles: weak and no ci waiver in STATUS (§10.4)")
            else:
                warnings.append(
                    "ci-oracles: weak — local gates are bypassable (§10.4); "
                    "Verifier must attach a clean-clone run to verify-report.md"
                )
        # 'tooling' — легитимный режим (гейт мержа в репо, серверного нет по тарифу),
        # а не поддавки: см. §10.4. Недопустим только 'weak'.
        if args.require_ci and not ci.startswith(("deployed", "tooling")):
            errors.append("--require-ci: ci-oracles is neither 'deployed' nor 'tooling'")

        stack = field(status, "stack")
        if is_placeholder(stack) or "delivery@" not in stack:
            warnings.append("STATUS.md: missing stack version (e.g. 'delivery@1.11, cqg@1.2, okf@absent')")

        # --- Circuit breakers (§3.4): анти-oneshot по объёму поставки
        if args.diff_base:
            limits = dict(DEFAULT_BREAKERS)
            # Одна и та же форма покрывает и override в circuit_breakers,
            # и human waiver: "max_files_touched=40 reason=… by=human:…".
            for m in re.finditer(r"(max_[a-z_]+)[ \t]*=[ \t]*(\d+)", status):
                if m.group(1) in limits:
                    limits[m.group(1)] = int(m.group(2))
            stats = diff_stats(args.diff_base)
            if stats is None:
                warnings.append(
                    f"circuit breakers: ref '{args.diff_base}' unavailable (shallow clone? need full history)"
                )
            else:
                n_files, added, deleted, excluded = stats
                net = abs(added - deleted)
                print(
                    f"breakers: files={n_files} net_loc={net} (+{added}/-{deleted}), "
                    f"excluded={excluded} ({'|'.join(BREAKER_EXCLUDE)}), "
                    f"limits={limits}"
                )
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

    if args.require_spec and not (ACTIVE / "spec.md").is_file():
        errors.append("--require-spec: active/spec.md missing")
    if args.require_verify and not (ACTIVE / "verify-report.md").is_file():
        errors.append("--require-verify: verify-report.md missing")

    if (ROOT / "CODE_QUALITY_GATES.md").is_file():
        cons = read(DELIVERY / "CONSTITUTION.md")
        if "CODE_QUALITY_GATES" not in cons:
            warnings.append("CQG present but CONSTITUTION.md has no pointer")
    if (ROOT / "OKF_KNOWLEDGE_BUNDLE.md").is_file() or (ROOT / "knowledge").is_dir():
        cons = read(DELIVERY / "CONSTITUTION.md")
        if "OKF" not in cons and "knowledge/" not in cons:
            warnings.append("OKF/knowledge present but CONSTITUTION.md has no pointer")

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    print(f"delivery_check: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
