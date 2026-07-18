#!/usr/bin/env python3
"""Юнит-проверки чистых функций спайка — без LLM, без браузера, без сети.

Usage: .venv/bin/python3 test_spike_units.py   (exit 0 = все проверки прошли)
"""

from __future__ import annotations

import sys

import benchmark_crawl as bc

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        print(f"  ok  {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL  {name}  {detail}")


# ---------------------------------------------------------------- normalize_url
check("norm: fragment strip", bc.normalize_url("https://x.com/a#sec") == "https://x.com/a")
check("norm: utm strip", bc.normalize_url("https://x.com/a?utm_source=tg&q=1")
      == "https://x.com/a?q=1")
check("norm: gclid/fbclid strip", "gclid" not in bc.normalize_url("https://x.com/?gclid=1&fbclid=2"))
check("norm: trailing slash", bc.normalize_url("https://x.com/about/") == bc.normalize_url("https://x.com/about"))
check("norm: root keeps slash", bc.normalize_url("https://x.com/") == "https://x.com/")
check("norm: host lowercase", bc.normalize_url("https://EXAMPLE.com/A") == "https://example.com/A")
check("norm: default port dropped", bc.normalize_url("https://x.com:443/a") == "https://x.com/a")
check("norm: custom port kept", ":8901" in bc.normalize_url("http://127.0.0.1:8901/a"))

# ---------------------------------------------------------------- same_site / registrable (OQ-2)
check("site: subdomain same registrable", bc.same_site("https://devguide.python.org/x", "https://www.python.org/"))
check("site: different domains", not bc.same_site("https://evil.com/", "https://python.org/"))
check("site: fixture ports distinct", not bc.same_site("http://127.0.0.1:8902/", "http://127.0.0.1:8901/"))
check("site: fixture same port", bc.same_site("http://127.0.0.1:8901/page/kontak", "http://127.0.0.1:8901/"))

# ---------------------------------------------------------------- is_allowed_target (I-H1/I-H8)
check("target: scheme block", not bc.is_allowed_target("javascript:alert(1)", "https://x.com/"))
check("target: file block", not bc.is_allowed_target("file:///etc/passwd", "https://x.com/"))
check("target: private host from public origin", not bc.is_allowed_target("http://192.168.1.1/admin", "https://x.com/"))

# ---------------------------------------------------------------- intent (RU+EN, D doc 21)
hints = bc.load_hints()
check("intent: EN contact", bc.classify_intent("Find sales email on the site", hints) == "contact")
check("intent: RU contact", bc.classify_intent("Найди почту отдела продаж", hints) == "contact")
check("intent: RU pricing", bc.classify_intent("Какая цена тарифа Pro", hints) == "pricing")
check("intent: RU design", bc.classify_intent("Опиши дизайн и цвета сайта", hints) == "design_audit")
check("intent: generic fallback", bc.classify_intent("Что-то совсем другое", hints) == "generic")

# ---------------------------------------------------------------- score_link (doc 21)
link_contact = {"href": "https://x.com/contact", "text": "Contact us"}
link_privacy = {"href": "https://x.com/privacy", "text": "Privacy"}
link_login = {"href": "https://x.com/login", "text": "Login"}
s_contact, _ = bc.score_link(link_contact, "contact", hints, "find contact email", on_homepage=True)
s_priv_contact, _ = bc.score_link(link_privacy, "contact", hints, "find contact email", on_homepage=False)
s_priv_pricing, _ = bc.score_link(link_privacy, "pricing", hints, "find price", on_homepage=False)
s_login, _ = bc.score_link(link_login, "contact", hints, "find contact", on_homepage=False)
check("score: contact slug boosted", s_contact >= 25, f"got {s_contact}")
check("score: legal boost only for contact intent", s_priv_contact > s_priv_pricing,
      f"{s_priv_contact} vs {s_priv_pricing}")
check("score: login penalized", s_login < 0, f"got {s_login}")

# ---------------------------------------------------------------- build_candidates (P0–P4, top-10)
snapshot = {
    "url": "http://127.0.0.1:8901/",
    "links": ([{"href": f"http://127.0.0.1:8901/page{i}", "text": f"Page {i}"} for i in range(15)]
              + [{"href": "http://127.0.0.1:8901/contact", "text": "Contact us"},
                 {"href": "http://127.0.0.1:8999/other", "text": "other site"}]),
}
cands = bc.build_candidates("hints", snapshot, None, "contact", hints, "find contact email",
                            "http://127.0.0.1:8901", visited=set(),
                            alive_probes=["http://127.0.0.1:8901/page/kontak"], legal_probes=[])
urls = [c["href"] for c in cands]
check("queue: top-10 cap", len(cands) <= 10, f"got {len(cands)}")
check("queue: intent link first", urls[0].endswith("/contact"), f"got {urls[:3]}")
check("queue: alive probe included", any(u.endswith("/page/kontak") for u in urls), f"{urls}")
check("queue: cross-origin excluded", all("8999" not in u for u in urls))
raw = bc.build_candidates("llm-only", snapshot, None, "contact", hints, "find contact",
                          "http://127.0.0.1:8901", visited=set(), alive_probes=[], legal_probes=[])
check("queue: llm-only no probes", all("kontak" not in c["href"] for c in raw))
visited_all = {bc.normalize_url(l["href"]) for l in snapshot["links"]}
empty = bc.build_candidates("hints", snapshot, None, "contact", hints, "find contact",
                            "http://127.0.0.1:8901", visited=visited_all,
                            alive_probes=[], legal_probes=[])
check("queue: visited excluded", len(empty) == 0, f"got {len(empty)}")

# ---------------------------------------------------------------- extract_json / strip_thinking
check("json: plain", bc.extract_json('{"a": 1}') == {"a": 1})
check("json: prose wrapped", bc.extract_json('Result:\n```json\n{"a": 1}\n```done') == {"a": 1})
check("json: braces inside strings", bc.extract_json('{"reasoning": "pick {contact} page", "a": 2}')
      == {"reasoning": "pick {contact} page", "a": 2})
check("json: thinking stripped", bc.extract_json('<think>{"draft": 0}</think>{"a": 3}') == {"a": 3})
check("json: garbage → None", bc.extract_json("no json here") is None)
check("json: broken then valid", bc.extract_json('{oops} {"a": 4}') == {"a": 4})

# ---------------------------------------------------------------- percentile
check("pctl: p50", bc.percentile([1, 2, 3, 4, 5], 50) == 3)
check("pctl: empty", bc.percentile([], 95) == 0.0)

print(f"\n{'PASS' if not FAILURES else 'FAIL'}: "
      f"{len(FAILURES)} failed" + (f" → {FAILURES}" if FAILURES else ""))
sys.exit(1 if FAILURES else 0)
