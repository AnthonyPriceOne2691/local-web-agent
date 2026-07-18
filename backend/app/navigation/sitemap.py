"""Sitemap tier P2.5 (doc 21): дешёвый детерминированный источник URL.

INIT (после robots): Sitemap-директивы robots.txt → fallback /sitemap.xml,
/sitemap_index.xml; F1 httpx GET; sitemap index → до 3 вложенных; cap 500 <loc>;
same registrable domain; фильтр по intent; top-20 в CandidateQueue (⊂ I-H6).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from app.navigation.path_hints import PathHints
from app.observer.links import normalize_url, same_site

SITEMAP_AUTO_INTENTS = ("content_search", "site_map")  # use_sitemap=auto → on
MAX_PARSED_URLS = 500
MAX_QUEUE_URLS = 20
MAX_NESTED_SITEMAPS = 3
SITEMAP_TIMEOUT_S = 8.0
CONTENT_PATH_MARKERS = ("/blog", "/article", "/news", "/guides", "/post")

_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.IGNORECASE)
_WORD = re.compile(r"[a-zа-яё0-9]{4,}", re.IGNORECASE)
# служебные слова задач — не сигнал в <loc> (RU+EN)
_STOPWORDS = frozenset({
    "find", "article", "about", "with", "from", "what", "where", "this", "that",
    "page", "site", "website", "найди", "найти", "статью", "статья", "сайт",
    "сайте", "текст", "guide",
})


def sitemap_enabled(use_sitemap: str, intent: str) -> bool:
    if use_sitemap == "never":
        return False
    return use_sitemap == "always" or intent in SITEMAP_AUTO_INTENTS


async def fetch_sitemap_candidates(
    client: httpx.AsyncClient,
    *,
    origin: str,
    intent: str,
    task: str,
    hints: PathHints,
    robots_sitemaps: list[str] | None = None,
) -> list[str]:
    """Топ-N sitemap-URL для CandidateQueue P2.5 (уже intent-фильтрованные)."""
    sources = list(robots_sitemaps or []) or [
        origin.rstrip("/") + "/sitemap.xml",
        origin.rstrip("/") + "/sitemap_index.xml",
    ]
    locs: list[str] = []
    for src in sources[:MAX_NESTED_SITEMAPS]:
        locs.extend(await _fetch_locs(client, src, allow_nested=True))
        if len(locs) >= MAX_PARSED_URLS:
            break
    unique = list(dict.fromkeys(normalize_url(u) for u in locs[:MAX_PARSED_URLS]))
    same = [u for u in unique if same_site(u, origin)]
    return _rank_by_intent(same, intent=intent, task=task, hints=hints)[:MAX_QUEUE_URLS]


async def _fetch_locs(client: httpx.AsyncClient, url: str, *, allow_nested: bool) -> list[str]:
    try:
        r = await client.get(url, timeout=SITEMAP_TIMEOUT_S, follow_redirects=True)
        if r.status_code >= 400:
            return []
        body = r.text
    except httpx.HTTPError:
        return []
    locs = _LOC.findall(body)
    if "<sitemapindex" not in body.lower():
        return locs
    if not allow_nested:
        return []
    nested: list[str] = []
    for child in locs[:MAX_NESTED_SITEMAPS]:  # index → до 3 вложенных sitemap
        nested.extend(await _fetch_locs(client, child, allow_nested=False))
    return nested


def _rank_by_intent(urls: list[str], *, intent: str, task: str, hints: PathHints) -> list[str]:
    if intent == "content_search":
        keywords = {w.lower() for w in _WORD.findall(task)} - _STOPWORDS

        def score(url: str) -> int:
            path = urlparse(url).path.lower()
            s = sum(10 for kw in keywords if kw in path)
            s += 5 if any(m in path for m in CONTENT_PATH_MARKERS) else 0
            return s
    else:
        slugs = [s.strip("/").lower() for s in hints.slugs_for(intent)]

        def score(url: str) -> int:
            path = urlparse(url).path.lower()
            return sum(10 for slug in slugs if slug and slug in path)

    scored = [(score(u), u) for u in urls]
    kept = [(s, u) for s, u in scored if s > 0]
    kept.sort(key=lambda pair: -pair[0])
    return [u for _, u in kept]
