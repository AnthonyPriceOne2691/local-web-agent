"""Навигация не теряет страницу из-за чужой аналитики (doc 03 § Навигация, doc 26 § T-3a-1).

Находка живого прогона T-3a: два сайта из трёх терялись целиком с
`Page.goto: Timeout 30000ms exceeded`, хотя документ приходил за 0.7 s. Держал событие
DOMContentLoaded **сторонний** трекер (`static.cloudflareinsights.com`, `cloud.umami.is`):
DOMContentLoaded ждёт и `defer`-скриптов, поэтому один зависший хост стоил всей страницы,
а сессии — 46 % времени впустую.

Здесь проверяется поведение, а не реализация: документ обязателен, DOMContentLoaded — нет.
"""

from __future__ import annotations

import pytest

from app.browser.playwright_session import PlaywrightSession


class FakeTimeoutError(Exception):
    """Стенд-ин для playwright TimeoutError (реальный класс тянет playwright)."""


class FakePage:
    """Страница Playwright настолько, насколько нужно для стратегии ожидания.

    `dcl_never` моделирует именно поведение сайта из находки: документ приходит, а
    DOMContentLoaded не наступает никогда (его держит зависший сторонний скрипт).
    Поэтому таймаут летит **из любого** ожидания этого события — и из `goto(wait_until=
    "domcontentloaded")`, как было в старом коде, и из отдельного `wait_for_load_state`,
    как в новом. Без этого тест давал бы ложное зелёное на старой реализации.
    """

    def __init__(self, *, dcl_never: bool = False, no_document: bool = False, no_body: bool = False) -> None:
        self.url = ""
        self._dcl_never = dcl_never
        self._no_document = no_document
        self._no_body = no_body
        self.goto_calls: list[tuple[str, str, int]] = []
        self.load_state_calls: list[tuple[str, int]] = []
        self.selector_waits: list[tuple[str, int]] = []
        self.waited_ms = 0

    async def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.goto_calls.append((url, wait_until, timeout))
        if self._no_document:
            raise FakeTimeoutError(f"Page.goto: Timeout {timeout}ms exceeded")
        if wait_until == "domcontentloaded" and self._dcl_never:
            raise FakeTimeoutError(f"Page.goto: Timeout {timeout}ms exceeded")
        self.url = url

    async def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        self.load_state_calls.append((state, timeout))
        if state == "domcontentloaded" and self._dcl_never:
            raise FakeTimeoutError(f"Timeout {timeout}ms exceeded")

    async def wait_for_selector(self, selector: str, *, state: str, timeout: int) -> None:
        self.selector_waits.append((selector, timeout))
        if self._no_body:
            raise FakeTimeoutError(f"Timeout {timeout}ms exceeded waiting for {selector}")

    async def wait_for_timeout(self, ms: int) -> None:
        self.waited_ms += ms


def _session(page: FakePage) -> PlaywrightSession:
    session = PlaywrightSession()
    session._page = page  # type: ignore[assignment]  # подстановка страницы вместо start()
    return session


async def test_goto_waits_only_for_commit_on_the_full_budget():
    """Бюджет перехода тратится на документ, а не на событие, которое держит чужой хост."""
    page = FakePage()
    url = await _session(page).goto("https://example.com/", timeout_ms=30_000)

    assert page.goto_calls == [("https://example.com/", "commit", 30_000)]
    assert url == "https://example.com/"


async def test_domcontentloaded_gets_its_own_short_budget():
    page = FakePage()
    await _session(page).goto("https://example.com/", timeout_ms=30_000)

    assert len(page.load_state_calls) == 1
    state, budget = page.load_state_calls[0]
    assert state == "domcontentloaded"
    assert budget < 30_000, "короткий отдельный бюджет — весь смысл правки"


async def test_hanging_tracker_does_not_lose_the_page():
    """Главный кейс T-3a: DOMContentLoaded не наступил — страница всё равно наша.

    На старой реализации падает: там это событие ждали на весь бюджет перехода, и
    таймаут уносил всю страницу (в живом прогоне — весь сайт, 0 страниц).
    """
    page = FakePage(dcl_never=True)
    url = await _session(page).goto("https://simonwillison.net/", timeout_ms=30_000)

    assert url == "https://simonwillison.net/"
    assert page.waited_ms == 1000, "settle после навигации сохранён (doc 03)"


async def test_unreachable_document_still_fails():
    """Негативный контроль правки: нет документа — читать нечего, падаем честно."""
    page = FakePage(no_document=True)
    with pytest.raises(FakeTimeoutError):
        await _session(page).goto("https://unreachable.example/", timeout_ms=30_000)


async def test_dcl_budget_never_exceeds_the_page_budget():
    """При маленьком page_timeout короткий бюджет не должен его превышать."""
    page = FakePage()
    await _session(page).goto("https://example.com/", timeout_ms=2_000)

    assert page.load_state_calls == [("domcontentloaded", 2_000)]


# --- тело документа: без него читать нечего (doc 26 § T-3b-1) ---


async def test_body_is_awaited_on_the_full_page_budget():
    """Замер T-3b: у habr.com body появлялся на 32.1 s — короткого бюджета события мало."""
    page = FakePage()
    await _session(page).goto("https://habr.com/ru/", timeout_ms=45_000)

    assert page.selector_waits == [("body", 45_000)], (
        "тело ждём на бюджет страницы, а не на бюджет DOMContentLoaded"
    )


async def test_missing_body_does_not_raise():
    """Не дождались тела — снапшот выйдет пустым (обработанный путь), а не исключение."""
    page = FakePage(no_body=True)
    url = await _session(page).goto("https://habr.com/ru/", timeout_ms=5_000)

    assert url == "https://habr.com/ru/"


def test_observe_js_survives_a_document_without_body():
    """Падение было прямо в нашем JS: `document.body` разыменовывался без проверки."""
    from app.observer.snapshot import OBSERVE_JS

    assert "document.documentElement" in OBSERVE_JS, "нужен запасной корень"
    assert "(mainEl && mainEl.innerText)" in OBSERVE_JS, "чтение должно быть защищённым"
    assert "(mainEl.innerText" not in OBSERVE_JS, "безусловное разыменование вернулось"
