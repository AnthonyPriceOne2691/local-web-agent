"""Скриншоты и cookie-баннер — вынесено из loop.py ради ≤500 LOC (doc 18).

desktop-only; multi-viewport (tablet/mobile) — backlog (doc 22, doc 25 Track A).
Consent живёт здесь же: баннер убирается ради годного скриншота (D-11), и держать
эти два шага в разных модулях значит разнести причину и следствие.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.browser.base import BrowserSession
from app.browser.consent import ConsentHandler
from app.schemas.run import RunRecord
from app.schemas.snapshot import PageSnapshot, ScreenshotRef
from app.storage.run_store import RunStore

logger = logging.getLogger(__name__)

SPA_TEXT_THRESHOLD = 200  # < этого текста → SPA/пустой DOM, снимаем скрин даже в auto (docs 03/22)


async def maybe_screenshot(
    browser: BrowserSession,
    store: RunStore,
    dismiss_consent: Callable[[RunRecord, str], Awaitable[None]],
    record: RunRecord,
    snapshot: PageSnapshot,
    step_index: int,
) -> None:
    mode = record.config.capture_screenshots
    spa_fallback = len(snapshot.main_text) < SPA_TEXT_THRESHOLD
    if mode == "never" or (mode == "auto" and not spa_fallback):
        return
    await dismiss_consent(record, snapshot.url)  # D-11: перед скриншотом
    rel = f"screenshots/{step_index:03d}_desktop.png"
    path = store.artifacts_dir(record.id) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await browser.screenshot(str(path))
        snapshot.screenshots.append(
            ScreenshotRef(profile="desktop", relative_path=rel, width=1440, height=900)
        )
    except Exception as exc:
        # Скриншот — вход для vision-пасса (doc 23): без лога его отсутствие
        # выглядело бы как «страница не выбрана для съёмки».
        logger.warning("screenshot failed for %s (%s: %s)", snapshot.url, type(exc).__name__, exc)


async def dismiss_consent(
    consent: ConsentHandler,
    browser: BrowserSession,
    record: RunRecord,
    url: str,
    *,
    click_used: bool,
) -> str:
    """D-11: detect → hide → click(reject-first). Возвращает статус, он же в metadata.

    Сбой не роняет прогон: скриншоты просто будут с оверлеем. Но молчать нельзя —
    иначе `status="failed"` в metadata остаётся без причины.
    """
    cfg = record.config
    try:
        status = await consent.dismiss(
            browser,
            mode=cfg.consent_handling,
            click_mode=cfg.consent_click,
            site_click_used=click_used,
        )
    except Exception as exc:
        logger.warning("consent dismissal failed on %s (%s: %s)", url, type(exc).__name__, str(exc)[:150])
        status = "failed"
    if status != "none":
        record.metadata.setdefault("consent", {})[url] = status
    return status
