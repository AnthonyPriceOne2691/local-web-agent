"""Общие фикстуры: FakeBrowserSession, FakeOllama, tmp store, настройки (doc 18 § mocks)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.navigation.path_hints import PathHints
from app.storage.sqlite_store import SqliteRunStore

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tmp_store(tmp_path: Path) -> SqliteRunStore:
    return SqliteRunStore(tmp_path / "runs")


@pytest.fixture(autouse=True)
def _no_network_probes(monkeypatch):
    """Юниты оркестратора не ходят в сеть: slug-пробы отключены — иначе результаты
    зависят от параллельно запущенного fixtures-сервера на 8901+ (флак).

    Патчим `orchestrator.discovery` — модуль, где пробы теперь и живут (вынесены
    из loop.py ради ≤500 LOC). Патч ставится по месту их импорта, иначе фикстура
    молча перестаёт работать при следующем переносе кода.
    """
    from app.orchestrator import discovery as discovery_mod

    async def no_probes(client, origin, slugs):
        return [], []

    async def no_legal(client, origin, slugs, cache, timeout_s=4.0):
        return []

    monkeypatch.setattr(discovery_mod, "probe_slugs_f1", no_probes)
    monkeypatch.setattr(discovery_mod, "filter_alive", no_legal)


@pytest.fixture(scope="session")
def hints() -> PathHints:
    return PathHints.load(REPO_ROOT / "data" / "navigation")


def page_raw(
    *,
    title: str = "",
    text: str = "",
    links: list[tuple[str, str]] | None = None,
    password: bool = False,
    meta: str = "",
    interactive: list[dict] | None = None,
) -> dict:
    """Хелпер: сырой результат OBSERVE_JS."""
    return {
        "title": title,
        "meta_description": meta,
        "headings": [{"level": 1, "text": title}] if title else [],
        "main_text": text,
        "links": [{"href": h, "text": t} for h, t in (links or [])],
        "interactive": interactive or [],
        "has_password_field": password,
    }


class FakeBrowserSession:
    """Канированные страницы: dict url → raw snapshot. Redirects: dict url → final_url."""

    def __init__(self, pages: dict[str, dict], redirects: dict[str, str] | None = None):
        self.pages = pages
        self.redirects = redirects or {}
        self.current_url: str = ""
        self.visited_log: list[str] = []
        self.screenshots: list[str] = []
        self.closed = False
        # consent (D-11): очередь ответов detect-скрипта и результат click
        self.consent_js_detects: list[bool] = []
        self.consent_click_result: str | None = None
        self.click_attempts: list[list[str]] = []
        self.clicked_indices: list[int] = []  # Tier 1 click (doc 25)
        self.filled: list[tuple[int, str]] = []  # Tier 2 fill (doc 25)
        self.storage_state_path: str | None = None  # persist_session (doc 24)

    async def start(self, *, headless: bool = True, storage_state_path: str | None = None) -> None:
        self.headless = headless
        self.storage_state_path = storage_state_path

    async def goto(self, url: str, *, timeout_ms: int) -> str:
        final = self.redirects.get(url, url)
        if final not in self.pages:
            raise RuntimeError(f"nav error: no such page {final}")
        self.current_url = final
        self.visited_log.append(final)
        return final

    async def raw_snapshot(self) -> dict:
        return self.pages[self.current_url]

    def page_url(self) -> str:
        return self.current_url

    async def wait(self, ms: int) -> None:
        pass

    async def wait_networkidle(self, timeout_ms: int) -> None:
        pass

    async def screenshot(self, path: str) -> None:
        Path(path).write_bytes(b"PNG")
        self.screenshots.append(path)

    async def eval_js(self, script: str):
        """Consent-скрипты (D-11): detect → сценарий из consent_js_detects, hide → True."""
        if "getBoundingClientRect" in script:  # detect-скрипт
            if self.consent_js_detects:
                return self.consent_js_detects.pop(0)
            return False
        return True  # hide-скрипт

    async def click_first(self, selectors: list[str], *, timeout_ms: int) -> str | None:
        self.click_attempts.append(list(selectors))
        return self.consent_click_result

    async def click_element(self, index: int) -> None:  # Tier 1 click (doc 25)
        self.clicked_indices.append(index)

    async def fill_element(self, index: int, value: str) -> None:  # Tier 2 fill (doc 25)
        self.filled.append((index, value))

    async def close(self) -> None:
        self.closed = True


class FakeOllama:
    """Скриптованные ответы: очередь (content, stats) для chat()."""

    def __init__(self, replies: list[str | dict]):
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.unloaded: list[str] = []
        self.warmed: list[str] = []

    async def chat(self, **kwargs) -> tuple[str, dict]:
        self.calls.append(kwargs)
        reply = self._replies.pop(0) if self._replies else '{"action": "stop", "reasoning": "out of replies"}'
        content = json.dumps(reply, ensure_ascii=False) if isinstance(reply, dict) else reply
        return content, {"eval_count": 42}

    async def warmup(self, model: str, keep_alive: str | int = "10m") -> None:
        self.warmed.append(model)  # прогрев модели до открытия браузера

    async def unload(self, model: str) -> None:
        self.unloaded.append(model)

    async def health(self) -> dict:
        return {"reachable": True, "version": "0.31.1", "models": ["fake"]}

    async def aclose(self) -> None:  # pragma: no cover - trivial
        pass
