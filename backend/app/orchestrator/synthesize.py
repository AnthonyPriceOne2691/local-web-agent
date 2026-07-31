"""SYNTHESIZE-стадия: снапшоты → ExtractionResult (docs 05/16).

Вынесено из loop.py по той же причине, что DECIDE (`decide.py`) — держать машину
состояний тонкой и уложиться в лимит 500 LOC (doc 18). Тема модуля: **как из
собранных страниц получается результат run'а**, включая дисциплину свопа моделей
(nav → synth) перед тяжёлым вызовом.
"""

from __future__ import annotations

from app.config import Settings
from app.llm.ollama_client import OllamaClient
from app.llm.synthesizer import Synthesizer
from app.orchestrator.states import State
from app.schemas.extraction import ExtractionResult
from app.schemas.run import CrawlStep, RunRecord
from app.schemas.snapshot import PageSnapshot
from app.storage.run_store import RunStore


async def run_synthesis(
    record: RunRecord,
    snapshots: list[PageSnapshot],
    *,
    synthesizer: Synthesizer,
    llm: OllamaClient,
    store: RunStore,
    settings: Settings,
) -> ExtractionResult:
    if not snapshots:
        return ExtractionResult(status="failed", summary="no pages observed")
    record.steps.append(CrawlStep(index=len(record.steps) + 1, state=State.SYNTHESIZE))
    store.save(record)
    # Обе nav-модели выгружаются: лёгкая иначе держит ~5 GB, пока синтез идёт на
    # 16K ctx (дисциплина RAM, doc 14).
    await llm.unload_many(settings.nav_model, settings.nav_light_model)
    result, stats = await synthesizer.synthesize(
        task=record.config.task, snapshots=snapshots, intent=record.intent
    )
    record.steps[-1].llm_stats = stats
    return result
