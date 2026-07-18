"""Synthesis validation lite (doc 13 § synthesis, Phase 1 подмножество):
S-H2 high-без-quote → downgrade; статус согласован с фактами.
Fuzzy quote⊆snapshot (S-H3) — Phase 2.
"""

from __future__ import annotations

from app.schemas.extraction import ExtractionResult


def validate_result(result: ExtractionResult) -> ExtractionResult:
    for fact in result.facts:
        if fact.confidence == "high" and not any(e.quote.strip() for e in fact.evidence):
            fact.confidence = "medium"  # S-H2 recovery: downgrade
    if result.status == "completed" and not result.facts:
        result.status = "not_found" if result.not_found else "partial"
    return result
