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


def unreached_urls(record: RunRecord) -> list[str]:
    """Страницы, которые агент выбрал, но не открыл из-за СВОИХ лимитов.

    Нужно, чтобы синтез не путал «мы не дошли» с «на сайте этого нет» (doc 26
    § T-3a-2). Берутся hard-нарушения с целевым URL, которые не удалось обойти:
    hop depth (G-H2), бюджет страниц, robots. Порядок сохраняется, дубли убираются —
    на живых прогонах модель предлагала один и тот же URL по три раза.
    """
    seen: dict[str, None] = {}
    for step in record.steps:
        for violation in step.violations:
            url = violation.proposed_url
            if url and violation.severity == "hard" and not violation.recovered:
                seen.setdefault(url, None)
    return list(seen)


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
    unreached = unreached_urls(record)
    if unreached:
        # Видно и в записи прогона, а не только в промпте: иначе «почему ответ такой»
        # не восстановить постфактум.
        record.metadata["unreached"] = unreached
    # Обе nav-модели выгружаются: лёгкая иначе держит ~5 GB, пока синтез идёт на
    # 16K ctx (дисциплина RAM, doc 14).
    await llm.unload_many(settings.nav_model, settings.nav_light_model)
    early_stop = str(record.metadata.get("early_stop") or "")
    result, stats = await synthesizer.synthesize(
        task=record.config.task,
        snapshots=snapshots,
        intent=record.intent,
        unreached=unreached,
        early_stop=early_stop,
    )
    record.steps[-1].llm_stats = stats
    return note_limits(result, unreached, early_stop=early_stop, pages_read=len(snapshots))


def note_limits(
    result: ExtractionResult,
    unreached: list[str],
    *,
    early_stop: str = "",
    pages_read: int = 0,
) -> ExtractionResult:
    """Дописать в summary, где обход остановили СВОИ правила. Кодом, не просьбой к модели.

    Замер на живом прогоне: запрет в промпте («не называй это отсутствием содержания»)
    сработал на **одном сайте из двух**. Тот же урок, что в synth-speed: формулировка
    слушается через раз, поэтому важное гарантируется кодом (doc 25 § T-2 — enforcement,
    а не доверие LLM).

    Два разных повода, и второй нашёлся уже после первой правки (doc 26 § T-3c-1):

    * **не открыли страницу** — hard-нарушение с целевым URL (глубина, бюджет, robots);
    * **обход оборвался раньше** — правило early stop G-S1. На живом прогоне агент дошёл
      до `blog.rust-lang.org/releases`, то есть до страницы со списком анонсов релизов,
      и остановился именно там (её ссылки не получили сигнальных тегов), после чего
      заявил с `confidence: high`, что подробных статей о релизах на сайте нет.
      Нарушений при этом ноль, поэтому первая версия приписки не срабатывала.
    """
    parts: list[str] = []
    if unreached:
        listed = ", ".join(unreached[:5])
        more = f" (+{len(unreached) - 5})" if len(unreached) > 5 else ""
        parts.append(f"pages not opened: {listed}{more}")
    if early_stop:
        parts.append(f"crawl ended early after {pages_read} page(s) by own rule ({early_stop})")
    if not parts:
        return result
    note = (
        "Reading was cut short by the agent's own limits, not by the site lacking content — "
        + "; ".join(parts)
        + "."
    )
    summary = f"{result.summary.rstrip()} {note}".strip() if result.summary else note
    return result.model_copy(update={"summary": summary})
