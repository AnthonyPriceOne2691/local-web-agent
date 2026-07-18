"""CandidateQueue P0–P4 (doc 21): порядок фиксирован до budget-cut (урок SEOLB §9)."""

from __future__ import annotations

from urllib.parse import urlparse

from app.navigation.link_scorer import score_link
from app.navigation.path_hints import PathHints
from app.observer.links import normalize_url, same_site
from app.schemas.snapshot import Candidate, PageSnapshot


def build_candidates(
    *,
    snapshot: PageSnapshot,
    homepage: PageSnapshot | None,
    intent: str,
    task: str,
    hints: PathHints,
    origin: str,
    visited: set[str],
    alive_probes: list[str],
    legal_probes: list[str],
    top_k: int = 10,
) -> list[Candidate]:
    def usable(snap: PageSnapshot) -> list[dict]:
        return [
            {"href": ln.href, "text": ln.text}
            for ln in snap.links
            if same_site(ln.href, origin) and normalize_url(ln.href) not in visited
        ]

    is_home = urlparse(snapshot.url).path.rstrip("/") in ("", "/")
    buckets: list[list[Candidate]] = [[], [], [], [], []]

    # P0: ссылки текущей страницы с intent/task-сигналом; P4: остальные
    for link in usable(snapshot):
        s, reason = score_link(link, intent=intent, task=task, hints=hints, on_homepage=is_home)
        bucket = 0 if any(tag in reason for tag in ("slug", "task-kw", "homepage+intent")) else 4
        buckets[bucket].append(Candidate(href=link["href"], text=link["text"], score=s, reason=reason))

    # P1: ссылки с закэшированной homepage
    if homepage is not None and homepage.url != snapshot.url:
        for link in usable(homepage):
            s, reason = score_link(link, intent=intent, task=task, hints=hints, on_homepage=True)
            if s > 0:
                buckets[1].append(
                    Candidate(href=link["href"], text=link["text"], score=s, reason="home:" + reason)
                )

    # P2: живые slug-пробы (HTTP-alive, doc 19 lesson); P3: legal только для contact
    for url in alive_probes:
        if normalize_url(url) not in visited:
            buckets[2].append(Candidate(href=url, text="(slug probe)", score=12, reason="probe"))
    for url in legal_probes:
        if normalize_url(url) not in visited:
            buckets[3].append(Candidate(href=url, text="(legal probe)", score=8, reason="legal-probe"))

    seen: set[str] = set()
    queue: list[Candidate] = []
    for bucket in buckets:
        for cand in sorted(bucket, key=lambda c: -c.score):
            n = normalize_url(cand.href)
            if n not in seen:
                seen.add(n)
                queue.append(cand)
    return queue[:top_k]
