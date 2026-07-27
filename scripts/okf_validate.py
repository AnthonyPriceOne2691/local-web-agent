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


def validate_bundle(root: Path) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    max_lines = int(os.environ.get("OKF_MAX_LINES", "600"))
    max_bytes = int(os.environ.get("OKF_MAX_BYTES", str(80 * 1024)))

    if not root.is_dir():
        print(f"ERROR: bundle root not a directory: {root}", file=sys.stderr)
        return 1

    md_files = sorted(root.rglob("*.md"))
    if not md_files:
        errors.append(f"no markdown files under {root}")

    root_index = root / "index.md"
    if root_index.is_file():
        text = root_index.read_text(encoding="utf-8")
        if "okf_version" not in text:
            warnings.append("root index.md has no okf_version (SPEC §12 recommended)")
    else:
        warnings.append("missing root index.md (optional in SPEC, required by project profile)")

    for path in md_files:
        rel = path.relative_to(root).as_posix()
        name = path.name
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{rel}: not UTF-8")
            continue

        if name in RESERVED:
            if name == "log.md":
                if not re.search(r"(?m)^## \d{4}-\d{2}-\d{2}\s*$", text):
                    warnings.append(f"{rel}: no ## YYYY-MM-DD headings (SPEC §9 shape)")
            continue

        meta, body = parse_frontmatter(text)
        if meta is None:
            errors.append(f"{rel}: missing YAML frontmatter (SPEC §11)")
            continue
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
            target = root / link.lstrip("/")
            if not target.is_file():
                warnings.append(f"{rel}: broken bundle link {link}")

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
