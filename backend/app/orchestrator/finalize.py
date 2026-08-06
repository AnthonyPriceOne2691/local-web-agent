"""Финализация прогона: результат из записи + markdown-отчёт.

Вынесено из `loop.py` (≤500 LOC, doc 18) — пятый вынос после attended /
interaction / capture / discovery / decide. Тема модуля: **чем прогон
заканчивается**, а не как он шёл.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from app.extraction.synthesis_validator import SynthesisValidator
from app.reporting.markdown import build_report
from app.reporting.phrasing import Phrases
from app.schemas.extraction import ExtractionResult
from app.schemas.run import RunRecord
from app.schemas.snapshot import PageSnapshot
from app.storage.run_store import RunStore

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def fail_run(
    record: RunRecord,
    exc: BaseException,
    *,
    store: RunStore,
    snapshots: list[PageSnapshot] | None = None,
    say: Phrases | None = None,
) -> RunRecord:
    """Прогон упал: записать причину так, чтобы её можно было объяснить человеку.

    Тема та же, что у `finalize_run` — чем прогон закончился, поэтому живёт здесь (и
    `loop.py` держится в пределах 500 LOC, doc 18).

    Кроме сообщения пишется **стадия падения**: без неё `httpx.ReadTimeout` от локальной
    модели неотличим от молчания сайта, а прогон при этом мог прочитать страницы. Живой
    прогон T-3h: 4 страницы прочитаны, включая целевую статью, а сайт был подан человеку
    как «не удалось прочитать — сайт не ответил» (doc 24 § Причина исключения).

    **Прочитанное не выбрасывается.** В том же прогоне вместе с сайтом пропали и 4
    страницы, и найденная статья: результата не было вовсе, поэтому в отчёте не осталось
    следа. Статус прогона остаётся `failed` — сайт без фактов не должен попасть в
    сравнение и получить оценку, — но страницы теперь видны в записи.
    """
    record.status = "failed"
    # str(httpx.ReadTimeout) пуст — без имени типа excluded[] нечитаем (M-H4)
    record.error_message = (str(exc) or type(exc).__name__)[:500]
    # `CrawlStep.state` — строка (StrEnum пишется значением), поэтому без `.value`.
    record.metadata["failed_stage"] = record.steps[-1].state if record.steps else "prepare"
    if snapshots and say is not None:
        record.result = _pages_read_result(record, snapshots, say)
    record.finished_at = _now()
    store.save(record)
    return record


def _pages_read_result(record: RunRecord, snapshots: list[PageSnapshot], say: Phrases) -> ExtractionResult:
    """Минимальный результат из прочитанного: сколько страниц и какие именно.

    Фактов здесь нет и быть не может — их извлекает синтез, который и упал. Текст идёт на
    языке запроса, как и весь ответ (doc 17 § Язык ответа).
    """
    urls = [s.url for s in snapshots]
    listed = ", ".join(urls[:5]) + (f" (+{len(urls) - 5})" if len(urls) > 5 else "")
    return ExtractionResult(
        status="partial",
        run_id=record.id,
        task=record.config.task,
        start_url=record.config.start_url,
        pages_visited=len(snapshots),
        summary=say.say("pages_read_no_answer", pages=len(snapshots), items=listed),
    )


def finalize_run(
    record: RunRecord,
    result: ExtractionResult,
    snapshots: list[PageSnapshot],
    *,
    visited: set[str],
    violations_total: int,
    started_perf: float,
    validator: SynthesisValidator,
    store: RunStore,
) -> RunRecord:
    """Заполнить результат из записи, провалидировать, сохранить и написать отчёт.

    Поля результата (`run_id`, `task`, `start_url`, …) проставляет код, а не LLM:
    синтезатор про них не знает и знать не должен.
    """
    cfg = record.config
    result.run_id = record.id
    result.task = cfg.task
    result.start_url = cfg.start_url
    # Страницы, на которых стоит ответ, а не все открытые: 404-страница расходует бюджет
    # (её мы правда запросили), но содержанием не является и в ответ не входит — иначе
    # «прочитано 2 стр.» там, где прочитана одна (doc 26 § Проверка эталона).
    result.pages_visited = len(snapshots) or len(visited)
    result.duration_seconds = round(time.perf_counter() - started_perf, 1)
    result.generated_at = _now()
    if record.metadata.get("blocked_by"):
        result.status = "blocked"

    record.result = validator.validate(result, snapshots)  # S-H2/H3/H6, S-G1/G2
    record.status = record.result.status
    record.metadata["violations_total"] = violations_total
    record.finished_at = _now()
    store.save(record)
    write_report(record, snapshots, store)
    return record


def write_report(record: RunRecord, snapshots: list[PageSnapshot], store: RunStore) -> None:
    """Markdown-отчёт (doc 05). Сбой записи run не валит: результат уже в БД —
    но и молчать нельзя, иначе пропавший report.md читается как «не предусмотрен»."""
    try:
        report_path = store.artifacts_dir(record.id) / "report.md"
        report_path.write_text(build_report(record, snapshots), encoding="utf-8")
    except Exception as exc:
        logger.warning("report.md not written for run %s (%s: %s)", record.id, type(exc).__name__, exc)
