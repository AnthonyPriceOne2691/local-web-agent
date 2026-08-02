"""Источники кандидатов P1–P4 — покрытие ДО разбора `build_candidates`.

Существующие тесты (`test_snapshot_and_queue`) проверяют порядок P0/P2 и отсев
visited/чужого origin. Не покрыты были ровно те ветки, которые разбор двигает:
ссылки закэшированной homepage, ссылки с F1-проб, sitemap и legal-пробы, а также
дедупликация между источниками. Покрытие модуля до: 74 %.
"""

from __future__ import annotations

from app.navigation.candidate_queue import build_candidates
from tests.test_snapshot_and_queue import ORIGIN, snap


def test_homepage_links_come_as_p1_with_home_prefix(hints) -> None:
    """Ссылки кэшированной homepage попадают в очередь помеченными «home:»."""
    home = snap(f"{ORIGIN}/", title="Home", text="w " * 60, links=[(f"{ORIGIN}/contact", "Contact us")])
    inner = snap(f"{ORIGIN}/about", title="About", text="w " * 60, links=[])

    cands = build_candidates(
        snapshot=inner,
        homepage=home,
        intent="contact",
        task="найди контакты",
        hints=hints,
        origin=ORIGIN,
        visited=set(),
        alive_probes=[],
        legal_probes=[],
    )

    contact = [c for c in cands if c.href.endswith("/contact")]
    assert contact, "ссылка с homepage обязана дойти до очереди"
    assert contact[0].reason.startswith("home:"), "источник обязан быть виден в reason"


def test_probe_links_are_tagged_f1(hints) -> None:
    """Ссылки, найденные F1-пробой, помечаются «f1:» — иначе не отличить от DOM."""
    page = snap(f"{ORIGIN}/", title="Home", text="w " * 60, links=[])

    cands = build_candidates(
        snapshot=page,
        homepage=None,
        intent="contact",
        task="найди контакты",
        hints=hints,
        origin=ORIGIN,
        visited=set(),
        alive_probes=[],
        legal_probes=[],
        probe_links=[{"href": f"{ORIGIN}/kontakty", "text": "Контакты"}],
    )

    assert [c.reason.startswith("f1:") for c in cands if c.href.endswith("/kontakty")] == [True]


def test_sitemap_and_legal_probes_fill_lower_buckets(hints) -> None:
    """P2.5 sitemap и P3 legal идут ниже P0/P2, но в очередь попадают."""
    page = snap(f"{ORIGIN}/", title="Home", text="w " * 60, links=[])

    cands = build_candidates(
        snapshot=page,
        homepage=None,
        intent="generic",
        task="что угодно",
        hints=hints,
        origin=ORIGIN,
        visited=set(),
        alive_probes=[f"{ORIGIN}/probe"],
        legal_probes=[f"{ORIGIN}/impressum"],
        sitemap_urls=[f"{ORIGIN}/from-sitemap"],
    )

    reasons = {c.href: c.reason for c in cands}
    assert reasons[f"{ORIGIN}/probe"] == "probe"
    assert reasons[f"{ORIGIN}/from-sitemap"] == "sitemap"
    assert reasons[f"{ORIGIN}/impressum"] == "legal-probe"
    order = [c.href for c in cands]
    assert (
        order.index(f"{ORIGIN}/probe")
        < order.index(f"{ORIGIN}/from-sitemap")
        < order.index(f"{ORIGIN}/impressum")
    ), "порядок вёдер P2 → P2.5 → P3 фиксирован (doc 21)"


def test_same_url_from_two_sources_appears_once(hints) -> None:
    """Один URL из DOM и из sitemap — один кандидат, с приоритетом более раннего ведра."""
    page = snap(f"{ORIGIN}/", title="Home", text="w " * 60, links=[(f"{ORIGIN}/contact", "Contact us")])

    cands = build_candidates(
        snapshot=page,
        homepage=None,
        intent="contact",
        task="найди контакты",
        hints=hints,
        origin=ORIGIN,
        visited=set(),
        alive_probes=[],
        legal_probes=[],
        sitemap_urls=[f"{ORIGIN}/contact"],
    )

    contacts = [c for c in cands if c.href.rstrip("/").endswith("/contact")]
    assert len(contacts) == 1, f"дубль между источниками: {[c.reason for c in contacts]}"
    assert contacts[0].reason != "sitemap", "побеждает более раннее ведро, а не sitemap"


def test_visited_filtered_in_every_source(hints) -> None:
    """visited отсекается во всех источниках, а не только в ссылках страницы."""
    page = snap(f"{ORIGIN}/", title="Home", text="w " * 60, links=[(f"{ORIGIN}/a", "A")])

    cands = build_candidates(
        snapshot=page,
        homepage=None,
        intent="generic",
        task="что угодно",
        hints=hints,
        origin=ORIGIN,
        visited={f"{ORIGIN}/a", f"{ORIGIN}/probe", f"{ORIGIN}/from-sitemap", f"{ORIGIN}/impressum"},
        alive_probes=[f"{ORIGIN}/probe"],
        legal_probes=[f"{ORIGIN}/impressum"],
        sitemap_urls=[f"{ORIGIN}/from-sitemap"],
        probe_links=[{"href": f"{ORIGIN}/a", "text": "A"}],
    )

    assert cands == []
