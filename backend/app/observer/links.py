"""URL-нормализация и same-site правила (doc 03 § URL normalization, OQ-2).

Единственное место с этой логикой (DRY): observer, navigation, contracts —
все импортируют отсюда.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import tldextract

_TLD = tldextract.TLDExtract(suffix_list_urls=())  # offline PSL snapshot
TRACKING_PARAMS = ("utm_", "gclid", "fbclid", "yclid", "ref")
_IP_OR_LOCAL = re.compile(r"[\d.]+|localhost")

PRIVATE_HOST_PATTERNS = (
    re.compile(r"^localhost$|\.local$|\.internal$"),
    re.compile(r"^127\.|^10\.|^192\.168\.|^169\.254\.|^0\."),
    re.compile(r"^172\.(1[6-9]|2\d|3[01])\."),
)


def normalize_url(url: str) -> str:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    port = f":{p.port}" if p.port and p.port not in (80, 443) else ""
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(p.query)
            if not any(k.lower().startswith(t) or k.lower() == t for t in TRACKING_PARAMS)
        ]
    )
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), host + port, path, "", query, ""))


def resolve(base_url: str, href: str) -> str:
    return normalize_url(urljoin(base_url, href))


def registrable_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if _IP_OR_LOCAL.fullmatch(host):
        return host
    ext = _TLD(host)
    reg = getattr(ext, "top_domain_under_public_suffix", "") or getattr(ext, "registered_domain", "")
    return reg or host


def is_private_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(p.search(host) for p in PRIVATE_HOST_PATTERNS)


def same_site(url: str, origin: str) -> bool:
    """Same registrable domain (OQ-2). Для IP/localhost origin — точный netloc
    (fixture-сайты на разных портах — разные origin'ы)."""
    origin_host = (urlparse(origin).hostname or "").lower()
    if _IP_OR_LOCAL.fullmatch(origin_host):
        return (urlparse(url).netloc or "").lower() == (urlparse(origin).netloc or "").lower()
    a, b = registrable_domain(url), registrable_domain(origin)
    return bool(a) and a == b


def origin_of(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def clean_links(base_url: str, raw_links: list[dict], origin: str, cap: int = 40) -> list[dict]:
    """Resolve, drop mailto/tel/js/anchors, dedupe by normalized href (doc 03)."""
    out, seen = [], set()
    for item in raw_links:
        href = (item.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        n = resolve(base_url, href)
        if urlparse(n).scheme not in ("http", "https") or n in seen:
            continue
        seen.add(n)
        out.append({"href": n, "text": (item.get("text") or "")[:120], "same_site": same_site(n, origin)})
        if len(out) >= cap:
            break
    return out
