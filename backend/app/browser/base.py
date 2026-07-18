"""BrowserSession Protocol (doc 18 § interfaces) — Playwright за интерфейсом,
тесты используют FakeBrowserSession."""

from __future__ import annotations

from typing import Protocol


class BrowserSession(Protocol):
    async def start(self, *, headless: bool = True) -> None: ...

    async def goto(self, url: str, *, timeout_ms: int) -> str:
        """Navigate + settle; возвращает ФИНАЛЬНЫЙ URL (redirects — I-H9)."""
        ...

    async def raw_snapshot(self) -> dict:
        """Результат OBSERVE_JS на текущей странице."""
        ...

    async def wait(self, ms: int) -> None: ...

    async def wait_networkidle(self, timeout_ms: int) -> None: ...

    async def screenshot(self, path: str) -> None: ...

    async def eval_js(self, script: str):
        """Выполнить JS на странице (consent detect/hide — D-11)."""
        ...

    async def click_first(self, selectors: list[str], *, timeout_ms: int) -> str | None:
        """Кликнуть первый видимый селектор; вернуть его или None (D-11 ступень 2)."""
        ...

    async def close(self) -> None: ...
