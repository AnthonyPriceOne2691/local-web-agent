"""VISION_BATCH шаг (doc 23): после crawl loop, до SYNTHESIZE.

Браузер уже закрыт вызывающей стороной (P-V3); insights пишутся в снапшоты,
агрегаты — в record.metadata. Vision не валит run.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.config import Settings
from app.llm.ollama_client import OllamaClient
from app.orchestrator.states import State
from app.schemas.run import CrawlStep, RunRecord
from app.schemas.snapshot import PageSnapshot
from app.storage.run_store import RunStore
from app.vision.analyzer import VisionAnalyzer
from app.vision.loader import VisionLoader, VisionLoadError
from app.vision.schemas import VisionInsight
from app.vision.selection import select_vision_jobs, vision_wanted


async def run_vision_batch(
    *,
    record: RunRecord,
    snapshots: list[PageSnapshot],
    settings: Settings,
    store: RunStore,
    llm: OllamaClient,
    analyzer: VisionAnalyzer,
    close_browser: Callable[[], Awaitable[None]],
    cancel_event: asyncio.Event | None = None,
) -> None:
    cfg = record.config
    if not vision_wanted(cfg.vision_enabled, record.intent, cfg.task, snapshots):
        return
    jobs, skipped = select_vision_jobs(
        snapshots, intent=record.intent, mode=cfg.vision_enabled,
        max_pages=settings.max_vision_pages, max_calls=settings.max_vision_calls,
    )
    if not jobs:
        return
    record.steps.append(CrawlStep(index=len(record.steps) + 1, state=State.VISION_BATCH))
    store.save(record)
    await close_browser()  # P-V3: браузер закрыт до загрузки VLM (RAM discipline)
    await llm.unload(settings.nav_model)
    loader = VisionLoader.load(store.artifacts_dir(record.id).parent, settings.contracts_dir)
    allowlist = {shot.relative_path for s in snapshots for shot in s.screenshots}
    calls = failures = 0
    for job in jobs:
        if cancel_event is not None and cancel_event.is_set():  # граница между вызовами
            break
        try:
            image = loader.read_base64(record.id, job.shot.relative_path, allowlist=allowlist)
        except VisionLoadError as exc:  # V-H1/H2/H3 → skip call (doc 13 recovery)
            job.snapshot.vision_insights.append(
                VisionInsight(profile=job.shot.profile, url=job.snapshot.url,
                              status="skipped", confidence="low", error=exc.reason).model_dump())
            continue
        insight = await analyzer.analyze(
            image_base64=image, task=cfg.task, url=job.snapshot.url,
            profile=job.shot.profile, dom_excerpt=job.snapshot.main_text,
        )
        calls += 1
        failures += insight.status != "ok"
        job.snapshot.vision_insights.append(insight.model_dump())
    await llm.unload(settings.vision_model)  # evict VLM → R1 (doc 23 swap)
    record.metadata.update({
        "vision_enabled": cfg.vision_enabled,
        "vision_pages_analyzed": len({j.snapshot.url for j in jobs}),
        "vision_calls_total": calls,
        "vision_failures": failures,
        "vision_partial": calls < len(jobs),
    })
    if skipped:
        record.metadata["vision_skipped_pages"] = skipped
    store.save(record)
