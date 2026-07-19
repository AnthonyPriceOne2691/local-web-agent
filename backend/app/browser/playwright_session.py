"""Playwright-реализация BrowserSession (doc 03): async_api, desktop viewport,
downloads blocked (I-H4), fresh context per run."""

from __future__ import annotations

from app.observer.snapshot import INTERACTIVE_SELECTOR, OBSERVE_JS

DESKTOP = {"width": 1440, "height": 900}


class PlaywrightSession:
    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._page = None

    async def start(self, *, headless: bool = True) -> None:
        from playwright.async_api import async_playwright

        # attended-режим (Phase 5): headless=False — видимое окно, чтобы человек
        # прошёл anti-bot challenge сам; cf_clearance-cookie живёт в контексте run'а
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=headless)
        context = await self._browser.new_context(viewport=DESKTOP, accept_downloads=False)
        self._page = await context.new_page()

    async def goto(self, url: str, *, timeout_ms: int) -> str:
        await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await self._page.wait_for_timeout(1000)  # settle (doc 03)
        return self._page.url

    async def raw_snapshot(self) -> dict:
        # anti-bot challenge-страницы (Cloudflare) дёргаются редиректами → evaluate
        # падает с "Execution context was destroyed". Ретраим, дав странице осесть —
        # так OBSERVE поймает challenge-снапшот и сработает attended-пауза (doc 24)
        for attempt in (1, 2, 3):
            try:
                return await self._page.evaluate(OBSERVE_JS)
            except Exception:  # noqa: BLE001
                if attempt == 3:
                    raise
                try:
                    await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:  # noqa: BLE001
                    pass
                await self._page.wait_for_timeout(1500)

    def page_url(self) -> str:
        return self._page.url if self._page else ""

    async def wait(self, ms: int) -> None:
        await self._page.wait_for_timeout(ms)

    async def wait_networkidle(self, timeout_ms: int) -> None:
        await self._page.wait_for_load_state("networkidle", timeout=timeout_ms)

    async def screenshot(self, path: str) -> None:
        await self._page.screenshot(path=path, type="png", animations="disabled", caret="hide")

    async def eval_js(self, script: str):
        return await self._page.evaluate(script)

    async def click_element(self, index: int) -> None:
        """Tier 1 (doc 25): клик по index-му элементу в том же порядке, что OBSERVE_JS
        (INTERACTIVE_SELECTOR + visibility-фильтр + document order) → индекс совпадает."""
        await self._page.evaluate(
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
        await self._page.wait_for_timeout(500)  # DOM settle после клика

    async def click_first(self, selectors: list[str], *, timeout_ms: int) -> str | None:
        deadline_per_sel = max(200, timeout_ms // max(len(selectors), 1))
        for sel in selectors:
            try:
                locator = self._page.locator(sel).first
                if await locator.is_visible(timeout=deadline_per_sel):
                    await locator.click(timeout=deadline_per_sel)
                    await self._page.wait_for_timeout(300)  # banner teardown settle
                    return sel
            except Exception:  # noqa: BLE001 — селектор мимо, пробуем следующий
                continue
        return None

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
