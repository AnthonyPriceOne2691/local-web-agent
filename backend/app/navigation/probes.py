"""F1 HTTP probe tier (doc 03 § Phase 2, урок Phase 0/SEOLB).

GET (12 s, 500 KB cap, browser-like UA, follow_redirects, https→http fallback);
403/пустой текст/captcha-маркер → escalate F2 (Playwright); иначе ссылки страницы
идут в CandidateQueue. Без фильтра пробы жгут page budget на 404-х.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

from app.observer.links import resolve, same_site

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
F1_TIMEOUT_S = 12.0
F1_MAX_BYTES = 500 * 1024
PROBE_LINKS_CAP = 20
_MIN_TEXT_CHARS = 50

_HREF = re.compile(r"<a\b[^>]*?href=[\"']([^\"'#][^\"']*)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


@dataclass
class ProbeResult:
    url: str
    alive: bool
    escalate: bool = False  # F2: только Playwright (анти-бот/пустой DOM)
    links: list[dict[str, str]] = field(default_factory=list)  # {href, text} same-site


async def fetch_probe(client: httpx.AsyncClient, url: str, origin: str) -> ProbeResult:
    """Полный F1: GET с caps → ProbeResult (alive/escalate/links)."""
    for attempt_url in _https_http_variants(url):
        try:
            body, status = await _bounded_get(client, attempt_url)
        except httpx.HTTPError:
            continue
        if status == 403:
            return ProbeResult(url=url, alive=True, escalate=True)
        if status >= 400:
            return ProbeResult(url=url, alive=False)
        text_only = _TAG.sub(" ", body)
        if len(text_only.strip()) < _MIN_TEXT_CHARS:  # SPA/challenge → Playwright
            return ProbeResult(url=url, alive=True, escalate=True)
        return ProbeResult(url=url, alive=True, links=_parse_links(body, attempt_url, origin))
    return ProbeResult(url=url, alive=False)


async def filter_alive(
    client: httpx.AsyncClient,
    origin: str,
    slugs: list[str],
    cache: dict[str, bool],
    timeout_s: float = 4.0,
) -> list[str]:
    """Лёгкий HEAD-фильтр (для legal-проб — links не нужны)."""
    alive: list[str] = []
    for slug in slugs:
        url = origin.rstrip("/") + slug
        if url not in cache:
            try:
                r = await client.head(url, timeout=timeout_s, follow_redirects=True)
                if r.status_code == 405:
                    r = await client.get(url, timeout=timeout_s, follow_redirects=True)
                cache[url] = r.status_code < 400
            except httpx.HTTPError:
                cache[url] = False
        if cache[url]:
            alive.append(url)
    return alive


async def probe_slugs_f1(
    client: httpx.AsyncClient, origin: str, slugs: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    """Интент-слуги через полный F1: (живые URL, ссылки с живых страниц)."""
    alive: list[str] = []
    links: list[dict[str, str]] = []
    seen_href: set[str] = set()
    for slug in slugs:
        result = await fetch_probe(client, origin.rstrip("/") + slug, origin)
        if result.alive:
            alive.append(result.url)
        for link in result.links:
            if link["href"] not in seen_href:
                seen_href.add(link["href"])
                links.append(link)
    return alive, links


async def _bounded_get(client: httpx.AsyncClient, url: str) -> tuple[str, int]:
    """GET с cap 500 KB — не выкачиваем больше (doc 03)."""
    async with client.stream(
        "GET",
        url,
        timeout=F1_TIMEOUT_S,
        follow_redirects=True,
        headers={"User-Agent": BROWSER_UA},
    ) as r:
        if r.status_code >= 400:
            return "", r.status_code
        chunks: list[bytes] = []
        size = 0
        async for chunk in r.aiter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size >= F1_MAX_BYTES:
                break
        return b"".join(chunks)[:F1_MAX_BYTES].decode("utf-8", errors="replace"), r.status_code


def _https_http_variants(url: str) -> list[str]:
    if url.startswith("https://"):
        return [url, "http://" + url[len("https://") :]]
    return [url]


def _parse_links(body: str, base_url: str, origin: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for href, inner in _HREF.findall(body):
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        resolved = resolve(base_url, href)
        if not same_site(resolved, origin):
            continue
        text = _TAG.sub(" ", inner)
        out.append({"href": resolved, "text": " ".join(text.split())[:80]})
        if len(out) >= PROBE_LINKS_CAP:
            break
    return out
