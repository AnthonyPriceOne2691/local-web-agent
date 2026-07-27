#!/usr/bin/env python3
"""AST-гейты для конвенций, которые grep не выразит.

Правила:
  silent-except  — «глухой» broad-except: `except Exception/BaseException/голый:`
                   без raise / логирования / record в теле хендлера (ошибка обязана
                   оставить след). Осознанный fail-soft помечается комментарием
                   `# silent-ok: <причина>` внутри хендлера — тогда сайт легален.
  inline-prompt  — LLM-промпт инлайном в .py: не-docstring строка >= 8 строк,
                   начинающаяся с персона-маркера («Ты — …», "You are …", …).
                   Порог по маркеру, не по длине: длинные SQL/Lua/regex легитимны.

Механика — per-file baseline-ratchet: легаси в снимке (`<count>:<path>`, путь от
repo-root); файл проходит при count <= снимок; файл вне снимка (любой новый) — hard 0.
Пересъём вниз: --generate.

Настройка (env):
  LINT_PY_SRC — корневой каталог прод-Python для гейтов, от repo-root (дефолт: backend/features)

Запуск (скрипт лежит в <repo-root>/scripts/lint/):
  python scripts/lint/check_ast_gate.py --rule silent-except
  python scripts/lint/check_ast_gate.py --rule silent-except --generate
  STRICT=0 …  — soft-режим (warning, exit 0), аварийно.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

FEATURES = Path(os.environ.get("LINT_PY_SRC", "backend/features"))
# Адаптация под этот проект (CQG «Применимость»): LINT_PY_SRC=. покрывает весь репо
# (прод-код лежит в backend/app И cli/), а venv/node_modules лежат ВНУТРИ дерева —
# rglob затянул бы site-packages в baseline (168 чужих записей на первом прогоне).
SKIP_PARTS = ("/tests/", "/migrations/", "/.venv/", "/site-packages/", "/node_modules/")
SILENT_OK_MARKER = "# silent-ok:"

_LOG_BASES = {"logger", "logging", "log", "warnings"}
_LOG_ATTR_PREFIXES = ("log", "warn", "exception", "error", "record", "capture", "notify")
_PROMPT_MARKERS = ("ты —", "ты -", "you are", "you classify", "act as", "роль:", "system:")
_PROMPT_MIN_LINES = 8


def _is_broad(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    if t is None:
        return True
    if isinstance(t, ast.Name) and t.id in ("Exception", "BaseException"):
        return True
    if isinstance(t, ast.Tuple):
        return any(isinstance(e, ast.Name) and e.id in ("Exception", "BaseException") for e in t.elts)
    return False


def _handler_leaves_trace(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                base = func.value
                if isinstance(base, ast.Name) and base.id in _LOG_BASES:
                    return True
                if func.attr.startswith(_LOG_ATTR_PREFIXES):
                    return True
            if isinstance(func, ast.Name) and func.id.startswith(("log", "record", "capture", "notify")):
                return True
    return False


def _handler_has_silent_ok(handler: ast.ExceptHandler, src_lines: list[str]) -> bool:
    end = handler.body[-1].end_lineno if handler.body else handler.lineno
    for i in range(handler.lineno - 1, min(end, len(src_lines))):
        if SILENT_OK_MARKER in src_lines[i]:
            return True
    return False


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def find_silent_except(tree: ast.AST, src_lines: list[str]) -> list[int]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_broad(node) and not _handler_leaves_trace(node) and not _handler_has_silent_ok(node, src_lines):
            out.append(node.lineno)
    return out


def find_inline_prompt(tree: ast.AST, src_lines: list[str]) -> list[int]:  # noqa: ARG001
    doc_ids = _docstring_ids(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids:
            if node.value.count("\n") + 1 < _PROMPT_MIN_LINES:
                continue
            head = node.value.strip().lower()
            if head.startswith(_PROMPT_MARKERS):
                out.append(node.lineno)
    return out


RULES = {
    "silent-except": {
        "find": find_silent_except,
        "baseline": "silent_except_baseline.txt",
        "label": "silent-except: broad-except без raise/лога",
        "hint": "Оставь след: logger.warning/exception с контекстом, либо пробрось. Осознанный fail-soft — пометь `# silent-ok: <причина>` в хендлере.",
    },
    "inline-prompt": {
        "find": find_inline_prompt,
        "baseline": "inline_prompt_baseline.txt",
        "label": "inline-prompt: LLM-промпт инлайном в .py",
        "hint": "Промпт — в отдельный <name>.md + lazy-load, не строкой в коде.",
    },
}


def iter_target_files(repo_root: Path):
    for path in sorted((repo_root / FEATURES).rglob("*.py")):
        rel = path.as_posix()
        if any(part in rel for part in SKIP_PARTS):
            continue
        if path.name.startswith("test_") or path.name == "conftest.py":
            continue
        yield path


def repo_rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def load_baseline(baseline_path: Path) -> dict[str, int]:
    snap: dict[str, int] = {}
    if not baseline_path.is_file():
        return snap
    for line in baseline_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or ":" not in line:
            continue
        count, _, p = line.partition(":")
        if count.isdigit():
            snap[p] = int(count)
    return snap


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule", required=True, choices=sorted(RULES))
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()

    strict = os.environ.get("STRICT", "1") == "1"
    rule = RULES[args.rule]

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent  # <repo-root>/scripts/lint/ -> repo-root
    baseline_path = script_dir / rule["baseline"]

    counts: dict[str, int] = {}
    for path in iter_target_files(repo_root):
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        hits = rule["find"](tree, src.splitlines())
        if hits:
            counts[repo_rel(path, repo_root)] = len(hits)

    if args.generate:
        lines = [
            f"# {rule['baseline']} — снимок AST-гейта. Генерируется --generate, НЕ руками.",
            f"# Правило: {rule['label']}",
            "# Формат: <count>:<path> (path от repo-root). Ратчет вниз: файл проходит при count <= снимок;",
            "# файл ВНЕ снимка (новый) — hard 0.",
        ]
        lines += [f"{c}:{p}" for p, c in sorted(counts.items())]
        baseline_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"baseline пересобран: {baseline_path.name} ({len(counts)} файлов, {sum(counts.values())} сайтов)")
        return 0

    snap = load_baseline(baseline_path)
    violations = []
    for p, c in sorted(counts.items()):
        allowed = snap.get(p, 0)
        if c > allowed:
            violations.append((p, c, allowed))

    if violations:
        mark = "✗" if strict else "⚠"
        for p, c, allowed in violations:
            print(f"  {mark}  {p}: {c} нарушений (разрешено {allowed})")
        print(f"\n{'ERROR' if strict else 'WARNING'}: {len(violations)} файл(ов) нарушают правило {args.rule}.")
        print(rule["hint"])
        print("Легаси из baseline — ок до чистки; новый код держим на нуле. Пересъём вниз: --generate.")
        return 1 if strict else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
