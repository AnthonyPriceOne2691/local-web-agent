"""F1 HTTP tier (doc 03): GET+parse, эскалация F2, https→http fallback, caps."""

from __future__ import annotations

import httpx

from app.navigation.probes import (
    F1_MAX_BYTES,
    fetch_probe,
    probe_slugs_f1,
)

ORIGIN = "https://x.com"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _page(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=body)


LINKED_PAGE = (
    "<html><body>" + "Plenty of visible text here. " * 10
    + '<a href="/contact-sales">Contact sales</a>'
    + f'<a href="{ORIGIN}/about">About us</a>'
    + '<a href="https://other.com/x">External</a>'
    + '<a href="mailto:hi@x.com">mail</a>'
    + "</body></html>"
)


async def test_probe_parses_same_site_links():
    async with _client(lambda r: _page(LINKED_PAGE)) as client:
        result = await fetch_probe(client, f"{ORIGIN}/contact", ORIGIN)
    assert result.alive and not result.escalate
    hrefs = [ln["href"] for ln in result.links]
    assert f"{ORIGIN}/contact-sales" in hrefs and f"{ORIGIN}/about" in hrefs
    assert all("other.com" not in h and "mailto" not in h for h in hrefs)
    assert result.links[0]["text"] == "Contact sales"


async def test_probe_403_and_empty_escalate_to_f2():
    async with _client(lambda r: _page("blocked", 403)) as client:
        result = await fetch_probe(client, f"{ORIGIN}/contact", ORIGIN)
    assert result.alive and result.escalate and not result.links

    async with _client(lambda r: _page("<html><body></body></html>")) as client:
        result = await fetch_probe(client, f"{ORIGIN}/spa", ORIGIN)
    assert result.alive and result.escalate  # пустой DOM → Playwright


async def test_probe_404_dead_and_https_http_fallback():
    async with _client(lambda r: _page("nope", 404)) as client:
        assert (await fetch_probe(client, f"{ORIGIN}/gone", ORIGIN)).alive is False

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.scheme == "https":
            raise httpx.ConnectError("tls broken", request=request)
        return _page(LINKED_PAGE)

    async with _client(handler) as client:
        result = await fetch_probe(client, f"{ORIGIN}/contact", ORIGIN)
    assert result.alive and result.links  # добыто по http


async def test_probe_body_capped_at_500kb():
    huge = "x" * (F1_MAX_BYTES * 2)
    async with _client(lambda r: _page(huge)) as client:
        result = await fetch_probe(client, f"{ORIGIN}/big", ORIGIN)
    assert result.alive  # не упало и не выкачало всё


async def test_probe_slugs_f1_dedupes_links():
    async with _client(lambda r: _page(LINKED_PAGE)) as client:
        alive, links = await probe_slugs_f1(client, ORIGIN, ["/contact", "/support"])
    assert alive == [f"{ORIGIN}/contact", f"{ORIGIN}/support"]
    hrefs = [ln["href"] for ln in links]
    assert len(hrefs) == len(set(hrefs))  # дубликаты между пробами убраны
