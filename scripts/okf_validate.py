#!/usr/bin/env python3
"""OKF bundle soft validator (project profile + SPEC §11 subset).

Usage:
  python scripts/okf_validate.py                 # bundle=knowledge/
  python scripts/okf_validate.py path/to/bundle
  OKF_MAX_LINES=600 python scripts/okf_validate.py

Exit 0 = no errors (warnings allowed). Exit 1 = conformance errors.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

RESERVED = {"index.md", "log.md"}

# (ошибки, предупреждения) — общий тип всех проверок, поэтому их можно складывать.
Report = tuple[list[str], list[str]]
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
TYPE_RE = re.compile(r"(?m)^type:\s*(.+?)\s*$")


def parse_frontmatter(text: str) -> tuple[dict[str, str] | None, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    raw = m.group(1)
    meta: dict[str, str] = {}
    # minimal: only need type; ignore nested YAML complexity
    tm = TYPE_RE.search(raw)
    if tm:
        meta["type"] = tm.group(1).strip().strip("\"'")
    meta["_raw"] = raw
    return meta, text[m.end() :]


def check_root_index(root: Path) -> Report:
    """index.md — мягкое правило SPEC, но обязательное по профилю проекта."""
    root_index = root / "index.md"
    if not root_index.is_file():
        return [], ["missing root index.md (optional in SPEC, required by project profile)"]
    if "okf_version" not in root_index.read_text(encoding="utf-8"):
        return [], ["root index.md has no okf_version (SPEC §12 recommended)"]
    return [], []


def check_reserved(rel: str, name: str, text: str) -> Report:
    """index.md / log.md проверяются по форме, а не как concept'ы."""
    if name == "log.md" and not re.search(r"(?m)^## \d{4}-\d{2}-\d{2}\s*$", text):
        return [], [f"{rel}: no ## YYYY-MM-DD headings (SPEC §9 shape)"]
    return [], []


def check_concept(root: Path, path: Path, rel: str, text: str) -> Report:
    """Один concept: frontmatter (жёстко) + объём и ссылки (мягко)."""
    max_lines = int(os.environ.get("OKF_MAX_LINES", "600"))
    max_bytes = int(os.environ.get("OKF_MAX_BYTES", str(80 * 1024)))

    meta, body = parse_frontmatter(text)
    if meta is None:
        return [f"{rel}: missing YAML frontmatter (SPEC §11)"], []

    errors: list[str] = []
    warnings: list[str] = []
    if not meta.get("type"):
        errors.append(f"{rel}: frontmatter missing non-empty type (SPEC §11)")

    lines = body.count("\n") + (1 if body and not body.endswith("\n") else 0)
    size = path.stat().st_size
    if lines > max_lines:
        warnings.append(f"{rel}: body ~{lines} lines > soft max {max_lines} (split?)")
    if size > max_bytes:
        warnings.append(f"{rel}: {size} bytes > soft max {max_bytes} (split?)")

    # bundle-absolute links existence (soft)
    for link in re.findall(r"\[[^\]]*\]\((/[^)]+?\.md)\)", body):
        if not (root / link.lstrip("/")).is_file():
            warnings.append(f"{rel}: broken bundle link {link}")

    return errors, warnings


def check_file(root: Path, path: Path) -> Report:
    rel = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"{rel}: not UTF-8"], []
    if path.name in RESERVED:
        return check_reserved(rel, path.name, text)
    return check_concept(root, path, rel, text)


def validate_bundle(root: Path) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not root.is_dir():
        print(f"ERROR: bundle root not a directory: {root}", file=sys.stderr)
        return 1

    md_files = sorted(root.rglob("*.md"))
    if not md_files:
        errors.append(f"no markdown files under {root}")

    for errs, warns in [check_root_index(root), *(check_file(root, p) for p in md_files)]:
        errors += errs
        warnings += warns

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)

    print(
        f"okf_validate: {len(errors)} error(s), {len(warnings)} warning(s), "
        f"files={len(md_files)}, root={root}"
    )
    return 1 if errors else 0


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "knowledge")
    return validate_bundle(root.resolve())


if __name__ == "__main__":
    sys.exit(main())
