"""Blocker detection (doc 03 § Blockers): login walls, captcha, error pages."""

from __future__ import annotations

from app.schemas.snapshot import PageStatus

_CAPTCHA_SIGNALS = (
    "cf-browser-verification", "cloudflare", "checking your browser",
    "verify you are human", "captcha",
)
_LOGIN_URL_HINTS = ("/login", "/signin", "/sign-in")


def detect_status(*, url: str, main_text: str, title: str, has_password_field: bool) -> PageStatus:
    text = f"{title}\n{main_text[:2000]}".casefold()
    if any(s in text for s in _CAPTCHA_SIGNALS):
        return "captcha"
    if has_password_field or any(h in url.lower() for h in _LOGIN_URL_HINTS):
        return "login_wall"
    return "ok"
