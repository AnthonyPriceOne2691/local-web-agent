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


def test_keyword_matches_word_start_not_any_substring(hints):
    """`ui` из дизайн-словаря не должен ловиться внутри `guide` / `build`.

    Найдено real-site прогоном 2026-08-01: задача «find the getting started guide,
    whose is the most thorough» по сайтам вида `docs.astro.build` классифицировалась
    как сравнение дизайна, и в сравнение уезжала рубрика `design_diff` — таблица
    заполнялась цветами и типографикой вместо полноты содержания.
    """
    assert classify_intent("Find the getting started guide", hints) != "design_audit"
    assert classify_intent("Read the docs on astro.build", hints) != "design_audit"
    # стем по-прежнему работает: «дизайна» совпадает с «дизайн»
    assert classify_intent("Опиши особенности дизайна сайта", hints) == "design_audit"


def test_research_intent_content_task_is_not_design():
    from app.research.meta_agent import classify_research_intent

    content = (
        "Compare these three: https://docs.astro.build https://gohugo.io "
        "https://www.11ty.dev — find the getting started guide on each and tell me "
        "whose is the most thorough, and why."
    )
    assert classify_research_intent(content, 3) == "comparative_content"
    design = "Take a look at a.com and b.com — describe the design and layout of each"
    assert classify_research_intent(design, 2) == "comparative_design"
