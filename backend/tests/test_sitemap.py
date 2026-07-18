"""Sitemap tier P2.5 (doc 21): fetch, index nesting, intent filter, caps."""

from __future__ import annotations

import httpx
import pytest

from app.navigation.path_hints import PathHints
from app.navigation.sitemap import fetch_sitemap_candidates, sitemap_enabled
from tests.conftest import REPO_ROOT

ORIGIN = "https://x.com"


@pytest.fixture(scope="module")
def hints() -> PathHints:
    return PathHints.load(REPO_ROOT / "data" / "navigation")


def _client(routes: dict[str, str | int]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(str(request.url))
        if body is None:
            return httpx.Response(404, text="not found")
        if isinstance(body, int):
            return httpx.Response(body)
        return httpx.Response(200, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _urlset(*urls: str) -> str:
    locs = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0"?><urlset>{locs}</urlset>'


def test_sitemap_enabled_matrix():
    assert sitemap_enabled("auto", "content_search")
    assert sitemap_enabled("auto", "site_map")
    assert not sitemap_enabled("auto", "contact")
    assert sitemap_enabled("always", "contact")
    assert not sitemap_enabled("never", "content_search")


async def test_content_search_filters_by_task_keywords(hints):
    sm = _urlset(
        f"{ORIGIN}/blog/betting-odds-guide",
        f"{ORIGIN}/blog/cooking-pasta",
        f"{ORIGIN}/about",
        "https://other.com/blog/betting",  # чужой домен — отсекается
    )
    async with _client({f"{ORIGIN}/sitemap.xml": sm}) as client:
        urls = await fetch_sitemap_candidates(
            client, origin=ORIGIN, intent="content_search",
            task="Find the article about betting odds", hints=hints,
        )
    assert urls[0] == f"{ORIGIN}/blog/betting-odds-guide"  # keyword match — top
    assert f"{ORIGIN}/about" not in urls  # без сигнала — отфильтрован
    assert all(u.startswith(ORIGIN) for u in urls)


async def test_sitemap_index_nested_and_robots_directive(hints):
    index = (f'<?xml version="1.0"?><sitemapindex>'
             f"<sitemap><loc>{ORIGIN}/sm-posts.xml</loc></sitemap>"
             f"<sitemap><loc>{ORIGIN}/sm-pages.xml</loc></sitemap>"
             f"</sitemapindex>")
    routes = {
        f"{ORIGIN}/custom-map.xml": index,  # из robots.txt Sitemap:
        f"{ORIGIN}/sm-posts.xml": _urlset(f"{ORIGIN}/blog/betting-tips"),
        f"{ORIGIN}/sm-pages.xml": _urlset(f"{ORIGIN}/news/betting-market"),
    }
    async with _client(routes) as client:
        urls = await fetch_sitemap_candidates(
            client, origin=ORIGIN, intent="content_search", task="betting news",
            hints=hints, robots_sitemaps=[f"{ORIGIN}/custom-map.xml"],
        )
    assert set(urls) == {f"{ORIGIN}/blog/betting-tips", f"{ORIGIN}/news/betting-market"}


async def test_site_map_intent_uses_path_hints(hints):
    sm = _urlset(f"{ORIGIN}/about", f"{ORIGIN}/contact", f"{ORIGIN}/x/random-page-1")
    async with _client({f"{ORIGIN}/sitemap.xml": sm}) as client:
        urls = await fetch_sitemap_candidates(
            client, origin=ORIGIN, intent="site_map", task="map the site", hints=hints,
        )
    assert f"{ORIGIN}/x/random-page-1" not in urls


async def test_unreachable_sitemap_returns_empty(hints):
    async with _client({}) as client:
        urls = await fetch_sitemap_candidates(
            client, origin=ORIGIN, intent="content_search", task="betting", hints=hints,
        )
    assert urls == []
