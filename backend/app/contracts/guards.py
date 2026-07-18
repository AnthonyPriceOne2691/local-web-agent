"""Contract-lite guards — Phase 1 hard checks (doc 13 § MVP scope):
I-H1 same-site · I-H6 url ∈ candidates · I-H8 private network · G-H1 pages ·
G-H2 hop depth · G-H3 visited. Полный YAML-enforcer — Phase 2.

Все проверки — чистые функции, < 1 ms (paper Prop. 4.15).
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.observer.links import is_private_host, normalize_url, same_site
from app.schemas.run import Violation
from app.schemas.snapshot import AgentAction, Candidate


def allowed_target(url: str, origin: str) -> bool:
    """I-H1 + I-H8: same site, http(s), не private (кроме самого origin — fixtures)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    if is_private_host(url) and not is_private_host(origin):
        return False
    return same_site(url, origin)


def validate_navigate(
    action: AgentAction,
    *,
    candidates: list[Candidate],
    origin: str,
    visited: set[str],
    hops: dict[str, int],
    current_url: str,
    max_depth: int,
    max_pages: int,
    pages_visited: int,
) -> Violation | None:
    """None = действие допустимо; иначе Violation (recovery решает orchestrator)."""
    target = normalize_url(action.url or "")
    if pages_visited >= max_pages:
        return Violation(constraint_id="G-H1", message="page budget exhausted", proposed_url=target)
    if target not in {normalize_url(c.href) for c in candidates}:
        return Violation(constraint_id="I-H6", message="url not in candidate queue", proposed_url=target)
    if not allowed_target(target, origin):
        return Violation(constraint_id="I-H1/I-H8", message="target outside allowed site",
                         proposed_url=target)
    if target in visited:
        return Violation(constraint_id="G-H3", message="already visited", proposed_url=target)
    if hops.get(current_url, 0) + 1 > max_depth:
        return Violation(constraint_id="G-H2", message="hop depth exceeded", proposed_url=target)
    return None


def check_redirect(final_url: str, origin: str, *, first_navigation: bool) -> tuple[bool, str]:
    """I-H9 post-redirect re-check. Возвращает (ok, new_origin).

    Step 0: off-domain redirect ПЕРЕОПРЕДЕЛЯЕТ origin (переезд домена, doc 03),
    private network блокируется всегда."""
    if is_private_host(final_url) and not is_private_host(origin):
        return False, origin
    if same_site(final_url, origin):
        return True, origin
    if first_navigation:
        p = urlparse(final_url)
        return True, f"{p.scheme}://{p.netloc}"
    return False, origin
