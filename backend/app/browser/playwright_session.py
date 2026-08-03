"""Playwright-реализация BrowserSession (doc 03): async_api, desktop viewport,
downloads blocked (I-H4), fresh context per run."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from app.browser.trackers import TrackerBlocklist
from app.observer.snapshot import INTERACTIVE_SELECTOR, OBSERVE_JS

if TYPE_CHECKING:  # playwright тянется лениво в start(), типы нужны только чекеру
    from playwright.async_api import Browser, BrowserContext, Page, Playwright, Request, Route

logger = logging.getLogger(__name__)

DESKTOP = {"width": 1440, "height": 900}

# Сколько ждём DOMContentLoaded ПОСЛЕ того, как документ пришёл. Отдельный короткий
# бюджет, а не весь page_timeout: событие держат сторонние `defer`-скрипты (аналитика),
# и на их сетевой таймаут (30 s у обоих сайтов замера) ждать нечего — doc 26 § T-3a-1.
DCL_BUDGET_MS = 5000


class PlaywrightSession:
    def __init__(self, *, trackers: TrackerBlocklist | None = None) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._context: BrowserContext | None = None
        self._persist_path: str | None = None
        self._headless = True
        self._trackers = trackers or TrackerBlocklist([])
        self.blocked_trackers = 0  # для записи прогона: сколько запросов отклонили

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
        self._headless = headless
        self._browser = await self._pw.chromium.launch(headless=headless)
        self._persist_path = storage_state_path
        ctx_kwargs: dict[str, Any] = {"viewport": DESKTOP, "accept_downloads": False}
        if storage_state_path and Path(storage_state_path).exists():
            ctx_kwargs["storage_state"] = storage_state_path  # cookie прошлой сессии (doc 24)
        self._context = await self._open_context(ctx_kwargs)
        self._page = await self._context.new_page()
        if not headless:
            await self._close_blank_windows()
            await self._page.bring_to_front()

    async def _open_context(self, ctx_kwargs: dict[str, Any]) -> BrowserContext:
        """Контекст + фильтр сторонней аналитики (один путь для start и _relaunch)."""
        if self._browser is None:
            raise RuntimeError("browser session is not started — call start() first")
        context = await self._browser.new_context(**ctx_kwargs)
        if self._trackers.size:
            await context.route("**/*", self._filter_request)
        return context

    async def _filter_request(self, route: Route, request: Request) -> None:
        page_host = urlsplit(self._page.url).hostname or "" if self._page else ""
        if self._trackers.blocks(request.url, page_host=page_host):
            self.blocked_trackers += 1
            await route.abort()
            return
        await route.continue_()

    async def goto(self, url: str, *, timeout_ms: int) -> str:
        """Навигация: документ обязателен, DOMContentLoaded — по возможности (doc 03).

        Раньше ждали `domcontentloaded` на весь бюджет и роняли переход по таймауту.
        На реальных сайтах это теряло страницу целиком из-за **чужой** аналитики:
        DOMContentLoaded ждёт и отложенных (`defer`) скриптов, поэтому один зависший
        сторонний хост держит событие до сетевого таймаута. Замер T-3a (doc 26):
        `simonwillison.net` — commit 0.7 s, DOMContentLoaded 31.0 s из-за
        `static.cloudflareinsights.com`; `martinfowler.com` — 30.9 s из-за
        `cloud.umami.is`. Оба сайта отдавали документ за секунду, и оба терялись.

        Теперь на бюджет ждём только `commit` (документ пришёл — без него читать
        нечего и падение честное), а на DOMContentLoaded даём короткий отдельный
        бюджет. Не наступил — идём снимать готовый DOM: HTML к этому моменту уже
        разобран, а пустой DOM подхватит SPA-fallback в OBSERVE.
        """
        await self._active.goto(url, wait_until="commit", timeout=timeout_ms)
        # Ожидание DOMContentLoaded — best-effort: его отсутствие не причина терять страницу.
        with contextlib.suppress(Exception):
            await self._active.wait_for_load_state("domcontentloaded", timeout=min(DCL_BUDGET_MS, timeout_ms))
        # Тело документа — уже не best-effort: без него читать нечего вовсе, поэтому ждём
        # его на весь бюджет навигации, а не на короткий бюджет события. Замер T-3b: у
        # habr.com body появлялся на 32.1 s (документ течёт всё это время) — таким сайтам
        # нужен именно бюджет страницы. Не дождались — снапшот выйдет пустым, и это
        # обработанный путь (SPA-fallback + ретрай), а не падение (doc 26 § T-3b-1).
        with contextlib.suppress(Exception):
            await self._active.wait_for_selector("body", state="attached", timeout=timeout_ms)
        await self._active.wait_for_timeout(1000)  # settle (doc 03)
        return self._active.url

    async def raw_snapshot(self) -> dict[str, Any]:
        # anti-bot challenge-страницы (Cloudflare) дёргаются редиректами → evaluate
        # падает с "Execution context was destroyed". Ретраим, дав странице осесть —
        # так OBSERVE поймает challenge-снапшот и сработает attended-пауза (doc 24)
        for attempt in (1, 2):  # две мягкие попытки, третья — ниже, уже без страховки
            try:
                observed: dict[str, Any] = await self._active.evaluate(OBSERVE_JS)
                return observed
            except Exception as exc:
                logger.debug(
                    "OBSERVE_JS attempt %s failed (%s) — page still settling", attempt, type(exc).__name__
                )
                # Ожидание — best-effort перед следующей попыткой.
                with contextlib.suppress(Exception):
                    await self._active.wait_for_load_state("domcontentloaded", timeout=5000)
                await self._active.wait_for_timeout(1500)
        # Третья попытка: если и она падает, исключение уходит вызывающему —
        # OBSERVE без снапшота продолжать нельзя.
        last: dict[str, Any] = await self._active.evaluate(OBSERVE_JS)
        return last

    def page_url(self) -> str:
        return self._page.url if self._page else ""

    async def wait(self, ms: int) -> None:
        await self._active.wait_for_timeout(ms)

    async def wait_networkidle(self, timeout_ms: int) -> None:
        await self._active.wait_for_load_state("networkidle", timeout=timeout_ms)

    async def screenshot(self, path: str) -> None:
        await self._active.screenshot(path=path, type="png", animations="disabled", caret="hide")

    async def eval_js(self, script: str) -> Any:
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

    async def reveal(self) -> bool:
        """Показать окно (перезапуск headed с переносом cookie). True — страница переоткрыта."""
        if not self._headless:
            await self._active.bring_to_front()  # уже видимо — просто поднять
            return False
        return await self._relaunch(headless=False)

    async def conceal(self) -> None:
        """Убрать окно: участие человека больше не нужно."""
        if self._headless:
            return
        await self._relaunch(headless=True)

    async def _relaunch(self, *, headless: bool) -> bool:
        """Пересобрать сессию в другом режиме видимости, сохранив cookie и URL.

        Playwright задаёт headless при запуске браузера, менять его на живом
        Chromium нельзя — поэтому это честный перезапуск, а не «скрытие окна».
        Cookie переносим через storage_state (тот же механизм, что persist_session),
        и страницу открываем заново на том же URL. Состояние страницы при этом
        теряется — вызывающий получает True и решает, что с этим делать.
        """
        if self._pw is None or self._browser is None or self._context is None:
            raise RuntimeError("browser session is not started — call start() first")
        url = self._page.url if self._page else ""
        state = await self._context.storage_state()  # cookie в память, без файла
        await self._browser.close()

        self._headless = headless
        self._browser = await self._pw.chromium.launch(headless=headless)
        ctx_kwargs: dict[str, Any] = {
            "viewport": DESKTOP,
            "accept_downloads": False,
            "storage_state": state,
        }
        self._context = await self._open_context(ctx_kwargs)
        self._page = await self._context.new_page()
        if not headless:
            await self._close_blank_windows()
            await self._page.bring_to_front()
        if url.startswith(("http://", "https://")):
            # Та же стратегия ожидания, что в goto: иначе перезапуск на сайте с
            # зависшим трекером стоил бы 30 s на пустом месте (doc 03 § Wait strategy).
            await self._page.goto(url, wait_until="commit")
            with contextlib.suppress(Exception):
                await self._page.wait_for_load_state("domcontentloaded", timeout=DCL_BUDGET_MS)
            await self._page.wait_for_timeout(500)
        return True

    async def _close_blank_windows(self) -> None:
        """Chromium показывает своё стартовое `about:blank` окно отдельно от контекста —
        человек смотрел в пустое окно и не понимал, где страница."""
        if self._browser is None:
            return
        for ctx in self._browser.contexts:
            if ctx is self._context:
                continue
            for page in ctx.pages:
                if page.url in ("about:blank", ""):
                    await page.close()

    async def close(self) -> None:
        try:  # сохранить cookie сессии по домену (persist_session, doc 24) — не валит run
            if self._persist_path and self._context is not None:
                Path(self._persist_path).parent.mkdir(parents=True, exist_ok=True)
                await self._context.storage_state(path=self._persist_path)
        except Exception as exc:
            # Не валит run, но молчание здесь стоит дорого: человек проходил
            # challenge/логин ради этого cookie, и без лога он «просто не сохранился».
            logger.warning(
                "storage_state not saved to %s (%s: %s)", self._persist_path, type(exc).__name__, exc
            )
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
