"""robots.txt (doc 03): 4xx → allow; 5xx/сбой → allow + log; Crawl-delay cap 10 s."""

from __future__ import annotations

import asyncio
import urllib.robotparser
from urllib.parse import urlparse

USER_AGENT = "LocalWebAgent/0.1 (personal research tool; +https://localhost)"
CRAWL_DELAY_CAP_S = 10.0


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
    async def load(cls, origin: str, *, respect: bool) -> RobotsPolicy:
        host = (urlparse(origin).hostname or "").lower()
        if not respect or host in ("127.0.0.1", "localhost"):
            return cls(None, 0.0)

        def _fetch() -> RobotsPolicy:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(origin.rstrip("/") + "/robots.txt")
            try:
                rp.read()
            except OSError:
                return cls(None, 0.0)  # proceed + log (doc 03)
            delay = 0.0
            for agent in (USER_AGENT, "*"):
                d = rp.crawl_delay(agent)
                if d:
                    delay = max(delay, min(float(d), CRAWL_DELAY_CAP_S))
            return cls(rp, delay)

        return await asyncio.to_thread(_fetch)
