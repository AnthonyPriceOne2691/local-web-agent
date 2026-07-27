"""observer/snapshot (truncation, blockers) + navigation/candidate_queue (P0–P4, top-K)."""

from __future__ import annotations

from app.navigation.candidate_queue import build_candidates
from app.observer.snapshot import INTERACTIVE_CAP, MAIN_TEXT_CAP, build_snapshot
from tests.conftest import page_raw

ORIGIN = "http://127.0.0.1:8901"


def snap(url: str, **kwargs):
    return build_snapshot(page_raw(**kwargs), page_url=url, origin=ORIGIN)


def test_truncation_caps_main_text():
    s = snap(f"{ORIGIN}/", title="T", text="x" * (MAIN_TEXT_CAP + 500))
    assert len(s.main_text) == MAIN_TEXT_CAP
    assert s.truncated is True


def test_blocker_detection_login_and_captcha():
    assert snap(f"{ORIGIN}/login", title="Sign in", text="password").status == "login_wall"
    assert snap(f"{ORIGIN}/x", title="", text="hello", password=True).status == "login_wall"
    cf = snap(f"{ORIGIN}/y", title="Attention", text="Checking your browser before accessing")
    assert cf.status == "captcha"
    assert snap(f"{ORIGIN}/ok", title="Fine", text="normal content here").status == "ok"


def test_queue_priorities_and_top_k(hints):
    links = [(f"{ORIGIN}/page{i}", f"Page {i}") for i in range(15)]
    links += [(f"{ORIGIN}/contact", "Contact us"), ("http://127.0.0.1:9999/ext", "other")]
    s = snap(f"{ORIGIN}/", title="Home", text="welcome " * 50, links=links)
    cands = build_candidates(
        snapshot=s,
        homepage=None,
        intent="contact",
        task="find contact email",
        hints=hints,
        origin=ORIGIN,
        visited=set(),
        alive_probes=[f"{ORIGIN}/page/kontak"],
        legal_probes=[],
    )
    hrefs = [c.href for c in cands]
    assert len(cands) <= 10
    assert hrefs[0].endswith("/contact")  # P0 intent link первым
    assert any(h.endswith("/page/kontak") for h in hrefs)  # P2 alive probe
    assert all("9999" not in h for h in hrefs)  # чужой origin исключён


def test_queue_excludes_visited(hints):
    s = snap(f"{ORIGIN}/", title="Home", text="w " * 200, links=[(f"{ORIGIN}/a", "A")])
    cands = build_candidates(
        snapshot=s,
        homepage=None,
        intent="generic",
        task="anything at all",
        hints=hints,
        origin=ORIGIN,
        visited={f"{ORIGIN}/a"},
        alive_probes=[],
        legal_probes=[],
    )
    assert cands == []


# --- interactive elements (doc 25 A-1: element referencing) ---


def test_interactive_elements_parsed_and_indexed():
    raw = page_raw(
        title="Contact",
        text="reach us",
        interactive=[
            {"kind": "text", "label": "Name", "input_type": "text", "name": "name"},
            {"kind": "email", "label": "Email", "input_type": "email", "name": "email"},
            {"kind": "button", "label": "Send"},
        ],
    )
    els = build_snapshot(raw, page_url=f"{ORIGIN}/contact", origin=ORIGIN).interactive_elements
    assert [e.index for e in els] == [0, 1, 2]
    assert els[1].kind == "email" and els[1].input_type == "email" and els[1].name == "email"
    assert els[2].kind == "button" and els[2].label == "Send"


def test_interactive_elements_cap_and_reindex():
    many = [{"kind": "button", "label": f"b{i}"} for i in range(INTERACTIVE_CAP + 12)]
    els = snap(f"{ORIGIN}/", title="T", text="x", interactive=many).interactive_elements
    assert len(els) == INTERACTIVE_CAP
    assert [e.index for e in els] == list(range(INTERACTIVE_CAP))  # contiguous reindex после cap


def test_interactive_label_truncated():
    els = snap(
        f"{ORIGIN}/", title="T", text="x", interactive=[{"kind": "button", "label": "z" * 300}]
    ).interactive_elements
    assert len(els[0].label) == 120


def test_snapshot_without_interactive_key_is_empty():
    # backward-compat: старый raw без ключа interactive (напр. FakeBrowser-страницы)
    s = build_snapshot({"title": "T", "main_text": "hi"}, page_url=f"{ORIGIN}/", origin=ORIGIN)
    assert s.interactive_elements == []
