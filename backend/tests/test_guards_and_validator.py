"""contracts/guards (I-H1/H6/H8/H9, G-H1/H2/H3) + extraction/validator + llm/parsing."""

from __future__ import annotations

from app.contracts import guards
from app.extraction.validator import validate_result
from app.llm.parsing import extract_json
from app.schemas.extraction import Evidence, ExtractionResult, Fact
from app.schemas.snapshot import AgentAction, Candidate

ORIGIN = "https://x.com"
CANDS = [Candidate(href="https://x.com/contact", text="Contact")]


def _validate(url: str, **overrides):
    defaults = dict(
        candidates=CANDS, origin=ORIGIN, visited=set(), hops={"https://x.com/": 0},
        current_url="https://x.com/", max_depth=2, max_pages=10, pages_visited=1,
    )
    defaults.update(overrides)
    return guards.validate_navigate(AgentAction(action="navigate", url=url), **defaults)


def test_ih6_rejects_url_outside_candidates():
    v = _validate("https://x.com/invented")
    assert v and v.constraint_id == "I-H6"


def test_ih1_h8_rejects_offsite_and_private():
    assert guards.allowed_target("https://evil.com/", ORIGIN) is False
    assert guards.allowed_target("http://192.168.1.1/admin", ORIGIN) is False
    assert guards.allowed_target("javascript:alert(1)", ORIGIN) is False
    assert guards.allowed_target("https://blog.x.com/post", ORIGIN) is True


def test_gh3_visited_and_gh2_hop_depth():
    v = _validate("https://x.com/contact", visited={"https://x.com/contact"})
    assert v and v.constraint_id == "G-H3"
    v = _validate("https://x.com/contact", hops={"https://x.com/": 2}, max_depth=2)
    assert v and v.constraint_id == "G-H2"


def test_gh1_budget():
    v = _validate("https://x.com/contact", pages_visited=10, max_pages=10)
    assert v and v.constraint_id == "G-H1"


def test_ih9_redirect_step0_adopts_landing_domain():
    ok, new_origin = guards.check_redirect("https://x.io/home", ORIGIN, first_navigation=True)
    assert ok and new_origin == "https://x.io"
    ok, origin2 = guards.check_redirect("https://x.io/home", ORIGIN, first_navigation=False)
    assert not ok and origin2 == ORIGIN
    ok, _ = guards.check_redirect("http://192.168.0.1/", ORIGIN, first_navigation=True)
    assert not ok  # private блокируется даже на step 0


def test_validator_downgrades_high_without_quote():
    result = ExtractionResult(
        facts=[
            Fact(key="a", value="1", confidence="high", evidence=[Evidence(url="u", quote="")]),
            Fact(key="b", value="2", confidence="high", evidence=[Evidence(url="u", quote="proof")]),
        ]
    )
    out = validate_result(result)
    assert out.facts[0].confidence == "medium"  # S-H2 downgrade
    assert out.facts[1].confidence == "high"


def test_validator_status_consistency():
    assert validate_result(ExtractionResult(status="completed")).status == "partial"
    r = ExtractionResult(status="completed", not_found=[{"key": "x", "reason": "absent"}])
    assert validate_result(r).status == "not_found"


def test_extract_json_robust():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('prose ```json\n{"a": 1}\n``` done') == {"a": 1}
    assert extract_json('{"reasoning": "pick {contact}", "a": 2}')["a"] == 2
    assert extract_json('<think>{"draft": 0}</think>{"a": 3}') == {"a": 3}
    assert extract_json("no json") is None
    assert extract_json('{oops} {"a": 4}') == {"a": 4}
