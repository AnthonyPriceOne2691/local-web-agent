"""SynthesisValidator (doc 13 § Mode: Synthesis, Phase 2): S-H2/S-H3/S-G1/S-G2.

S-H3 — in-memory во время synthesis (снапшоты ещё загружены), rapidfuzz
partial_ratio ≥ fuzzy-порога из synthesis.contract.yaml. Recovery по доке:
непрошедшая цитата → drop evidence; факт без выживших evidence → remove + not_found.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app.contracts.loader import ContractSpec, load_contract
from app.extraction.validator import validate_result
from app.schemas.extraction import Evidence, ExtractionResult, NotFound
from app.schemas.snapshot import PageSnapshot

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def _visited_url_in_value(value: str, snapshots: list[PageSnapshot]) -> str | None:
    """S-H3c: value содержит URL посещённой страницы → визит и есть evidence.
    Fabricated URL (не из visited) под правило не попадает."""
    value_l = value.lower()
    for snap in snapshots:
        if snap.url.lower().rstrip("/") in value_l:
            return snap.url
    return None


def _vision_text(ins: dict[str, Any]) -> str:
    """Текст vision-инсайта для S-H3b-матчинга: description + extracted + design."""
    parts = [str(ins.get("description", ""))]
    parts += [f"{e.get('key', '')} {e.get('value', '')}" for e in ins.get("extracted", [])]
    parts += [str(t) for t in ins.get("text_not_in_dom", [])]
    parts += [str(v) for v in (ins.get("design") or {}).values()]
    return " ".join(parts)


class SynthesisValidator:
    def __init__(self, spec: ContractSpec | None = None):
        params = {r.check: r.params for r in spec.invariants_hard + spec.governance_hard} if spec else {}
        self._fuzzy = float(params.get("evidence_substring", {}).get("fuzzy", 0.85))
        self._max_facts = int(params.get("facts_budget", {}).get("max", 20))

    @classmethod
    def load(cls, contracts_dir: Path) -> SynthesisValidator:
        return cls(load_contract(contracts_dir / "synthesis.contract.yaml"))

    def validate(self, result: ExtractionResult, snapshots: list[PageSnapshot]) -> ExtractionResult:
        pages = {s.url: _norm(f"{s.title} {s.main_text}") for s in snapshots}
        all_text = " ".join(pages.values())
        vision_pages = {
            s.url: _norm(
                " ".join(_vision_text(ins) for ins in s.vision_insights if ins.get("status") == "ok")
            )
            for s in snapshots
            if s.vision_insights
        }
        all_vision = " ".join(vision_pages.values())

        if len(result.facts) > self._max_facts:  # S-G2: truncate + log
            result.facts = result.facts[: self._max_facts]

        kept, removed_keys = [], []
        for fact in result.facts:
            fact.evidence = [
                ev for ev in fact.evidence if self._evidence_ok(ev, pages, all_text, vision_pages, all_vision)
            ]
            if not fact.evidence:  # S-H3c: URL-факт — визит страницы сам по себе пруф
                visited_url = _visited_url_in_value(fact.value, snapshots)
                if visited_url:
                    fact.evidence = [Evidence(url=visited_url, quote="")]
                    if fact.confidence == "high":
                        fact.confidence = "medium"
            quoted = [ev for ev in fact.evidence if ev.quote.strip() and ev.source != "vision"]
            if fact.evidence or fact.confidence != "high":
                if fact.confidence == "high" and not quoted:
                    fact.confidence = "medium"  # S-H2 после фильтра цитат
                vision_only = fact.evidence and all(ev.source == "vision" for ev in fact.evidence)
                if fact.confidence == "high" and vision_only:
                    fact.confidence = "medium"  # S-H6: vision-only не может быть high
                kept.append(fact)
            else:
                removed_keys.append(fact.key)  # S-H3 recovery: remove → not_found
        result.facts = kept
        for key in removed_keys:
            if not any(nf.key == key for nf in result.not_found):
                result.not_found.append(NotFound(key=key, reason="evidence quote not found in visited pages"))
        self._enrich_article(result, snapshots)
        return validate_result(result)  # S-H2 базовый + статус-согласование (S-G1)

    @staticmethod
    def _enrich_article(result: ExtractionResult, snapshots: list[PageSnapshot]) -> None:
        """Article excerpt/word_count подставляет КОД из снапшота (verbatim, до 12K —
        doc 20); LLM возвращает только url+мету и не перепечатывает статью в output."""
        article = result.article
        if article is None:
            return
        from app.observer.links import normalize_url

        target = normalize_url(article.url)
        source = next((s for s in snapshots if normalize_url(s.url) == target), None)
        if source is None:  # URL статьи не из посещённых → блок недостоверен
            result.article = None
            return
        article.main_text_excerpt = source.main_text[:12000]
        if article.word_count < 50:  # мусор LLM («14 min read» → 14) — считаем сами
            article.word_count = len(source.main_text.split())
        if not article.title:
            article.title = source.title

    def _evidence_ok(
        self,
        ev: Evidence,
        pages: dict[str, Any],
        all_text: str,
        vision_pages: dict[str, str],
        all_vision: str,
    ) -> bool:
        """S-H3a: DOM-цитата ⊆ snapshot text; S-H3b: vision-evidence не проверяется
        против DOM. Цитата не из DOM, но найденная в vision-инсайтах →
        переклассифицируется в source=vision (модель не всегда ставит source сама)."""
        if ev.source == "vision" or not ev.quote.strip():
            return True
        if self._quote_found(ev.quote, pages.get(ev.url), all_text):
            return True
        if vision_pages and self._vision_match(ev.quote, vision_pages.get(ev.url, all_vision)):
            ev.source = "vision"
            return True
        return False

    def _vision_match(self, quote: str, vision_text: str) -> bool:
        """Перефраз со скриншота: token_set_ratio (устойчив к вставкам слов),
        в отличие от verbatim-семантики S-H3a (partial_ratio)."""
        if not vision_text:
            return False
        return fuzz.token_set_ratio(_norm(quote), vision_text) >= self._fuzzy * 100

    def _quote_found(self, quote: str, page_text: str | None, all_text: str) -> bool:
        q = _norm(quote)
        if not q:
            return True
        haystack = page_text if page_text else all_text
        if q in haystack:
            return True
        score = fuzz.partial_ratio(q, haystack)
        return score >= self._fuzzy * 100
