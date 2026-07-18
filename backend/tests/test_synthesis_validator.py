"""SynthesisValidator (S-H2/S-H3/S-H6, S-G2): fuzzy quote check, remove→not_found."""

from __future__ import annotations

import pytest

from app.extraction.synthesis_validator import SynthesisValidator
from app.schemas.extraction import Evidence, ExtractionResult, Fact
from app.schemas.snapshot import PageSnapshot
from tests.conftest import REPO_ROOT

URL = "https://x.com/contact"


@pytest.fixture(scope="module")
def validator() -> SynthesisValidator:
    return SynthesisValidator.load(REPO_ROOT / "data" / "contracts")


def _snapshots(text: str = "Call us at +1 555 123 4567, office in Berlin.") -> list[PageSnapshot]:
    return [PageSnapshot(url=URL, title="Contact", main_text=text)]


def _fact(quote: str, *, key: str = "phone", confidence: str = "high", source: str = "dom") -> Fact:
    return Fact(key=key, value="+1 555 123 4567", confidence=confidence,
                evidence=[Evidence(url=URL, quote=quote, source=source)])


def test_exact_and_fuzzy_quotes_pass(validator):
    result = ExtractionResult(facts=[
        _fact("Call us at +1 555 123 4567"),                       # exact
        _fact("Call us at +1  555 123 4567, office in Berlin", key="k2"),  # whitespace/fuzzy
    ])
    out = validator.validate(result, _snapshots())
    assert [f.confidence for f in out.facts] == ["high", "high"]
    assert not out.not_found


def test_fabricated_quote_removes_fact_to_not_found(validator):
    result = ExtractionResult(facts=[_fact("Our HQ is on the Moon since 1969")])
    out = validator.validate(result, _snapshots())
    assert not out.facts
    assert out.not_found and out.not_found[0].key == "phone"
    assert "quote not found" in out.not_found[0].reason
    assert out.status == "not_found"  # S-G1 статус согласован


def test_partial_evidence_filtered_keeps_fact(validator):
    fact = Fact(key="phone", value="+1 555 123 4567", confidence="high", evidence=[
        Evidence(url=URL, quote="Call us at +1 555 123 4567"),
        Evidence(url=URL, quote="totally made up quote about llamas"),
    ])
    out = validator.validate(ExtractionResult(facts=[fact]), _snapshots())
    assert len(out.facts) == 1 and len(out.facts[0].evidence) == 1
    assert out.facts[0].confidence == "high"


def test_unknown_url_falls_back_to_all_pages_text(validator):
    fact = _fact("office in Berlin")
    fact.evidence[0].url = "https://x.com/other-page"
    out = validator.validate(ExtractionResult(facts=[fact]), _snapshots())
    assert out.facts  # цитата найдена в общем тексте


def test_vision_only_high_downgraded_sh6(validator):
    fact = Fact(key="hero_color", value="blue", confidence="high",
                evidence=[Evidence(url=URL, quote="", source="vision")])
    out = validator.validate(ExtractionResult(facts=[fact]), _snapshots())
    assert out.facts[0].confidence == "medium"


def test_vision_quote_not_in_dom_survives_sh3b(validator):
    """S-H3b: vision-цитата (текст со скриншота, в DOM отсутствует) не режется S-H3."""
    fact = Fact(key="price", value="$49/mo", confidence="high",
                evidence=[Evidence(url=URL, quote="Team $49/mo", source="vision")])
    out = validator.validate(ExtractionResult(facts=[fact]), _snapshots())
    assert out.facts and out.facts[0].value == "$49/mo"
    assert out.facts[0].confidence == "medium"  # S-H6: vision-only ≠ high
    assert out.facts[0].evidence  # evidence сохранён
    assert not out.not_found


def test_dom_quote_matching_vision_reclassified(validator):
    """Модель не поставила source=vision — цитата из vision-инсайта переклассифицируется."""
    snap = PageSnapshot(url=URL, title="SPA", main_text="tiny",
                        vision_insights=[{"status": "ok", "profile": "desktop",
                                          "description": "Team plan card shows $49/month",
                                          "extracted": [{"key": "team_price",
                                                         "value": "$49/month"}]}])
    fact = Fact(key="price", value="$49/month", confidence="high",
                evidence=[Evidence(url=URL, quote="Team plan $49/month", source="dom")])
    out = validator.validate(ExtractionResult(facts=[fact]), [snap])
    assert out.facts and out.facts[0].evidence[0].source == "vision"  # reclass S-H3b
    assert out.facts[0].confidence == "medium"  # S-H6 после reclass
    assert not out.not_found


def test_url_fact_survives_as_self_evidence_sh3c(validator):
    """S-H3c: value = URL посещённой страницы; провал цитаты → medium, не смерть."""
    snap = PageSnapshot(url="https://x.com/search", title="Search",
                        main_text="model cards grid")
    fact = Fact(key="search_url", value="The search page is https://x.com/search",
                confidence="high",
                evidence=[Evidence(url="https://x.com/search",
                                   quote="totally paraphrased nonsense quote")])
    out = validator.validate(ExtractionResult(facts=[fact]), [snap])
    assert out.facts and out.facts[0].confidence == "medium"
    assert out.facts[0].evidence[0].url == "https://x.com/search"
    assert not out.not_found
    # негатив: URL НЕ из visited → факт по-прежнему режется
    bad = Fact(key="u", value="see https://x.com/invented-page", confidence="high",
               evidence=[Evidence(url="https://x.com/search", quote="nonsense")])
    out = validator.validate(ExtractionResult(facts=[bad]), [snap])
    assert not out.facts and out.not_found


def test_facts_truncated_to_contract_max(validator):
    facts = [_fact("Call us at +1 555 123 4567", key=f"k{i}", confidence="medium")
             for i in range(25)]
    out = validator.validate(ExtractionResult(facts=facts), _snapshots())
    assert len(out.facts) == 20  # S-G2


def test_article_enriched_from_snapshot_code_side():
    """Excerpt/word_count статьи подставляет код из снапшота, не LLM-перепечатка."""
    from app.schemas.extraction import Article

    v = SynthesisValidator()
    long_text = "Odds formats explained with worked examples. " * 400  # > 12K chars
    snap = PageSnapshot(url="https://x.com/blog/guide", title="Guide",
                        main_text=long_text)
    result = ExtractionResult(
        status="completed", summary="found",
        article=Article(url="https://x.com/blog/guide/", title="",
                        main_text_excerpt="short quote"))
    out = v.validate(result, [snap])  # трейлинг-слэш нормализуется
    assert len(out.article.main_text_excerpt) == 12000
    assert out.article.word_count == len(long_text.split())
    assert out.article.title == "Guide"
    # url статьи не из посещённых → блок отбрасывается
    bad = ExtractionResult(status="completed", summary="s",
                           article=Article(url="https://x.com/invented"))
    assert v.validate(bad, [snap]).article is None


def test_article_word_count_coercion():
    from app.schemas.extraction import Article

    assert Article(url="u", word_count="≈2400 words").word_count == 2400
    assert Article(url="u", word_count=None).word_count == 0


def test_defaults_without_spec():
    v = SynthesisValidator()
    assert v._fuzzy == 0.85 and v._max_facts == 20
