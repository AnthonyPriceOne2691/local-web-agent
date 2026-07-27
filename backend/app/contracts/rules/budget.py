"""Governance checks (doc 13): G-H1/G-H2/G-H5 per-action + config-floor'ы G-H4/G-H6.

Config-check: fn(code, params, config) -> Violation | None (на старте run).
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.contracts.context import ActionContext
from app.observer.links import is_private_host
from app.schemas.run import RunConfig, Violation
from app.schemas.snapshot import AgentAction

# ---------------------------------------------------------------- per-action


def pages_budget(code: str, params: dict, action: AgentAction, ctx: ActionContext) -> Violation | None:
    if ctx.pages_visited >= ctx.max_pages:
        return Violation(constraint_id=code, message="page budget exhausted", proposed_url=action.url)
    return None


def hop_depth(code: str, params: dict, action: AgentAction, ctx: ActionContext) -> Violation | None:
    if ctx.hops.get(ctx.current_url, 0) + 1 > ctx.max_depth:
        return Violation(constraint_id=code, message="hop depth exceeded", proposed_url=action.url)
    return None


def robots_allowed(code: str, params: dict, action: AgentAction, ctx: ActionContext) -> Violation | None:
    if ctx.robots is not None and not ctx.robots.allowed(action.url or ""):
        return Violation(constraint_id=code, message="robots.txt disallow", proposed_url=action.url)
    return None


# -------------------------------------------------------------- config-time


def url_scheme(code: str, params: dict, config: RunConfig) -> Violation | None:
    scheme = urlparse(config.start_url).scheme.lower()
    if scheme not in params.get("allowed", ("http", "https")):
        return Violation(constraint_id=code, message=f"start_url scheme '{scheme}' not allowed")
    return None


def non_empty(code: str, params: dict, config: RunConfig) -> Violation | None:
    value = str(getattr(config, params.get("field", "task"), "") or "")
    if not value.strip():
        return Violation(constraint_id=code, message=f"field '{params.get('field')}' is empty")
    return None


def rate_limit_floor(code: str, params: dict, config: RunConfig) -> Violation | None:
    """G-H4: floor для публичных хостов (enforcement = clamp в effective_rate_ms);
    private/fixtures exempt. Violation — soft-лог о поднятии."""
    floor = int(params.get("min_delay", 0))
    if params.get("exempt") == "private_hosts" and is_private_host(config.start_url):
        return None
    if config.rate_limit_ms < floor:
        return Violation(
            constraint_id=code,
            severity="soft",
            message=f"rate_limit_ms {config.rate_limit_ms} raised to floor {floor}",
        )
    return None


def page_timeout_ceiling(code: str, params: dict, config: RunConfig) -> Violation | None:
    """G-H6: ceiling; enforcement = clamp (enforcer.effective_timeout_ms)."""
    ceiling = int(params.get("max", 0))
    configured = int(getattr(config, "page_timeout_ms", 0) or 0)
    if ceiling and configured > ceiling:
        return Violation(constraint_id=code, severity="soft", message=f"page timeout capped at {ceiling} ms")
    return None
