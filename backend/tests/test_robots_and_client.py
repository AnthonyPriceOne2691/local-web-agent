"""RobotsPolicy (fetch/allow/delay/sitemaps) + OllamaClient через MockTransport."""

from __future__ import annotations

import httpx

from app.llm.ollama_client import OllamaClient, strip_thinking, supports_think
from app.orchestrator.robots import RobotsPolicy

ROBOTS_TXT = """User-agent: *
Disallow: /private
Crawl-delay: 30
Sitemap: https://x.com/custom-map.xml
"""


def _robots_transport(status: int, body: str = "", *, boom: bool = False):
    """Ответ сервера на GET /robots.txt — мы читаем его своим клиентом, не urllib."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        # UA обязателен и честный: именно из-за дефолтного urllib-UA сайты отвечали 403
        assert "LocalWebAgent" in request.headers["user-agent"]
        if boom:
            raise httpx.ConnectError("network down", request=request)
        return httpx.Response(status, text=body)

    return httpx.MockTransport(handler)


def _patch_robots_fetch(monkeypatch, transport: httpx.MockTransport) -> None:
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr("app.orchestrator.robots.httpx.AsyncClient", factory)


async def test_robots_fetch_allow_delay_sitemaps(monkeypatch):
    _patch_robots_fetch(monkeypatch, _robots_transport(200, ROBOTS_TXT))
    policy = await RobotsPolicy.load("https://x.com", respect=True)
    assert policy.allowed("https://x.com/public") is True
    assert policy.allowed("https://x.com/private/page") is False
    assert policy.crawl_delay_s == 10.0  # cap 10 s (doc 03)
    assert policy.sitemaps() == ["https://x.com/custom-map.xml"]


async def test_robots_403_is_not_a_prohibition(monkeypatch):
    """403 на robots.txt — правил нам не выдали, а не «нельзя ничего».

    Найдено real-site прогоном 2026-08-01: `RobotFileParser.read()` ходит с
    дефолтным urllib-UA, docs.astro.build отвечает на него 403, а stdlib трактует
    401/403 как disallow_all — агент сообщал `robots_disallow` про сайт, у которого
    в robots.txt написано `Allow: /`.
    """
    _patch_robots_fetch(monkeypatch, _robots_transport(403, "nope"))
    policy = await RobotsPolicy.load("https://docs.example", respect=True)
    assert policy.allowed("https://docs.example/en/getting-started/") is True
    assert policy.sitemaps() == []


async def test_robots_404_allows(monkeypatch):
    _patch_robots_fetch(monkeypatch, _robots_transport(404))
    policy = await RobotsPolicy.load("https://x.com", respect=True)
    assert policy.allowed("https://x.com/anything") is True


async def test_robots_5xx_proceeds_with_log(monkeypatch):
    _patch_robots_fetch(monkeypatch, _robots_transport(503))
    policy = await RobotsPolicy.load("https://x.com", respect=True)
    assert policy.allowed("https://x.com/anything") is True  # doc 03: 5xx → allow + log


async def test_robots_disallow_is_still_respected(monkeypatch):
    """Инвариант проекта не размывается: настоящий Disallow работает."""
    _patch_robots_fetch(monkeypatch, _robots_transport(200, "User-agent: *\nDisallow: /\n"))
    policy = await RobotsPolicy.load("https://closed.example", respect=True)
    assert policy.allowed("https://closed.example/") is False


async def test_robots_localhost_and_disabled():
    p1 = await RobotsPolicy.load("http://127.0.0.1:8901", respect=True)
    p2 = await RobotsPolicy.load("https://x.com", respect=False)
    for p in (p1, p2):
        assert p.allowed("anything") is True
        assert p.sitemaps() == []


async def test_robots_fetch_error_proceeds(monkeypatch):
    _patch_robots_fetch(monkeypatch, _robots_transport(200, boom=True))
    policy = await RobotsPolicy.load("https://x.com", respect=True)
    assert policy.allowed("https://x.com/anything") is True  # сбой сети → allow + log


# ---------------------------------------------------------------- Ollama client
def _ollama_client(handler) -> OllamaClient:
    client = OllamaClient("http://ollama.test")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


async def test_chat_schema_think_and_stats():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200, json={"message": {"content": '{"ok": true}'}, "eval_count": 5, "total_duration": 100}
        )

    client = _ollama_client(handler)
    content, stats = await client.chat(
        model="qwen3:14b", system="s", user="u", schema={"type": "object"}, think=False, images=["QUJD"]
    )
    assert content == '{"ok": true}'
    assert stats["eval_count"] == 5
    body = seen[0]
    assert body["format"] == {"type": "object"}
    assert body["think"] is False
    assert body["messages"][1]["images"] == ["QUJD"]


async def test_chat_think_400_fallback_retries_without_think():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        calls.append(body)
        if "think" in body:
            return httpx.Response(400, json={"error": "unknown option think"})
        return httpx.Response(200, json={"message": {"content": "ok"}})

    client = _ollama_client(handler)
    content, _ = await client.chat(model="qwen3:14b", system="s", user="u", think=True)
    assert content == "ok"
    assert len(calls) == 2 and "think" not in calls[1]


async def test_unload_swallows_errors_and_health_states():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = _ollama_client(down)
    await client.unload("m")  # не бросает
    health = await client.health()
    assert health == {"reachable": False, "version": "", "models": []}

    def up(request: httpx.Request) -> httpx.Response:
        if "version" in str(request.url):
            return httpx.Response(200, json={"version": "0.9.9"})
        return httpx.Response(200, json={"models": [{"name": "qwen3:14b"}]})

    client2 = _ollama_client(up)
    health = await client2.health()
    assert health["reachable"] and health["models"] == ["qwen3:14b"]
    await client2.aclose()


def test_think_helpers():
    assert supports_think("qwen3:14b") and supports_think("deepseek-r1:14b")
    assert not supports_think("qwen2.5:14b-instruct")
    assert strip_thinking("<think>draft</think>final") == "final"
