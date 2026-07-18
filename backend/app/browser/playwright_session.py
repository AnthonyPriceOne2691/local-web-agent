"""Playwright-реализация BrowserSession (doc 03): async_api, desktop viewport,
downloads blocked (I-H4), fresh context per run."""

from __future__ import annotations

from app.observer.snapshot import OBSERVE_JS

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
        return await self._page.evaluate(OBSERVE_JS)

    async def wait(self, ms: int) -> None:
        await self._page.wait_for_timeout(ms)

    async def wait_networkidle(self, timeout_ms: int) -> None:
        await self._page.wait_for_load_state("networkidle", timeout=timeout_ms)

    async def screenshot(self, path: str) -> None:
        await self._page.screenshot(path=path, type="png", animations="disabled", caret="hide")

    async def eval_js(self, script: str):
        return await self._page.evaluate(script)

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
