"""URL/action checks (doc 13): I-H1, I-H2, I-H6, I-H8, G-H3, I-S2.

Сигнатура action-check: fn(code, params, action, ctx) -> Violation | None.
Все проверки O(1)/O(n_paths), < 1 ms (paper Prop. 4.15).
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.contracts.context import ActionContext
from app.observer.links import is_private_host, normalize_url, same_site
from app.schemas.run import Violation
from app.schemas.snapshot import AgentAction


def url_in_allowed_domains(
    code: str, params: dict, action: AgentAction, ctx: ActionContext
) -> Violation | None:
    target = normalize_url(action.url or "")
    if not same_site(target, ctx.origin):
        return Violation(constraint_id=code, message="target outside allowed site",
                         proposed_url=target)
    return None


def url_in_candidate_queue(
    code: str, params: dict, action: AgentAction, ctx: ActionContext
) -> Violation | None:
    target = normalize_url(action.url or "")
    if "start_url" in params.get("except", []) and target == normalize_url(ctx.start_url):
        return None
    if target not in ctx.candidates:
        return Violation(constraint_id=code, message="url not in candidate queue",
                         proposed_url=target)
    return None


def public_http_url(
    code: str, params: dict, action: AgentAction, ctx: ActionContext
) -> Violation | None:
    target = action.url or ""
    if urlparse(target).scheme not in ("http", "https"):
        return Violation(constraint_id=code, message="scheme not http(s)", proposed_url=target)
    if ctx.allow_private:  # override_flag: allow_private (--allow-private)
        return None
    # private origin (fixtures) может ходить по своему private-хосту — same_site решает I-H1
    if is_private_host(target) and not is_private_host(ctx.origin):
        return Violation(constraint_id=code, message="private network target",
                         proposed_url=target)
    return None


def action_not_in(
    code: str, params: dict, action: AgentAction, ctx: ActionContext
) -> Violation | None:
    if action.action in params.get("forbidden", ()):
        return Violation(constraint_id=code, message=f"forbidden action '{action.action}'")
    return None


def url_not_visited(
    code: str, params: dict, action: AgentAction, ctx: ActionContext
) -> Violation | None:
    target = normalize_url(action.url or "")
    if target in ctx.visited:
        return Violation(constraint_id=code, message="already visited", proposed_url=target)
    return None


def intent_conditional_paths(
    code: str, params: dict, action: AgentAction, ctx: ActionContext
) -> Violation | None:
    """I-S2: legal/utility пути — soft avoid; при intent=contact наоборот boost (нет violation)."""
    if ctx.intent == params.get("boost_when_intent"):
        return None
    path = urlparse(action.url or "").path.lower()
    if any(sub in path for sub in ctx.forbidden_paths):
        return Violation(constraint_id=code, severity="soft",
                         message="legal/utility page — soft avoid",
                         proposed_url=normalize_url(action.url or ""))
    return None


def click_target_safe(
    code: str, params: dict, action: AgentAction, ctx: ActionContext
) -> Violation | None:
    """I-H10 (doc 25 Tier 1): click только по существующему интерактивному элементу,
    не submit/password/login. submit/login → Tier 2 (нужно attended-подтверждение)."""
    if action.action != "click":
        return None
    idx = action.element_index
    elements = ctx.interactive_elements
    if idx is None or idx < 0 or idx >= len(elements):
        return Violation(constraint_id=code, message=f"click index {idx} out of range")
    el = elements[idx]
    forbidden = {k.lower() for k in params.get("forbidden_kinds", ("submit", "password"))}
    kind = (getattr(el, "kind", "") or "").lower()
    itype = (getattr(el, "input_type", "") or "").lower()
    if kind in forbidden or itype in forbidden:
        return Violation(constraint_id=code,
                         message=f"click on '{kind or itype}' needs Tier 2 (confirmation)")
    return None
