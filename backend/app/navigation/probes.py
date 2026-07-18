"""F1-lite HTTP-фильтр slug-проб (урок Phase 0, doc 19/21).

Без фильтра пробы жгут page budget на 404-х: в очередь идут только живые.
Полный F1 tier (parsing контента) — Phase 2.
"""

from __future__ import annotations

import httpx


async def filter_alive(
    client: httpx.AsyncClient,
    origin: str,
    slugs: list[str],
    cache: dict[str, bool],
    timeout_s: float = 4.0,
) -> list[str]:
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
