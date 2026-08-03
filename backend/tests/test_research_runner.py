"""ResearchRunner (doc 24): sequential D-7, partial failure, M-H2/M-H4, cancel, reply."""

from __future__ import annotations

import asyncio
import uuid

from app.config import Settings
from app.research.compare_synthesizer import CompareSynthesizer
from app.research.runner import ResearchRunner
from app.schemas.extraction import ExtractionResult, Fact
from app.schemas.research import SessionConfig, SessionRecord
from app.storage.session_store import SqliteSessionStore
from app.storage.sqlite_store import SqliteRunStore
from tests.conftest import REPO_ROOT, FakeOllama

COMPARE_OK = {
    "narrative": "a.com wins overall",
    "winner": {"url": "https://a.com", "label": "a.com", "reason": "richer"},
    "rankings": [
        {"url": "https://a.com", "score": 90, "summary": "full"},
        {"url": "https://b.com", "score": 60, "summary": "ok"},
    ],
    "dimensions": [{"name": "depth", "scores": {"a.com": 9, "b.com": 6}}],
}


class ScriptedOrchestrator:
    """Исход per-URL: 'completed' | 'blocked' | 'crash'. Пишет в store, как настоящий."""

    def __init__(self, store, behavior: dict[str, str], visit_log: list[str]):
        self._store = store
        self._behavior = behavior
        self._log = visit_log

    async def run(self, record, cancel_event=None):
        url = record.config.start_url
        self._log.append(url)
        outcome = self._behavior.get(url, "completed")
        if outcome == "crash":
            raise RuntimeError("browser exploded")
        if cancel_event is not None and cancel_event.is_set():
            record.status = "canceled"
        elif outcome == "blocked":
            record.status = "blocked"
            record.metadata["blocked_by"] = "captcha"
        else:
            record.status = "completed"
            record.result = ExtractionResult(
                status="completed",
                start_url=url,
                run_id=record.id,
                summary=f"summary of {url}",
                facts=[Fact(key="k", value=f"v-{url}")],
            )
            record.pages_visited = 2
        self._store.save(record)
        return record


def make_runner(tmp_path, *, behavior=None, compare_replies=None, **settings_kw):
    settings = Settings(
        data_dir=REPO_ROOT / "data",
        runs_dir_override=tmp_path / "runs",
        site_cooldown_s=0.0,
        site_cooldown_hot_s=0.0,
        **settings_kw,
    )
    run_store = SqliteRunStore(settings.runs_dir)
    session_store = SqliteSessionStore(settings.runs_dir)
    visit_log: list[str] = []
    llm = FakeOllama(compare_replies if compare_replies is not None else [COMPARE_OK])
    runner = ResearchRunner(
        settings=settings,
        run_store=run_store,
        session_store=session_store,
        orchestrator_factory=lambda: ScriptedOrchestrator(run_store, behavior or {}, visit_log),
        compare=CompareSynthesizer(llm, settings),  # type: ignore[arg-type]
    )
    return runner, run_store, session_store, visit_log, llm


def new_session(**cfg) -> SessionRecord:
    return SessionRecord(
        id=uuid.uuid4().hex[:12], config=SessionConfig(**cfg), created_at="2026-07-18T20:00:00"
    )


async def test_uc1_happy_path_sequential_compare_report(tmp_path):
    runner, run_store, session_store, visits, llm = make_runner(tmp_path)
    session = new_session()
    session_store.save(session)
    msg = "Опиши дизайн и отличия: https://a.com https://b.com"
    session = await runner.run_message(session, msg)

    assert session.status == "completed"
    assert session.research_intent == "comparative_design"
    assert visits == ["https://a.com", "https://b.com"]  # sequential, порядок сохранён
    assert len(session.run_ids) == 2
    assert all(run_store.get(rid).session_id == session.id for rid in session.run_ids)
    comparison = session.comparison_result
    assert comparison and comparison.winner.label == "a.com"
    assert comparison.rubric == "design_diff"
    assert comparison.rankings[0].run_id == session.run_ids[0]
    report = session_store.artifacts_dir(session.id) / "comparison_report.md"
    text = report.read_text(encoding="utf-8")
    assert "# Comparison Report" in text and "a.com" in text and "| depth |" in text
    roles = [m.role for m in session.messages]
    assert roles[0] == "user" and roles.count("tool") == 2  # M-S1 прогресс
    assert roles[-1] == "assistant"
    # Формулировки ответа — пользовательский текст (doc 17 § Wording), поэтому
    # тест держит их дословно: смена слов должна быть осознанной, не случайной.
    assert "Best of the bunch: a.com" in session.messages[-1].content
    # состояние в store идентично
    assert session_store.get(session.id).status == "completed"


async def test_url_count_over_cap_warns_and_truncates(tmp_path):
    runner, _, session_store, visits, _ = make_runner(tmp_path)
    session = new_session()  # max_sites default 10
    session_store.save(session)
    urls = " ".join(f"https://s{i}.com" for i in range(12))
    session = await runner.run_message(session, f"сравни дизайн: {urls}")
    assert len(visits) == 10  # M-H2: обойдены только первые 10, а не молча все 12
    assert any("I can take 10 at a time" in m.content for m in session.messages if m.role == "tool")


async def test_partial_failure_excluded_and_partial_status(tmp_path):
    behavior = {"https://c.com": "blocked"}
    reply = dict(COMPARE_OK)
    runner, _, session_store, visits, _ = make_runner(tmp_path, behavior=behavior, compare_replies=[reply])
    session = new_session()
    session_store.save(session)
    session = await runner.run_message(session, "дизайн отличия https://a.com https://b.com https://c.com")
    assert session.status == "completed"
    comparison = session.comparison_result
    assert comparison.status == "partial"  # excluded есть
    assert [e.start_url for e in comparison.excluded] == ["https://c.com"]
    assert "captcha" in comparison.excluded[0].reason
    assert "Left out: c.com" in session.messages[-1].content


async def test_single_survivor_answers_without_compare(tmp_path):
    behavior = {"https://b.com": "crash"}
    runner, _, session_store, _, llm = make_runner(tmp_path, behavior=behavior, compare_replies=[])
    session = new_session()
    session_store.save(session)
    session = await runner.run_message(session, "дизайн https://a.com https://b.com")
    assert session.status == "completed"  # M-H4: single-site ответ
    assert session.comparison_result is None
    assert llm.calls == []  # compare не вызывался
    reply = session.messages[-1].content
    # Сайт в ответе называется хостом, а не полным URL (doc 17 § Wording)
    assert "summary of https://a.com" in reply and "b.com" in reply


async def test_all_failed_session_failed(tmp_path):
    behavior = {"https://a.com": "crash", "https://b.com": "blocked"}
    runner, _, session_store, _, _ = make_runner(tmp_path, behavior=behavior)
    session = new_session()
    session_store.save(session)
    session = await runner.run_message(session, "дизайн https://a.com https://b.com")
    assert session.status == "failed"
    assert "captcha" in session.messages[-1].content or "browser" in session.messages[-1].content


async def test_no_urls_fails_and_max_sites_cap(tmp_path):
    runner, _, session_store, visits, _ = make_runner(tmp_path)
    session = new_session()
    session_store.save(session)
    session = await runner.run_message(session, "просто текст без ссылок")
    assert session.status == "failed"

    runner2, _, store2, visits2, _ = make_runner(tmp_path / "x")
    session2 = new_session(max_sites=2)  # M-H2
    store2.save(session2)
    await runner2.run_message(session2, "дизайн https://a.com https://b.com https://c.com https://d.com")
    assert visits2 == ["https://a.com", "https://b.com"]


async def test_cancel_between_sites(tmp_path):
    runner, _, session_store, visits, llm = make_runner(tmp_path, compare_replies=[])
    session = new_session()
    session_store.save(session)
    event = asyncio.Event()

    class CancelAfterFirst(ScriptedOrchestrator):
        async def run(self, record, cancel_event=None):
            result = await super().run(record, cancel_event)
            event.set()  # отмена прилетает во время первого crawl
            return result

    runner._factory = lambda: CancelAfterFirst(runner._runs, {}, visits)
    session = await runner.run_message(
        session, "дизайн https://a.com https://b.com https://c.com", cancel_event=event
    )
    assert visits == ["https://a.com"]  # очередь очищена (doc 15 cancel semantics)
    assert session.status == "completed"  # один выживший → single-site ответ
    assert llm.calls == []


# --- настройки обхода доходят до прогонов сессии (doc 26 § T-3a-2) ---


async def test_session_run_takes_max_depth_from_settings(tmp_path):
    """`max_depth` брался из дефолта RunConfig, а не из настроек.

    Нашлось при попытке замерить глубину на реальных сайтах: оба плеча A/B
    (`LWA_MAX_DEPTH=3` против дефолта) дали побитово одинаковую структуру обхода —
    потому что research-путь настройку игнорировал, и замер не измерял ничего.
    """
    runner, run_store, session_store, _visits, _llm = make_runner(tmp_path, max_depth=4)
    session = new_session()
    session_store.save(session)

    session = await runner.run_message(session, "Сравни: https://a.com https://b.com")

    depths = [run_store.get(rid).config.max_depth for rid in session.run_ids]
    assert depths == [4, 4], "настройка обхода должна доходить до каждого run'а сессии"


async def test_plan_argument_still_wins_over_the_setting(tmp_path):
    """Контроль рядом: у `max_pages` бюджет задаёт ПЛАН (intent-таблица meta_agent), и
    аргумент плана старше настройки — правка глубины эту иерархию не должна ломать.

    Именно поэтому глубина брала дефолт схемы: плана для неё нет, а к настройке
    обращения не было — значение просто некому было подставить.
    """
    runner, run_store, session_store, _visits, _llm = make_runner(tmp_path, max_pages=7)
    session = new_session()
    session_store.save(session)

    session = await runner.run_message(session, "Сравни: https://a.com https://b.com")

    pages = [run_store.get(rid).config.max_pages for rid in session.run_ids]
    assert pages == [10, 10], "multi_site_research задаёт 10 страниц планом"
