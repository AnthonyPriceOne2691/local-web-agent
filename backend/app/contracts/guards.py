"""Orchestrator-owned guard: I-H9 post-redirect re-check (doc 13).

Вызывается ПОСЛЕ Playwright goto — вне PLAN-shield (enforcer.py покрывает
проверки до действия; per-action логика Phase 1 переехала в contracts/rules/).
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.observer.links import is_private_host, same_site


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
