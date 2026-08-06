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
            client,
            origin=ORIGIN,
            intent="content_search",
            task="Find the article about betting odds",
            hints=hints,
        )
    assert urls[0] == f"{ORIGIN}/blog/betting-odds-guide"  # keyword match — top
    assert f"{ORIGIN}/about" not in urls  # без сигнала — отфильтрован
    assert all(u.startswith(ORIGIN) for u in urls)


async def test_sitemap_index_nested_and_robots_directive(hints):
    index = (
        f'<?xml version="1.0"?><sitemapindex>'
        f"<sitemap><loc>{ORIGIN}/sm-posts.xml</loc></sitemap>"
        f"<sitemap><loc>{ORIGIN}/sm-pages.xml</loc></sitemap>"
        f"</sitemapindex>"
    )
    routes = {
        f"{ORIGIN}/custom-map.xml": index,  # из robots.txt Sitemap:
        f"{ORIGIN}/sm-posts.xml": _urlset(f"{ORIGIN}/blog/betting-tips"),
        f"{ORIGIN}/sm-pages.xml": _urlset(f"{ORIGIN}/news/betting-market"),
    }
    async with _client(routes) as client:
        urls = await fetch_sitemap_candidates(
            client,
            origin=ORIGIN,
            intent="content_search",
            task="betting news",
            hints=hints,
            robots_sitemaps=[f"{ORIGIN}/custom-map.xml"],
        )
    assert set(urls) == {f"{ORIGIN}/blog/betting-tips", f"{ORIGIN}/news/betting-market"}


async def test_nested_sitemaps_are_chosen_by_name_not_by_order(hints):
    """Замер на `legalbet.ru` (doc 26 § T-3j): в индексе **30** вложенных карт с говорящими
    именами, и нужная — `sm_shkola_bettinga.xml` — стоит **22-й**. Брались первые три по
    порядку (`sm_best_posts`, `sm_bonus`, `sm_bonus_compilation`), то есть бонусные промо, и
    до школы обход не доходил никогда.

    Это третий случай одной и той же ошибки: **отбор по позиции вместо смысла** (первые
    два — лимит ссылок снапшота и позиция статей в DOM, T-3d).
    """
    junk = "".join(f"<sitemap><loc>{ORIGIN}/sm-bonus-{i}.xml</loc></sitemap>" for i in range(20))
    index = (
        f'<?xml version="1.0"?><sitemapindex>{junk}'
        f"<sitemap><loc>{ORIGIN}/sm-shkola-bettinga.xml</loc></sitemap>"
        f"</sitemapindex>"
    )
    routes = {f"{ORIGIN}/sitemap.xml": index}
    routes.update({f"{ORIGIN}/sm-bonus-{i}.xml": _urlset(f"{ORIGIN}/bonus/promo-{i}") for i in range(20)})
    routes[f"{ORIGIN}/sm-shkola-bettinga.xml"] = _urlset(f"{ORIGIN}/shkola-bettinga/stavki-na-futbol")

    async with _client(routes) as client:
        urls = await fetch_sitemap_candidates(
            client,
            origin=ORIGIN,
            intent="content_search",
            task="Найди статью о том, как делать ставки на футбол",
            hints=hints,
        )
    assert f"{ORIGIN}/shkola-bettinga/stavki-na-futbol" in urls, urls


async def test_sitemap_index_junk_maps_are_skipped(hints):
    """У `championat.com` в индексе `stats.xml` ведёт к **5385** вложенным картам статистики:
    обход по порядку тонет в них и до содержательных карт не доходит. Такие имена
    (`stats`, `matches`, `teams`, `tags`, `video`) пропускаются."""
    index = (
        f'<?xml version="1.0"?><sitemapindex>'
        f"<sitemap><loc>{ORIGIN}/sitemap/stats.xml</loc></sitemap>"
        f"<sitemap><loc>{ORIGIN}/sitemap/articles.xml</loc></sitemap>"
        f"</sitemapindex>"
    )
    routes = {
        f"{ORIGIN}/sitemap.xml": index,
        f"{ORIGIN}/sitemap/stats.xml": _urlset(*(f"{ORIGIN}/stat/betting-{i}" for i in range(50))),
        f"{ORIGIN}/sitemap/articles.xml": _urlset(f"{ORIGIN}/articles/kak-delat-stavki-na-futbol"),
    }
    async with _client(routes) as client:
        urls = await fetch_sitemap_candidates(
            client,
            origin=ORIGIN,
            intent="content_search",
            task="Найди статью о том, как делать ставки на футбол",
            hints=hints,
        )
    assert f"{ORIGIN}/articles/kak-delat-stavki-na-futbol" in urls
    assert not any("/stat/" in u for u in urls)


async def test_site_map_intent_uses_path_hints(hints):
    sm = _urlset(f"{ORIGIN}/about", f"{ORIGIN}/contact", f"{ORIGIN}/x/random-page-1")
    async with _client({f"{ORIGIN}/sitemap.xml": sm}) as client:
        urls = await fetch_sitemap_candidates(
            client,
            origin=ORIGIN,
            intent="site_map",
            task="map the site",
            hints=hints,
        )
    assert f"{ORIGIN}/x/random-page-1" not in urls


async def test_unreachable_sitemap_returns_empty(hints):
    async with _client({}) as client:
        urls = await fetch_sitemap_candidates(
            client,
            origin=ORIGIN,
            intent="content_search",
            task="betting",
            hints=hints,
        )
    assert urls == []
