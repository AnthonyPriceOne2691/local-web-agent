"""maybe_screenshot — вынесено из loop.py ради ≤500 LOC (doc 18).

desktop-only; multi-viewport (tablet/mobile) — backlog (doc 22, doc 25 Track A).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.browser.base import BrowserSession
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
        logger.warning("screenshot failed for %s (%s: %s)",
                       snapshot.url, type(exc).__name__, exc)
