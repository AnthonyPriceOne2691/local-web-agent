"""ContractSpec loader (doc 13, paper §5): YAML → ContractSpec.

Декларативный DSL, не Turing-complete: только named checks из contracts/rules/;
unknown check — ошибка загрузки (fail fast на старте приложения).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from app.contracts.rules import KNOWN_CHECKS

_RESERVED_KEYS = ("id", "check", "code", "owner")


class ContractRule(BaseModel):
    id: str
    check: str
    code: str = ""  # constraint_id для violation log (I-H1, G-H5, …); default = id
    severity: Literal["hard", "soft"] = "hard"
    owner: Literal["enforcer", "orchestrator"] = "enforcer"
    params: dict[str, Any] = Field(default_factory=dict)


class ContractSpec(BaseModel):
    mode: str
    version: str = "1.0"
    source: str = ""
    preconditions: list[ContractRule] = Field(default_factory=list)
    invariants_hard: list[ContractRule] = Field(default_factory=list)
    invariants_soft: list[ContractRule] = Field(default_factory=list)
    governance_hard: list[ContractRule] = Field(default_factory=list)
    governance_soft: list[ContractRule] = Field(default_factory=list)
    recovery: dict[str, Any] = Field(default_factory=dict)


def _parse_rules(raw_list: list[dict[str, Any]] | None, severity: str, *, path: Path) -> list[ContractRule]:
    rules: list[ContractRule] = []
    for raw in raw_list or []:
        known = {k: raw[k] for k in _RESERVED_KEYS if k in raw}
        params = {k: v for k, v in raw.items() if k not in _RESERVED_KEYS}
        rule = ContractRule(**known, severity=severity, params=params)
        if rule.check not in KNOWN_CHECKS:
            raise ValueError(f"{path.name}: unknown check '{rule.check}' in rule '{rule.id}'")
        rule.code = rule.code or rule.id
        rules.append(rule)
    return rules


def load_contract(path: Path) -> ContractSpec:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    invariants = data.get("invariants") or {}
    governance = data.get("governance") or {}
    return ContractSpec(
        mode=data.get("mode", ""),
        version=str(data.get("version", "1.0")),
        source=data.get("source", ""),
        preconditions=_parse_rules(data.get("preconditions"), "hard", path=path),
        invariants_hard=_parse_rules(invariants.get("hard"), "hard", path=path),
        invariants_soft=_parse_rules(invariants.get("soft"), "soft", path=path),
        governance_hard=_parse_rules(governance.get("hard"), "hard", path=path),
        governance_soft=_parse_rules(governance.get("soft"), "soft", path=path),
        recovery=data.get("recovery") or {},
    )


def load_forbidden_paths(path: Path) -> tuple[str, ...]:
    """crawl_forbidden.txt → substrings (без комментариев/пустых строк)."""
    if not path.is_file():
        return ()
    lines = (ln.strip() for ln in path.read_text(encoding="utf-8").splitlines())
    return tuple(ln.lower() for ln in lines if ln and not ln.startswith("#"))
