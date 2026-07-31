"""DECIDE-стадия: предложение действия навигатором + валидация + recovery.

Вынесено из loop.py ради ≤500 LOC (doc 18) — четвёртый вынос после attended /
interaction / capture / discovery. Тема модуля: **как из кандидатов получается
одно валидное действие** — replan при hard-violation, drift auto-tighten
(doc 13 § Drift detection) и детерминированный fallback на link scorer.
Сама машина состояний осталась в loop.py.
"""

from __future__ import annotations

from typing import Any

from app.contracts.context import build_action_context
from app.contracts.enforcer import ContractEnforcer
from app.llm.model_router import NavRouting
from app.llm.navigator import Navigator
from app.observer.links import normalize_url
from app.orchestrator.robots import RobotsPolicy
from app.schemas.run import RunRecord, Violation
from app.schemas.snapshot import AgentAction, Candidate, PageSnapshot

# Drift auto-tighten (doc 13 § Drift detection)
DRIFT_HARD_FOR_LOW_TEMP = 3  # hard violations ≥ 3/run → nav temperature 0.4 → 0.2
DRIFT_IH6_FOR_TOP5 = 2  # fabricated URL ≥ 2 → shrink candidate list to top 5
DRIFT_MIN_RECOVERIES = 2  # recovery success < 50% (при ≥2 попытках) → fallback-only


async def plan_validated(
    record: RunRecord,
    current: PageSnapshot,
    candidates: list[Candidate],
    visited: set[str],
    hops: dict[str, int],
    origin: str,
    pages_left: int,
    robots: RobotsPolicy,
    *,
    navigator: Navigator,
    enforcer: ContractEnforcer,
    routing: NavRouting | None = None,
) -> tuple[AgentAction, list[Violation], dict[str, Any]]:
    violations: list[Violation] = []
    llm_stats: dict[str, Any] = {}
    retry_note = ""
    drift = record.metadata.setdefault(
        "drift", {"hard_total": 0, "ih6": 0, "replan_ok": 0, "replan_fail": 0, "fallbacks": 0}
    )
    cands = candidates[: 5 if drift["ih6"] >= DRIFT_IH6_FOR_TOP5 else None]
    ctx = build_action_context(record, current, cands, visited, hops, origin, robots)

    replans_used = 0
    if not _fallback_only(drift):
        for attempt in range(enforcer.max_replans_per_step + 1):
            temperature = 0.2 if drift["hard_total"] >= DRIFT_HARD_FOR_LOW_TEMP else 0.4
            action, llm_stats = await navigator.propose(
                task=record.config.task,
                intent=record.intent,
                snapshot=current,
                candidates=cands,
                visited=visited,
                pages_left=pages_left,
                retry_note=retry_note,
                temperature=temperature,
                attended=record.config.attended,
                destructive_signals=enforcer.destructive_signals,
                model=_nav_model(routing, record, current, replanning=attempt > 0),
            )
            replans_used = attempt
            if action is None:  # I-H7 invalid schema
                violations.append(
                    Violation(constraint_id="I-H7", message="unparseable action", recovered=False)
                )
                drift["hard_total"] += 1
                retry_note = "response was not valid action JSON"
                continue
            if action.action in ("extract_now", "stop"):
                _mark_recovered(violations, replans_used, drift)
                return action, violations, llm_stats
            # click→I-H10, fill→I-H11, иначе navigate-shield (doc 25)
            _validate = {
                "click": enforcer.validate_click,
                "fill": enforcer.validate_fill,
                "fill_form": enforcer.validate_fill,  # I-H11 по каждому полю пачки
            }
            hard, softs = _validate.get(action.action, enforcer.validate_navigate)(action, ctx)
            violations.extend(softs)
            if hard is None:
                _mark_recovered(violations, replans_used, drift)
                return action, violations, llm_stats
            violations.append(hard)
            drift["hard_total"] += 1
            if hard.constraint_id == "I-H6":
                drift["ih6"] += 1
                if drift["ih6"] >= DRIFT_IH6_FOR_TOP5:  # auto-tighten: top-5 (doc 13)
                    cands = cands[:5]
                    ctx.candidates = {normalize_url(c.href) for c in cands}
            if hard.constraint_id == "G-H1":  # budget → форс stop, не replan
                return (
                    AgentAction(action="stop", reasoning="page budget exhausted"),
                    violations,
                    llm_stats,
                )
            retry_note = f"{hard.constraint_id}: {hard.message}"
        drift["replan_fail"] += 1

    # fallback: детерминированный link scorer (recovery R2, doc 13)
    drift["fallbacks"] += 1
    for cand in candidates:
        fallback = AgentAction(action="navigate", url=cand.href, reasoning="fallback: top candidate")
        hard, _ = enforcer.validate_navigate(fallback, ctx)
        if hard is None:
            for v in violations:
                v.recovered = True
            return fallback, violations, llm_stats
    return AgentAction(action="stop", reasoning="no valid candidates"), violations, llm_stats


def _nav_model(
    routing: NavRouting | None,
    record: RunRecord,
    current: PageSnapshot,
    *,
    replanning: bool,
) -> str:
    """Лёгкая или тяжёлая модель на это решение (doc 16 § Маршрутизация).

    `routing is None` → маршрутизация не настроена, `""` = канонная nav-модель
    навигатора (поведение до поставки `nav-model-split`).
    """
    if routing is None:
        return ""
    return routing.pick(
        task=record.config.task,
        snapshot=current,
        steps=[(s.state, s.action, s.url) for s in record.steps],
        replanning=replanning,
    )


def _fallback_only(drift: dict[str, Any]) -> bool:
    """Recovery success < 50% при ≥2 попытках → link_scorer до конца run (doc 13)."""
    ok, fail = int(drift["replan_ok"]), int(drift["replan_fail"])
    attempts = ok + fail
    return attempts >= DRIFT_MIN_RECOVERIES and ok / attempts < 0.5


def _mark_recovered(violations: list[Violation], replans_used: int, drift: dict[str, Any]) -> None:
    if not violations:
        return
    for v in violations:
        v.recovered = True
    if replans_used > 0:
        drift["replan_ok"] += 1
