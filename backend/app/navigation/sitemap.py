"""Sitemap tier P2.5 (doc 21): дешёвый детерминированный источник URL.

INIT (после robots): Sitemap-директивы robots.txt → fallback /sitemap.xml,
/sitemap_index.xml; F1 httpx GET; sitemap index → до 3 вложенных; cap 500 <loc>;
same registrable domain; фильтр по intent; top-20 в CandidateQueue (⊂ I-H6).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from app.navigation.matching import task_words, transliterate
from app.navigation.path_hints import PathHints
from app.observer.links import normalize_url, same_site

SITEMAP_AUTO_INTENTS = ("content_search", "site_map")  # use_sitemap=auto → on
MAX_PARSED_URLS = 500
MAX_QUEUE_URLS = 20
MAX_NESTED_SITEMAPS = 3
SITEMAP_TIMEOUT_S = 8.0
CONTENT_PATH_MARKERS = ("/blog", "/article", "/news", "/guides", "/post")

_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.IGNORECASE)
# Служебные слова задач («найди статью на сайте») — не сигнал в <loc>. Словарь переехал в
# `data/navigation/path_hints.yaml` (`task_stopwords`): у него появился второй потребитель —
# оценка ссылок, и копия в коде разошлась бы с ним.


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

    def pick(children: list[str]) -> list[str]:
        return _pick_nested(children, intent=intent, task=task, hints=hints)

    locs: list[str] = []
    for src in sources[:MAX_NESTED_SITEMAPS]:
        locs.extend(await _fetch_locs(client, src, allow_nested=True, pick=pick))
        if len(locs) >= MAX_PARSED_URLS:
            break
    unique = list(dict.fromkeys(normalize_url(u) for u in locs[:MAX_PARSED_URLS]))
    same = [u for u in unique if same_site(u, origin)]
    return _rank_by_intent(same, intent=intent, task=task, hints=hints)[:MAX_QUEUE_URLS]


def _pick_nested(children: list[str], *, intent: str, task: str, hints: PathHints) -> list[str]:
    """Вложенные карты выбираются **по имени**, а не по порядку в индексе.

    Замер (doc 26 § T-3j): у `legalbet.ru` в индексе 30 карт с говорящими именами, нужная —
    `sm_shkola_bettinga.xml` — стоит 22-й, а брались первые три (`sm_best_posts`, `sm_bonus`,
    `sm_bonus_compilation`), то есть бонусные промо. У `championat.com` первая же карта
    `stats.xml` ведёт к 5385 вложенным картам статистики, и обход тонет в них.

    Это третий случай одной ошибки — **отбор по позиции вместо смысла** (первые два: лимит
    ссылок снапшота и позиция статей в DOM, T-3d).
    """
    words = task_words(task, hints.task_stopwords)
    forms = {*words, *(transliterate(w) for w in words)}
    genre = hints.learn_markers if intent == "content_search" else ()
    slugs = [s.strip("/") for s in hints.slugs_for(intent)]

    def score(url: str) -> int:
        name = url.rsplit("/", 1)[-1].removesuffix(".gz").removesuffix(".xml").casefold()
        s = sum(10 for w in forms if len(w) > 3 and w[:5] in name)
        s += sum(6 for g in genre if g in name)
        s += sum(4 for slug in slugs if slug and slug in name)
        return s

    ranked = sorted(((score(u), i, u) for i, u in enumerate(children)), key=lambda t: (-t[0], t[1]))
    useful = [u for s, _, u in ranked if s > 0]
    # Ни одного говорящего имени — берём начало индекса, как раньше: карта может быть одна
    # и называться `sitemap1.xml`.
    return useful[:MAX_NESTED_SITEMAPS] if useful else children[:MAX_NESTED_SITEMAPS]


async def _fetch_locs(
    client: httpx.AsyncClient,
    url: str,
    *,
    allow_nested: bool,
    pick: Callable[[list[str]], list[str]] | None = None,
) -> list[str]:
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
    children = pick(locs) if pick else locs[:MAX_NESTED_SITEMAPS]
    for child in children:  # index → до 3 вложенных карт, выбранных ПО ИМЕНИ
        nested.extend(await _fetch_locs(client, child, allow_nested=False))
    return nested


def _rank_by_intent(urls: list[str], *, intent: str, task: str, hints: PathHints) -> list[str]:
    if intent == "content_search":
        # Словарь служебных слов — общий с оценкой ссылок (`data/navigation/path_hints.yaml`):
        # он жил здесь в коде, и второй потребитель завёл бы копию.
        #
        # Транслит обязателен по той же причине, что в оценке ссылок: русские слова задачи
        # с латинским путём (`/shkola-bettinga/stavki-na-futbol`) не совпадают **никогда**,
        # и весь sitemap-tier для русских задач молча давал ноль кандидатов (doc 26 § T-3j).
        words = task_words(task, hints.task_stopwords)
        keywords = {*words, *(transliterate(w) for w in words)}
        genre = tuple(hints.learn_markers)

        def score(url: str) -> int:
            path = urlparse(url).path.lower()
            s = sum(10 for kw in keywords if len(kw) > 3 and kw[:5] in path)
            s += 5 if any(m in path for m in CONTENT_PATH_MARKERS) else 0
            s += 5 if any(g in path for g in genre) else 0
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
