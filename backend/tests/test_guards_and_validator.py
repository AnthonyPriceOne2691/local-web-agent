"""ContractEnforcer (I-H1/H6/H8/H9, G-H1/H2/H3/H5, I-S2) + extraction/validator + llm/parsing."""

from __future__ import annotations

import pytest

from app.contracts import guards
from app.contracts.context import ActionContext
from app.contracts.enforcer import ContractEnforcer
from app.extraction.validator import validate_result
from app.llm.parsing import extract_json
from app.schemas.extraction import Evidence, ExtractionResult, Fact
from app.schemas.snapshot import AgentAction
from tests.conftest import REPO_ROOT

ORIGIN = "https://x.com"


@pytest.fixture(scope="module")
def enforcer() -> ContractEnforcer:
    return ContractEnforcer.load(REPO_ROOT / "data" / "contracts")


def _ctx(**overrides) -> ActionContext:
    defaults = dict(
        origin=ORIGIN, start_url="https://x.com/", current_url="https://x.com/",
        candidates={"https://x.com/contact"}, visited=set(), hops={"https://x.com/": 0},
        max_depth=2, max_pages=10, pages_visited=1,
    )
    defaults.update(overrides)
    return ActionContext(**defaults)


def _nav(url: str) -> AgentAction:
    return AgentAction(action="navigate", url=url)


def test_ih6_rejects_url_outside_candidates(enforcer):
    hard, _ = enforcer.validate_navigate(_nav("https://x.com/invented"), _ctx())
    assert hard and hard.constraint_id == "I-H6"
    # except: [start_url] — стартовый URL валиден вне queue
    hard, _ = enforcer.validate_navigate(_nav("https://x.com/"), _ctx(visited=set()))
    assert hard is None or hard.constraint_id != "I-H6"


def test_ih1_h8_rejects_offsite_and_private(enforcer):
    # I-H1: чужой домен (в queue, чтобы дойти до domain-проверки)
    hard, _ = enforcer.validate_navigate(
        _nav("https://evil.com/x"), _ctx(candidates={"https://evil.com/x"}))
    assert hard and hard.constraint_id == "I-H1"
    # I-H8: private network с публичного origin
    hard, _ = enforcer.validate_navigate(
        _nav("http://192.168.1.1/admin"), _ctx(candidates={"http://192.168.1.1/admin"}))
    assert hard and hard.constraint_id in ("I-H1", "I-H8")
    # subdomain same site — ok
    hard, _ = enforcer.validate_navigate(
        _nav("https://blog.x.com/post"), _ctx(candidates={"https://blog.x.com/post"}))
    assert hard is None


def test_ih8_allow_private_override(enforcer):
    ctx = _ctx(candidates={"http://192.168.1.1/admin"}, allow_private=True)
    hard, _ = enforcer.validate_navigate(_nav("http://192.168.1.1/admin"), ctx)
    assert hard and hard.constraint_id == "I-H1"  # I-H8 снят флагом, I-H1 (домен) остаётся


def test_gh3_visited_and_gh2_hop_depth(enforcer):
    hard, _ = enforcer.validate_navigate(
        _nav("https://x.com/contact"), _ctx(visited={"https://x.com/contact"}))
    assert hard and hard.constraint_id == "G-H3"
    hard, _ = enforcer.validate_navigate(
        _nav("https://x.com/contact"), _ctx(hops={"https://x.com/": 2}))
    assert hard and hard.constraint_id == "G-H2"


def test_gh1_budget_first(enforcer):
    # бюджет проверяется раньше I-H6 (форс stop, не replan) — даже для мусорного URL
    hard, _ = enforcer.validate_navigate(_nav("https://x.com/junk"), _ctx(pages_visited=10))
    assert hard and hard.constraint_id == "G-H1"


def test_gh5_robots(enforcer):
    class DenyAll:
        def allowed(self, url: str) -> bool:
            return False

    hard, _ = enforcer.validate_navigate(_nav("https://x.com/contact"), _ctx(robots=DenyAll()))
    assert hard and hard.constraint_id == "G-H5"


def test_is2_legal_soft_avoid_vs_contact_boost(enforcer):
    # generic intent: legal-путь → soft violation, действие НЕ отклонено
    ctx = _ctx(candidates={"https://x.com/privacy"}, intent="generic")
    hard, softs = enforcer.validate_navigate(_nav("https://x.com/privacy"), ctx)
    assert hard is None
    assert softs and softs[0].constraint_id == "I-S2" and softs[0].severity == "soft"
    # contact intent: boost — никакого violation
    ctx = _ctx(candidates={"https://x.com/privacy"}, intent="contact")
    hard, softs = enforcer.validate_navigate(_nav("https://x.com/privacy"), ctx)
    assert hard is None and not softs


def test_config_checks_and_recovery(enforcer):
    from app.schemas.run import RunConfig

    bad = RunConfig(start_url="ftp://x.com", task="t")
    violations = enforcer.check_run_config(bad)
    assert any(v.constraint_id == "P-1" and v.severity == "hard" for v in violations)
    # rate floor: публичный хост клэмпится, private (fixtures) — нет
    fast = RunConfig(start_url="https://x.com", task="t", rate_limit_ms=0)
    assert enforcer.effective_rate_ms(fast.rate_limit_ms, fast.start_url) == 1000
    assert any(v.constraint_id == "G-H4" and v.severity == "soft"
               for v in enforcer.check_run_config(fast))
    assert enforcer.effective_rate_ms(0, "http://127.0.0.1:8901/") == 0
    assert enforcer.effective_timeout_ms(60000) == 30000  # G-H6 ceiling
    assert enforcer.max_replans_per_step == 2  # recovery k=2 (doc 13)


def test_rule_primitives_edge_cases(enforcer):
    from app.contracts.rules import budget, navigation
    from app.schemas.run import RunConfig

    # I-H8: не-http scheme и private→private (fixtures)
    v = navigation.public_http_url("I-H8", {}, _nav("ftp://x.com/f"), _ctx())
    assert v and "scheme" in v.message
    ctx_priv = _ctx(origin="http://127.0.0.1:8901",
                    candidates={"http://127.0.0.1:8901/a"})
    assert navigation.public_http_url("I-H8", {}, _nav("http://127.0.0.1:8901/a"), ctx_priv) is None
    # I-H2: запрещённый тип действия (schema Literal не пустит, но правило — страховка)
    act = AgentAction.model_construct(action="submit", url=None, reasoning="", confidence="low")
    v = navigation.action_not_in("I-H2", {"forbidden": ["submit"]}, act, _ctx())
    assert v and v.constraint_id == "I-H2"
    # G-H6: конфиг без page_timeout_ms → нет violation; с полем выше ceiling → soft
    assert budget.page_timeout_ceiling("G-H6", {"max": 30000},
                                       RunConfig(start_url="https://x.com", task="t")) is None
    # non_empty: пробельная task (Pydantic пропускает ' ', контракт ловит)
    cfg = RunConfig(start_url="https://x.com", task=" ")
    assert budget.non_empty("P-2", {"field": "task"}, cfg) is not None
    # empty contract dir → пустые forbidden paths
    from app.contracts.loader import load_forbidden_paths
    assert load_forbidden_paths(REPO_ROOT / "data" / "contracts" / "nope.txt") == ()


def test_loader_rejects_unknown_check(tmp_path):
    from app.contracts.loader import load_contract

    bad = tmp_path / "bad.contract.yaml"
    bad.write_text("mode: crawl\ninvariants:\n  hard:\n    - id: x\n      check: no_such_check\n")
    with pytest.raises(ValueError, match="unknown check"):
        load_contract(bad)


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
