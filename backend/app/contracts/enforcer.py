"""ContractEnforcer (doc 13): shield между LLM и Playwright.

Ни одно не-валидированное действие не попадает в browser. Порядок hard-проверок
фиксирован приоритетом кодов (G-H1 первым — budget форсит stop, не replan).
"""

from __future__ import annotations

from pathlib import Path

from app.contracts.context import ActionContext
from app.contracts.loader import ContractSpec, load_contract, load_forbidden_paths
from app.contracts.rules import ACTION_CHECKS, CONFIG_CHECKS
from app.schemas.run import RunConfig, Violation
from app.schemas.snapshot import AgentAction

# G-H1 до I-H6: при исчерпанном бюджете нужен force-stop, а не replan (doc 13 § Recovery)
_PRIORITY = {"G-H1": 0, "I-H6": 1, "I-H1": 2, "I-H8": 3, "I-H2": 4, "G-H3": 5, "G-H2": 6, "G-H5": 7}


class ContractEnforcer:
    def __init__(self, spec: ContractSpec, forbidden_paths: tuple[str, ...] = ()):
        self.spec = spec
        self.forbidden_paths = forbidden_paths
        # свои пути, не в navigate-shield
        _routed = ("click_not_destructive", "click_target_safe", "fill_target_safe")
        enforced = [
            r for r in (spec.governance_hard + spec.invariants_hard)
            if r.check in ACTION_CHECKS and r.check not in _routed
        ]
        enforced.sort(key=lambda r: _PRIORITY.get(r.code, 99))
        self._action_hard = enforced
        self._click_hard = [  # I-H12 → I-H10 (порядок YAML): navigate-проверки к click неприменимы
            r for r in (spec.invariants_hard + spec.governance_hard)
            if r.check in ("click_not_destructive", "click_target_safe")
        ]
        self._fill_hard = [  # I-H11: fill-safety (текстовые поля, не password)
            r for r in (spec.invariants_hard + spec.governance_hard)
            if r.check == "fill_target_safe"
        ]
        self._action_soft = [
            r for r in (spec.invariants_soft + spec.governance_soft) if r.check in ACTION_CHECKS
        ]
        self._config_rules = [
            r for r in (spec.preconditions + spec.governance_hard + spec.governance_soft)
            if r.check in CONFIG_CHECKS
        ]

    @classmethod
    def load(cls, contracts_dir: Path) -> ContractEnforcer:
        spec = load_contract(contracts_dir / "crawl.contract.yaml")
        forbidden = load_forbidden_paths(contracts_dir / "crawl_forbidden.txt")
        return cls(spec, forbidden)

    # ------------------------------------------------------------ run start
    def check_run_config(self, config: RunConfig) -> list[Violation]:
        """Preconditions P-1/P-2 + config governance. Hard → run не стартует."""
        out: list[Violation] = []
        for rule in self._config_rules:
            violation = CONFIG_CHECKS[rule.check](rule.code, rule.params, config)
            if violation is not None:
                violation.severity = violation.severity if violation.severity == "soft" else rule.severity
                out.append(violation)
        return out

    def effective_rate_ms(self, config_rate_ms: int, start_url: str) -> int:
        """G-H4 enforcement by construction: floor для публичных хостов."""
        from app.observer.links import is_private_host

        rule = self._rule("rate_limit_floor")
        if rule is None:
            return config_rate_ms
        if rule.params.get("exempt") == "private_hosts" and is_private_host(start_url):
            return config_rate_ms
        return max(config_rate_ms, int(rule.params.get("min_delay", 0)))

    def effective_timeout_ms(self, configured_ms: int) -> int:
        """G-H6 enforcement: ceiling."""
        rule = self._rule("page_timeout_ceiling")
        ceiling = int(rule.params.get("max", 0)) if rule else 0
        return min(configured_ms, ceiling) if ceiling else configured_ms

    # ---------------------------------------------------------- per action
    def validate_navigate(
        self, action: AgentAction, ctx: ActionContext
    ) -> tuple[Violation | None, list[Violation]]:
        """(hard_violation | None, soft_violations). Hard → действие отклонено."""
        if not ctx.forbidden_paths:
            ctx.forbidden_paths = self.forbidden_paths
        for rule in self._action_hard:
            violation = ACTION_CHECKS[rule.check](rule.code, rule.params, action, ctx)
            if violation is not None:
                violation.severity = "hard"
                violation.recovered = False  # recovery выставит orchestrator
                return violation, []
        softs: list[Violation] = []
        for rule in self._action_soft:
            violation = ACTION_CHECKS[rule.check](rule.code, rule.params, action, ctx)
            if violation is not None:
                violation.severity = "soft"
                softs.append(violation)
        return None, softs

    def validate_click(
        self, action: AgentAction, ctx: ActionContext
    ) -> tuple[Violation | None, list[Violation]]:
        """I-H10 click-safety: только click-правила (URL-инварианты к click неприменимы)."""
        for rule in self._click_hard:
            violation = ACTION_CHECKS[rule.check](rule.code, rule.params, action, ctx)
            if violation is not None:
                violation.severity = "hard"
                violation.recovered = False
                return violation, []
        return None, []

    def validate_fill(
        self, action: AgentAction, ctx: ActionContext
    ) -> tuple[Violation | None, list[Violation]]:
        """I-H11 fill-safety: только fill-правила (текстовые поля, не password)."""
        for rule in self._fill_hard:
            violation = ACTION_CHECKS[rule.check](rule.code, rule.params, action, ctx)
            if violation is not None:
                violation.severity = "hard"
                violation.recovered = False
                return violation, []
        return None, []

    # ------------------------------------------------------------ recovery
    @property
    def max_replans_per_step(self) -> int:
        return int(self.spec.recovery.get("max_replan_per_step", 2))

    @property
    def destructive_signals(self) -> tuple[str, ...]:
        """I-H12 словарь (Tier 3, doc 25) — для handoff-развилки в ACT."""
        for rule in self._click_hard:
            if rule.check == "click_not_destructive":
                return tuple(str(s).casefold()
                             for s in rule.params.get("destructive_signals", ()))
        return ()

    def _rule(self, check: str):
        for rule in (self.spec.governance_hard + self.spec.governance_soft
                     + self.spec.invariants_hard + self.spec.invariants_soft
                     + self.spec.preconditions):
            if rule.check == check:
                return rule
        return None
