"""SynthesisValidator (doc 13 § Mode: Synthesis, Phase 2): S-H2/S-H3/S-G1/S-G2.

S-H3 — in-memory во время synthesis (снапшоты ещё загружены), rapidfuzz
partial_ratio ≥ fuzzy-порога из synthesis.contract.yaml. Recovery по доке:
непрошедшая цитата → drop evidence; факт без выживших evidence → remove + not_found.
"""

from __future__ import annotations

import re
from pathlib import Path

from rapidfuzz import fuzz

from app.contracts.loader import ContractSpec, load_contract
from app.extraction.validator import validate_result
from app.schemas.extraction import ExtractionResult, NotFound
from app.schemas.snapshot import PageSnapshot

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


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

        if len(result.facts) > self._max_facts:  # S-G2: truncate + log
            result.facts = result.facts[: self._max_facts]

        kept, removed_keys = [], []
        for fact in result.facts:
            fact.evidence = [
                ev for ev in fact.evidence
                if not ev.quote.strip() or self._quote_found(ev.quote, pages.get(ev.url), all_text)
            ]
            quoted = [ev for ev in fact.evidence if ev.quote.strip()]
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
                result.not_found.append(
                    NotFound(key=key, reason="evidence quote not found in visited pages")
                )
        return validate_result(result)  # S-H2 базовый + статус-согласование (S-G1)

    def _quote_found(self, quote: str, page_text: str | None, all_text: str) -> bool:
        q = _norm(quote)
        if not q:
            return True
        haystack = page_text if page_text else all_text
        if q in haystack:
            return True
        score = fuzz.partial_ratio(q, haystack)
        return score >= self._fuzzy * 100
