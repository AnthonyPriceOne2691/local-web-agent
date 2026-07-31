"""robots.txt (doc 03): 4xx → allow; 5xx/сбой → allow + log; Crawl-delay cap 10 s.

Файл читается **нашим** httpx-клиентом с честным UA, а не `RobotFileParser.read()`.
Причина найдена на real-site прогоне 2026-08-01: `read()` ходит через `urllib` с
его дефолтным `Python-urllib/3.x`, реальные сайты отвечают на такой UA **403**, а
`robotparser` трактует 401/403 как «запрещено всё». В результате `docs.astro.build`,
у которого в robots.txt написано `Allow: /`, давал `robots_disallow` и ноль страниц —
то есть агент сообщал «сайт просил не ходить», хотя сайт просил обратное.

Здесь же восстановлен контракт из шапки: 4xx (включая 401/403) — правил нам не
выдали, значит запрета нет; 5xx и сетевой сбой — тоже проходим, но с логом. Разбор
директив остаётся за stdlib: свой парсер robots писать незачем.
"""

from __future__ import annotations

import logging
import urllib.robotparser
from urllib.parse import urlparse

import httpx

USER_AGENT = "LocalWebAgent/0.1 (personal research tool; +https://localhost)"
CRAWL_DELAY_CAP_S = 10.0
FETCH_TIMEOUT_S = 10.0
MAX_ROBOTS_BYTES = 512_000  # разумный потолок: robots на пол-мегабайта — уже аномалия

logger = logging.getLogger(__name__)


class RobotsPolicy:
    def __init__(self, parser: urllib.robotparser.RobotFileParser | None, crawl_delay_s: float):
        self._parser = parser
        self.crawl_delay_s = crawl_delay_s

    def allowed(self, url: str) -> bool:
        if self._parser is None:
            return True
        return self._parser.can_fetch(USER_AGENT, url) and self._parser.can_fetch("*", url)

    def sitemaps(self) -> list[str]:
        """Sitemap-директивы robots.txt (doc 21 P2.5)."""
        if self._parser is None:
            return []
        return list(self._parser.site_maps() or [])

    @classmethod
    def from_text(cls, text: str) -> RobotsPolicy:
        """Политика из текста robots.txt (разбор — stdlib, поведение — наше)."""
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(text.splitlines())
        delay = 0.0
        for agent in (USER_AGENT, "*"):
            d = rp.crawl_delay(agent)
            if d:
                delay = max(delay, min(float(d), CRAWL_DELAY_CAP_S))
        return cls(rp, delay)

    @classmethod
    async def load(cls, origin: str, *, respect: bool) -> RobotsPolicy:
        host = (urlparse(origin).hostname or "").lower()
        if not respect or host in ("127.0.0.1", "localhost"):
            return cls(None, 0.0)

        url = origin.rstrip("/") + "/robots.txt"
        try:
            async with httpx.AsyncClient(
                timeout=FETCH_TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                resp = await client.get(url)
        except httpx.HTTPError as exc:
            # Сбой сети ≠ запрет: правил мы не получили (doc 03).
            logger.info("robots.txt unreachable at %s (%s) — proceeding", url, type(exc).__name__)
            return cls(None, 0.0)

        if resp.status_code >= 400:
            # 401/403 — сайт не отдал нам правила; 404 — их просто нет. Ни то, ни
            # другое не является запретом, и именно здесь stdlib ошибался.
            logger.info("robots.txt at %s returned %s — no rules served", url, resp.status_code)
            return cls(None, 0.0)

        return cls.from_text(resp.text[:MAX_ROBOTS_BYTES])
