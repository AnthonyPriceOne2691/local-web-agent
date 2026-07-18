"""observer/links (нормализация, same-site, private) + navigation/intent (RU+EN)."""

from __future__ import annotations

from app.navigation.intent import classify_intent
from app.observer.links import clean_links, is_private_host, normalize_url, same_site


def test_normalize_strips_fragment_and_tracking():
    assert normalize_url("https://x.com/a#sec") == "https://x.com/a"
    assert normalize_url("https://x.com/a?utm_source=tg&q=1") == "https://x.com/a?q=1"
    assert "gclid" not in normalize_url("https://x.com/?gclid=1")


def test_normalize_trailing_slash_and_ports():
    assert normalize_url("https://x.com/about/") == normalize_url("https://x.com/about")
    assert normalize_url("https://x.com/") == "https://x.com/"
    assert normalize_url("https://x.com:443/a") == "https://x.com/a"
    assert ":8901" in normalize_url("http://127.0.0.1:8901/a")


def test_same_site_registrable_domain():
    assert same_site("https://devguide.python.org/x", "https://www.python.org/")
    assert not same_site("https://evil.com/", "https://python.org/")


def test_same_site_fixture_ports_are_distinct_origins():
    assert same_site("http://127.0.0.1:8901/page", "http://127.0.0.1:8901/")
    assert not same_site("http://127.0.0.1:8902/", "http://127.0.0.1:8901/")


def test_private_host_detection():
    assert is_private_host("http://192.168.1.1/admin")
    assert is_private_host("http://localhost:8001/")
    assert is_private_host("http://api.internal/")
    assert not is_private_host("https://python.org/")


def test_clean_links_drops_junk_and_dedupes():
    raw = [
        {"href": "mailto:a@b.c", "text": "mail"},
        {"href": "javascript:void(0)", "text": "js"},
        {"href": "/contact", "text": "Contact"},
        {"href": "/contact/", "text": "Contact dup"},
        {"href": "https://other.com/x", "text": "ext"},
    ]
    links = clean_links("https://x.com/", raw, "https://x.com")
    hrefs = [item["href"] for item in links]
    assert hrefs.count("https://x.com/contact") == 1
    assert all(not h.startswith(("mailto:", "javascript:")) for h in hrefs)
    ext = next(item for item in links if item["href"].startswith("https://other.com"))
    assert ext["same_site"] is False


def test_intent_bilingual(hints):
    assert classify_intent("Find sales email on the site", hints) == "contact"
    assert classify_intent("Найди почту отдела продаж", hints) == "contact"
    assert classify_intent("Какая цена тарифа Pro", hints) == "pricing"
    assert classify_intent("Опиши дизайн и цвета сайта", hints) == "design_audit"
    assert classify_intent("Что-то совсем другое", hints) == "generic"
