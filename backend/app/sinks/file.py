"""Локальный file-sink (Tier 0, doc 25): экспорт результата в markdown-файл.

Локальный sink не покидает машину → consent не нужен (cloud carve-out — только
про облако). Пишем строго внутрь каталога артефактов сессии: имя от LLM
санитизируется до basename (никаких путей), коллизия имён → суффикс -2, -3…
"""

from __future__ import annotations

import re
from pathlib import Path

_UNSAFE_CHARS = re.compile(r"[^\w\- .]", re.UNICODE)


def _safe_name(filename: str | None, title: str) -> str:
    base = Path(filename).name if filename else title  # filename как путь → basename
    base = _UNSAFE_CHARS.sub("", base).strip(" .") or "export"
    return base if base.endswith(".md") else f"{base}.md"


def export_to_file(
    title: str, text: str, *, out_dir: Path, filename: str | None = None,
) -> Path:
    """Записать `# title + text` в out_dir, вернуть путь к файлу."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / _safe_name(filename, title)
    stem, n = path.stem, 2
    while path.exists():
        path = out_dir / f"{stem}-{n}.md"
        n += 1
    path.write_text(f"# {title}\n\n{text}\n", encoding="utf-8")
    return path
