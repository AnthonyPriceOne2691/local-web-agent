"""Откуда берутся кандидаты на обход и что считается статьёй.

Вынесено из loop.py ради ≤500 LOC (doc 18), как attended.py / interaction.py /
capture.py. Тема модуля: **источники URL до навигации** (F1 slug-пробы, sitemap —
doc 21 § P2/P2.5) плюс детект article-кандидата для content_search (doc 24).
Сетевые вызовы здесь одноразовые: свой httpx-клиент на шаг, без общего пула.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.navigation.path_hints import PathHints
from app.navigation.probes import filter_alive, probe_slugs_f1
from app.navigation.sitemap import (
    CONTENT_PATH_MARKERS,
    fetch_sitemap_candidates,
    sitemap_enabled,
)
from app.schemas.run import RunRecord
from app.schemas.snapshot import PageSnapshot

ARTICLE_MIN_TEXT_WITH_PATH = 800  # path-маркер + столько текста → статья
ARTICLE_MIN_TEXT_BY_TITLE = 2000  # без маркера верим только длинному тексту + title


async def probe_slugs(
    hints: PathHints,
    intent: str,
    origin: str,
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    """F1 tier: интент-слуги через GET+parse (links → queue), legal — HEAD-фильтр."""
    cache: dict[str, bool] = {}
    async with httpx.AsyncClient() as client:
        alive, probe_links = await probe_slugs_f1(client, origin, hints.slugs_for(intent))
        legal = await filter_alive(client, origin, hints.legal_slugs, cache) if intent == "contact" else []
    return alive, legal, probe_links


async def sitemap_urls(
    record: RunRecord,
    origin: str,
    robots_sitemaps: list[str],
    hints: PathHints,
) -> list[str]:
    """P2.5: sitemap.xml → интент-фильтрованные URL; число уходит в metadata."""
    if not sitemap_enabled(record.config.use_sitemap, record.intent):
        return []
    async with httpx.AsyncClient() as client:
        urls = await fetch_sitemap_candidates(
            client,
            origin=origin,
            intent=record.intent,
            task=record.config.task,
            hints=hints,
            robots_sitemaps=robots_sitemaps,
        )
    if urls:
        record.metadata["sitemap_candidates"] = len(urls)
    return urls


def looks_like_article(snapshot: PageSnapshot, task: str) -> bool:
    """Article-кандидат (doc 24): path-маркер ИЛИ task-слова в title + длинный текст."""
    path = urlparse(snapshot.url).path.lower()
    if any(m in path for m in CONTENT_PATH_MARKERS) and len(snapshot.main_text) > ARTICLE_MIN_TEXT_WITH_PATH:
        return True
    title = snapshot.title.casefold()
    task_words = [w for w in task.casefold().split() if len(w) > 3]
    return len(snapshot.main_text) > ARTICLE_MIN_TEXT_BY_TITLE and any(w in title for w in task_words)
