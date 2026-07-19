"""Blocker detection (doc 03 § Blockers): login walls, captcha, error pages."""

from __future__ import annotations

from app.schemas.snapshot import PageStatus

_CAPTCHA_SIGNALS = (
    # Cloudflare challenge (старые + актуальные managed/Turnstile формулировки 2026)
    "cf-browser-verification", "cloudflare", "checking your browser",
    "just a moment", "enable javascript and cookies", "verifying you are human",
    "needs to review the security of your connection", "challenges.cloudflare.com",
    "__cf_chl", "attention required",
    # прочие anti-bot / captcha
    "verify you are human", "captcha", "are you a robot", "unusual traffic",
)
_LOGIN_URL_HINTS = ("/login", "/signin", "/sign-in")


# full-page anti-bot challenge = «тонкая» страница-заглушка; реальная страница с
# встроенным Turnstile-виджетом («verifying you are human») толстая — её не блокируем
_CHALLENGE_MAX_TEXT = 800


def detect_status(*, url: str, main_text: str, title: str, has_password_field: bool) -> PageStatus:
    title_l = title.casefold()
    body = f"{title}\n{main_text[:2000]}".casefold()
    in_title = any(s in title_l for s in _CAPTCHA_SIGNALS)  # challenge-заглушка всегда c таким title
    thin = len(main_text or "") < _CHALLENGE_MAX_TEXT
    if in_title or (thin and any(s in body for s in _CAPTCHA_SIGNALS)):
        return "captcha"
    if has_password_field or any(h in url.lower() for h in _LOGIN_URL_HINTS):
        return "login_wall"
    return "ok"


def looks_like_challenge(raw: dict) -> bool:
    """anti-bot challenge на сыром снапшоте — чтобы OBSERVE не ждал SPA-networkidle
    (это ожидание даёт challenge пройти и проскочить attended-паузу, Phase 5)."""
    return detect_status(
        url="", main_text=raw.get("main_text") or "", title=raw.get("title") or "",
        has_password_field=bool(raw.get("has_password_field")),
    ) == "captcha"
