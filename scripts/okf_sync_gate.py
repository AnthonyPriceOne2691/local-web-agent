#!/usr/bin/env python3
"""OKF code<->canon sync gate + freshness check.

Usage:
  python scripts/okf_sync_gate.py --base origin/main        # sync (PR-режим)
  python scripts/okf_sync_gate.py --staged                  # sync (pre-commit)
  python scripts/okf_sync_gate.py --check-stale             # freshness, без git
  OKF_BUNDLE=brain python scripts/okf_sync_gate.py --base origin/main

Exit 0 = OK (warnings allowed). Exit 1 = drift/staleness errors.

Waiver (осознанный дрейф — например, чистый рефакторинг без смены инварианта):
  ALLOW_CANON_DRIFT=1 python scripts/okf_sync_gate.py --base origin/main
Обязан быть виден и объяснён в PR. STRICT=0 — soft-режим (warning, exit 0).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

BUNDLE = os.environ.get("OKF_BUNDLE", "knowledge")
STRICT = os.environ.get("STRICT", "1") != "0"
ALLOW_DRIFT = os.environ.get("ALLOW_CANON_DRIFT", "0") == "1"
# Waiver, ВИДИМЫЙ в репозитории. env-переменной в CI не задать (а значит любая
# правка кода без смены инварианта — форматирование, типизация, логирование —
# роняла бы PR), поэтому осознанный дрейф объявляется строкой в STATUS:
#   canon_drift_waiver: reason=… by=human:…
# Она попадает в дифф, читается ревьюером и живёт ровно одну поставку.
STATUS_WAIVER_RE = re.compile(r"(?im)^[ \t]*[-*]?[ \t]*\**canon_drift_waiver\**[ \t]*:[ \t]*(.+)$")
RESERVED = {"index.md", "log.md"}

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def git(*args: str) -> str:
    """git с подавлением ошибок: пустая строка = git не смог (не блокер сам по себе)."""
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return ""
    return out.stdout if out.returncode == 0 else ""


def repo_root() -> Path:
    top = git("rev-parse", "--show-toplevel").strip()
    return Path(top) if top else Path.cwd()


def frontmatter(text: str) -> str:
    m = FRONTMATTER_RE.match(text)
    return m.group(1) if m else ""


def parse_list_field(fm: str, name: str) -> list[str] | None:
    """YAML-подмножество: "name:" + block-list, или "name: [a, b]", или "name: []".

    Возвращает None, если поля нет (concept невидим для гейта), и [] если поле
    объявлено пустым (сознательно не привязан к коду).
    """
    inline = re.search(rf"(?m)^{name}:[ \t]*\[(.*?)\][ \t]*$", fm)
    if inline:
        items = [i.strip().strip("\"'") for i in inline.group(1).split(",")]
        return [i for i in items if i]
    block = re.search(rf"(?m)^{name}:[ \t]*$", fm)
    if not block:
        return None
    out: list[str] = []
    for line in fm[block.end() :].splitlines():
        if re.match(r"^[ \t]*-[ \t]*", line):
            out.append(re.sub(r"^[ \t]*-[ \t]*", "", line).strip().strip("\"'"))
        elif line.strip() and not line.startswith((" ", "\t")):
            break  # началось следующее поле верхнего уровня
    return out


def scalar_field(fm: str, name: str) -> str:
    m = re.search(rf"(?m)^{name}:[ \t]*(.+?)[ \t]*$", fm)
    return m.group(1).strip().strip("\"'") if m else ""


def covers(declared: str, changed: str) -> bool:
    """Совпадение пути: точное, префикс каталога или glob-хвост /**."""
    d = declared.strip().lstrip("./").rstrip()
    if d.endswith("/**"):
        d = d[:-3]
    if d.endswith("/*"):
        d = d[:-2]
    d = d.rstrip("/")
    if not d:
        return False
    return changed == d or changed.startswith(d + "/")


def changed_files(base: str | None, staged: bool) -> tuple[list[str], list[str]]:
    """(файлы, проблемы). Пустой список файлов при проблеме = гейт не судит."""
    if staged:
        out = git("diff", "--name-only", "--cached")
        if not out.strip():
            return [], ["nothing staged"]
        return [f for f in out.splitlines() if f], []
    if not base:
        return [], ["no --base and no --staged"]
    if not git("rev-parse", "--verify", "--quiet", base).strip():
        return [], [f"ref '{base}' unavailable (shallow clone? need full history)"]
    merge_base = git("merge-base", base, "HEAD").strip() or base
    out = git("diff", "--name-only", f"{merge_base}..HEAD")
    return [f for f in out.splitlines() if f], []


def status_waiver() -> str:
    """Строка `canon_drift_waiver:` из delivery/active/STATUS.md (пусто = нет)."""
    status = repo_root() / "delivery" / "active" / "STATUS.md"
    if not status.is_file():
        return ""
    m = STATUS_WAIVER_RE.search(status.read_text(encoding="utf-8"))
    if not m:
        return ""
    return re.sub(r"<!--.*?-->", "", m.group(1)).strip().lstrip("*").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="ref to diff against (e.g. origin/main)")
    ap.add_argument("--staged", action="store_true", help="use staged diff")
    ap.add_argument("--check-stale", action="store_true", help="stale_after check")
    args = ap.parse_args()

    root = repo_root()
    bundle = root / BUNDLE
    errors: list[str] = []
    warnings: list[str] = []

    if not bundle.is_dir():
        print(f"okf_sync_gate: no bundle at {BUNDLE}/ — skip (deploy OKF first)")
        return 0

    # --- собрать карту concept -> declared paths
    concepts: dict[str, list[str]] = {}
    stale: list[tuple[str, str]] = []
    # Явный UTC, а не локальная дата: гейт гоняется и на машине автора, и в CI —
    # «просрочен ли stale_after» не должно зависеть от часового пояса раннера.
    today = datetime.now(UTC).date()
    for path in sorted(bundle.rglob("*.md")):
        if path.name in RESERVED:
            continue
        rel = path.relative_to(root).as_posix()
        fm = frontmatter(path.read_text(encoding="utf-8"))
        if not fm:
            continue
        declared = parse_list_field(fm, "implementation")
        if declared:
            concepts[rel] = declared
        after = scalar_field(fm, "stale_after")
        m = DATE_RE.search(after) if after else None
        if m:
            when = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if when < today:
                stale.append((rel, after))

    if args.check_stale:
        for rel, when in stale:
            errors.append(f"{rel}: stale_after {when} is in the past — re-verify or bump")
        if not stale:
            print(f"okf_sync_gate: freshness OK ({len(concepts)} mapped concepts)")
    else:
        for rel, when in stale:
            warnings.append(f"{rel}: stale_after {when} is in the past (§7.2)")

        files, issues = changed_files(args.base, args.staged)
        for i in issues:
            warnings.append(f"cannot compute diff: {i}")
        if not files and not issues:
            # Пустой дифф = гейт ничего не судит. Это законно (push в саму базу),
            # но должно быть видно: молчаливый no-op читается как «проверено».
            warnings.append(f"diff vs '{args.base or 'staged'}' is empty — gate inert this run")
        if files:
            touched_bundle = {f for f in files if f.startswith(f"{BUNDLE}/")}
            code = [f for f in files if f not in touched_bundle]
            for rel, declared in sorted(concepts.items()):
                if rel in touched_bundle:
                    continue  # concept обновлён — синхронизация заявлена
                hits = sorted({c for c in code for d in declared if covers(d, c)})[:5]
                if hits:
                    errors.append(f"{rel}: implementation changed but concept untouched -> {', '.join(hits)}")
            if not concepts:
                warnings.append(
                    "no concept declares implementation: — gate is inert; "
                    "start filling the field (Приложение A.3)"
                )

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)

    if not errors:
        print(f"okf_sync_gate: OK ({len(concepts)} mapped concepts, {len(warnings)} warning(s))")
        return 0
    waiver = status_waiver()
    if ALLOW_DRIFT or waiver:
        source = "ALLOW_CANON_DRIFT=1" if ALLOW_DRIFT else f"STATUS: {waiver}"
        print(
            f"okf_sync_gate: drift allowed ({source}) — {len(errors)} finding(s); "
            f"инварианты обязаны быть не тронуты, иначе это ложное «обновлено»",
            file=sys.stderr,
        )
        return 0
    if not STRICT:
        print(f"okf_sync_gate: WARNING (STRICT=0) — {len(errors)} finding(s)", file=sys.stderr)
        return 0
    if args.check_stale:
        print(
            f"okf_sync_gate: FAIL — {len(errors)} concept(s) past stale_after.\n"
            "Fix: re-verify the canon and set `verified:` + a new `stale_after`, "
            "or mark the concept `status: deprecated` (§7.2).",
            file=sys.stderr,
        )
    else:
        print(
            f"okf_sync_gate: FAIL — {len(errors)} concept(s) out of sync with code.\n"
            "Fix: update the concept + scope log.md, or drop the path from "
            "`implementation:` if it no longer applies (§4.1).",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
