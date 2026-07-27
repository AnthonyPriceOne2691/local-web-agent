"""Playwright-реализация BrowserSession (doc 03): async_api, desktop viewport,
downloads blocked (I-H4), fresh context per run."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.observer.snapshot import INTERACTIVE_SELECTOR, OBSERVE_JS

if TYPE_CHECKING:  # playwright тянется лениво в start(), типы нужны только чекеру
    from playwright.async_api import Browser, BrowserContext, Page, Playwright

logger = logging.getLogger(__name__)

DESKTOP = {"width": 1440, "height": 900}


class PlaywrightSession:
    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._context: BrowserContext | None = None
        self._persist_path: str | None = None

    @property
    def _active(self) -> Page:
        """Страница запущенной сессии.

        Обращение до `start()` — ошибка вызывающего, и лучше узнать о ней с
        внятным текстом, чем получить `AttributeError: 'NoneType' has no
        attribute 'goto'` (CQG §1.5: мисконфиг падает явно).
        """
        if self._page is None:
            raise RuntimeError("browser session is not started — call start() first")
        return self._page

    async def start(self, *, headless: bool = True, storage_state_path: str | None = None) -> None:
        from playwright.async_api import async_playwright

        # attended-режим (Phase 5): headless=False — видимое окно, чтобы человек
        # прошёл anti-bot challenge сам; cf_clearance-cookie живёт в контексте run'а
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=headless)
        self._persist_path = storage_state_path
        ctx_kwargs: dict = {"viewport": DESKTOP, "accept_downloads": False}
        if storage_state_path and Path(storage_state_path).exists():
            ctx_kwargs["storage_state"] = storage_state_path  # cookie прошлой сессии (doc 24)
        self._context = await self._browser.new_context(**ctx_kwargs)
        self._page = await self._context.new_page()

    async def goto(self, url: str, *, timeout_ms: int) -> str:
        await self._active.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await self._active.wait_for_timeout(1000)  # settle (doc 03)
        return self._active.url

    async def raw_snapshot(self) -> dict:
        # anti-bot challenge-страницы (Cloudflare) дёргаются редиректами → evaluate
        # падает с "Execution context was destroyed". Ретраим, дав странице осесть —
        # так OBSERVE поймает challenge-снапшот и сработает attended-пауза (doc 24)
        for attempt in (1, 2):  # две мягкие попытки, третья — ниже, уже без страховки
            try:
                return await self._active.evaluate(OBSERVE_JS)
            except Exception as exc:
                logger.debug("OBSERVE_JS attempt %s failed (%s) — page still settling",
                             attempt, type(exc).__name__)
                # Ожидание — best-effort перед следующей попыткой.
                with contextlib.suppress(Exception):
                    await self._active.wait_for_load_state("domcontentloaded", timeout=5000)
                await self._active.wait_for_timeout(1500)
        # Третья попытка: если и она падает, исключение уходит вызывающему —
        # OBSERVE без снапшота продолжать нельзя.
        return await self._active.evaluate(OBSERVE_JS)

    def page_url(self) -> str:
        return self._page.url if self._page else ""

    async def wait(self, ms: int) -> None:
        await self._active.wait_for_timeout(ms)

    async def wait_networkidle(self, timeout_ms: int) -> None:
        await self._active.wait_for_load_state("networkidle", timeout=timeout_ms)

    async def screenshot(self, path: str) -> None:
        await self._active.screenshot(path=path, type="png", animations="disabled", caret="hide")

    async def eval_js(self, script: str):
        return await self._active.evaluate(script)

    async def click_element(self, index: int) -> None:
        """Tier 1 (doc 25): клик по index-му элементу в том же порядке, что OBSERVE_JS
        (INTERACTIVE_SELECTOR + visibility-фильтр + document order) → индекс совпадает."""
        await self._active.evaluate(
            """(args) => {
              const [sel, i] = args;
              const els = [...document.querySelectorAll(sel)]
                .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
              const el = els[i];
              if (!el) throw new Error('no interactive element at index ' + i);
              el.scrollIntoView({block: 'center'});
              el.click();
            }""",
            [INTERACTIVE_SELECTOR, index],
        )
        await self._active.wait_for_timeout(500)  # DOM settle после клика

    async def fill_element(self, index: int, value: str) -> None:
        """Tier 2 (doc 25): вписать текст в index-е поле (тот же порядок, что OBSERVE_JS)."""
        await self._active.evaluate(
            """(args) => {
              const [sel, i, val] = args;
              const els = [...document.querySelectorAll(sel)]
                .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
              const el = els[i];
              if (!el) throw new Error('no interactive element at index ' + i);
              el.focus();
              el.value = val;
              el.dispatchEvent(new Event('input', {bubbles: true}));
              el.dispatchEvent(new Event('change', {bubbles: true}));
            }""",
            [INTERACTIVE_SELECTOR, index, value],
        )
        await self._active.wait_for_timeout(200)

    async def click_first(self, selectors: list[str], *, timeout_ms: int) -> str | None:
        deadline_per_sel = max(200, timeout_ms // max(len(selectors), 1))
        for sel in selectors:
            try:
                locator = self._active.locator(sel).first
                if await locator.is_visible(timeout=deadline_per_sel):
                    await locator.click(timeout=deadline_per_sel)
                    await self._active.wait_for_timeout(300)  # banner teardown settle
                    return sel
            except Exception:
                # silent-ok: перебор CMP-селекторов (D-11) — «не нашёл/не кликнулось»
                # это штатная ветка, а не сбой; итог перебора возвращается наверх
                # (None = ни один не сработал) и попадает в metadata.consent.
                continue
        return None

    async def close(self) -> None:
        try:  # сохранить cookie сессии по домену (persist_session, doc 24) — не валит run
            if self._persist_path and self._context is not None:
                Path(self._persist_path).parent.mkdir(parents=True, exist_ok=True)
                await self._context.storage_state(path=self._persist_path)
        except Exception as exc:
            # Не валит run, но молчание здесь стоит дорого: человек проходил
            # challenge/логин ради этого cookie, и без лога он «просто не сохранился».
            logger.warning("storage_state not saved to %s (%s: %s)",
                           self._persist_path, type(exc).__name__, exc)
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
