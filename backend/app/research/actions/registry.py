"""Реестр действий Layer 2 (A-H1) — единственный источник правды для tools.

Новое действие = модуль в `research/actions/` c `register(ActionSpec(...))` +
описание для meta-промпта в `data/prompts/tools/<name>.txt` (промпты в data/,
не в коде — doc 18). Runner и llm_planner ходят только через реестр:
незарегистрированное имя отбрасывается (M-H1 как точка расширения, doc 25).
"""

from __future__ import annotations

from pathlib import Path

from app.research.actions.base import ActionSpec

_REGISTRY: dict[str, ActionSpec] = {}


def register(spec: ActionSpec) -> ActionSpec:
    """Дубль имени — ошибка конфигурации, падаем сразу (fail fast, doc 13)."""
    if spec.name in _REGISTRY:
        raise ValueError(f"action '{spec.name}' already registered")
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> ActionSpec | None:
    return _REGISTRY.get(name)


def names() -> tuple[str, ...]:
    return tuple(_REGISTRY)


def prompt_block(prompts_dir: Path) -> str:
    """Блок «Available tools» meta-промпта — по файлу на действие.

    Отсутствие файла-описания у зарегистрированного действия — ошибка
    конфигурации (fail fast): LLM не должен видеть неполный список.
    """
    lines = []
    for name in _REGISTRY:
        lines.append((prompts_dir / "tools" / f"{name}.txt")
                     .read_text(encoding="utf-8").strip())
    return "\n".join(lines)
