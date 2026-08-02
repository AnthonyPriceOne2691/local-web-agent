#!/usr/bin/env python3
"""Self-test for the canon stack: every fenced code block must parse.

Usage:
  python stack_selftest.py [dir]

Проверяет:
  * python-блоки  -> ast.parse
  * bash-блоки    -> bash -n
  * yaml-блоки    -> yaml.safe_load (или запрет табов, если PyYAML нет)
  * сбалансированность ``` в каждом файле
  * версии в шапках канонов == таблица §1 в AGENT_STACK.md

Exit 0 = всё чисто. Exit 1 = хоть один блок не парсится / версии разошлись.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

CANONS = (
    "AGENT_STACK.md",
    "AGENT_DELIVERY_HARNESS.md",
    "CODE_QUALITY_GATES.md",
    "OKF_KNOWLEDGE_BUNDLE.md",
)
CHECKED_LANGS = {"python", "bash", "sh", "yaml", "yml"}


def blocks(text: str) -> tuple[list[tuple[int, str, str]], int]:
    """[(line_no, lang, code)] + число незакрытых фенсов.

    Сканер построчный, а не regex: вложенный фенс в шаблоне рассинхронизировал бы
    регулярку молча, а несбалансированность мы хотим видеть как ошибку.
    """
    out: list[tuple[int, str, str]] = []
    lang: str | None = None
    start = 0
    buf: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.startswith("```"):
            if lang is not None:
                buf.append(line)
            continue
        if lang is None:  # открытие
            lang, start, buf = line[3:].strip().lower(), i, []
        else:  # закрытие
            out.append((start, lang, "\n".join(buf)))
            lang = None
    return out, (1 if lang is not None else 0)


def check_yaml(code: str) -> str | None:
    try:
        import yaml  # type: ignore
    except ImportError:
        # Без PyYAML ловим самое частое: таб в отступе YAML запрещён спекой.
        for n, line in enumerate(code.splitlines(), 1):
            if line[:1] == "\t" or (line.strip() and "\t" in line[: len(line) - len(line.lstrip())]):
                return f"tab indentation at line {n} (YAML forbids tabs)"
        return None
    try:
        # safe_load_all, а не safe_load: блоки-шаблоны frontmatter обрамлены `---`,
        # то есть являются потоком из нескольких YAML-документов, и одиночный
        # safe_load ронял их с ComposerError (ложное срабатывание).
        list(yaml.safe_load_all(code))
    except Exception as exc:  # любая ошибка парсера = провал блока
        # silent-ok: ошибка не теряется — текст возвращается вызывающему и печатается
        # как FAIL в отчёте; логгера у одноразового CLI-скрипта нет.
        return f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
    return None


def declared_versions(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """(версии из шапок канонов, версии из таблицы §1 карты)."""
    heads: dict[str, str] = {}
    for name in CANONS[1:]:
        p = root / name
        if not p.is_file():
            continue
        m = re.search(r"\*\*Canon version:\*\*\s*`([a-z]+)@([\d.]+)`", p.read_text(encoding="utf-8"))
        if m:
            heads[m.group(1)] = m.group(2)
    table: dict[str, str] = {}
    smap = root / CANONS[0]
    if smap.is_file():
        for m in re.finditer(r"\|\s*`([a-z]+)@([\d.]+)`\s*\|", smap.read_text(encoding="utf-8")):
            table[m.group(1)] = m.group(2)
    return heads, table


def check_block(lang: str, code: str) -> str | None:
    """Синтаксис одного блока: None = валиден, строка = текст ошибки."""
    if lang == "python":
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return f"SyntaxError: {exc.msg} (block line {exc.lineno})"
        return None
    if lang in {"bash", "sh"}:
        proc = subprocess.run(["bash", "-n"], input=code, text=True, capture_output=True, check=False)
        if proc.returncode:
            return proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "bash -n failed"
        return None
    return check_yaml(code)


def check_canon(path: Path, name: str) -> tuple[list[str], int]:
    """(провалы, сколько блоков проверено) для одного файла канона."""
    failures: list[str] = []
    text = path.read_text(encoding="utf-8")
    found, unbalanced = blocks(text)
    if unbalanced:
        failures.append(f"{name}: unbalanced ``` fence (unterminated block)")
    checked = 0
    for line_no, lang, code in found:
        if lang not in CHECKED_LANGS or not code.strip():
            continue
        checked += 1
        err = check_block(lang, code)
        if err:
            failures.append(f"{name}:{line_no} [{lang}] {err}")
    print(f"{name}: {checked} executable block(s) checked")
    return failures, checked


def check_versions(root: Path) -> list[str]:
    """Версия в шапке канона обязана совпадать с таблицей §1 карты стека."""
    failures: list[str] = []
    heads, table = declared_versions(root)
    for layer, ver in heads.items():
        if layer in table and table[layer] != ver:
            failures.append(
                f"version skew: {layer}@{ver} in canon header vs {layer}@{table[layer]} "
                f"in {CANONS[0]} §1 table"
            )
    missing = sorted(set(table) - set(heads))
    if missing:
        print(f"note: no Canon version header for {', '.join(missing)}")
    return failures


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    failures: list[str] = []
    total = 0

    for name in CANONS:
        path = root / name
        if not path.is_file():
            failures.append(f"{name}: MISSING")
            continue
        canon_failures, checked = check_canon(path, name)
        failures += canon_failures
        total += checked

    failures += check_versions(root)

    print(f"\nstack_selftest: {total} block(s), {len(failures)} failure(s)")
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
