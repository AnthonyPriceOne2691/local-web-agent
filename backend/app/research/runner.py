"""ResearchRunner — исполнение одного user message (doc 24).

Sequential crawl queue (D-7) → partial failure → compare (M-H4) → chat reply +
comparison_report.md. Контракты M-H1..M-H4 enforced здесь (`Layer 2 ≠ ABC crawl`);
membership и исполнение действий — через Action registry (doc 25, A-H1/A-H2).
Session-level cancel_event пробрасывается в текущий crawl (FR-3.8 семантика).
Phase 4: URLs в сообщении → rules fast-path (без LLM); иначе LLM-планнер
(follow-up диалог, re-compare, доступ к прошлым runs — doc 24 § Planner).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.reporting.phrasing import Phrases
from app.reporting.phrasing import action_name as _action_name
from app.reporting.phrasing import site_name as _site_name
from app.research import actions
from app.research.compare_synthesizer import CompareSynthesizer
from app.research.llm_planner import LlmPlanner
from app.research.meta_agent import (
    ToolCall,
    build_plan,
    classify_research_intent,
    parse_urls,
    strip_urls,
)
from app.research.report import build_comparison_report
from app.schemas.research import (
    ComparisonResult,
    ExcludedSite,
    ResearchIntent,
    SessionMessage,
    SessionRecord,
)
from app.schemas.run import RunConfig, RunRecord
from app.storage.run_store import RunStore
from app.storage.session_store import SessionStore

logger = logging.getLogger(__name__)

COMPARABLE_STATUSES = ("completed", "partial", "not_found")  # есть result → участвует
HOT_QUEUE_SITES = 4  # N ≥ 4 → длинный cooldown (thermal, doc 24)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _nav_error(record: RunRecord) -> str:
    """Причина, по которой страница не открылась, записана шагом OBSERVE (`nav_error: …`),
    а в `error_message` её нет вовсе: прогон закончился штатно, просто без страниц. Живой
    прогон T-3h — двум сайтам из трёх человек получил «не удалось прочитать» без единой
    подробности, хотя причина (`Page.goto: Timeout 30000ms`) лежала в записи."""
    for step in reversed(record.steps):
        note = step.note or ""
        if note.startswith("nav_error:"):
            return note
    return ""


class ResearchRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        run_store: RunStore,
        session_store: SessionStore,
        orchestrator_factory: Callable[[], Any],
        compare: CompareSynthesizer,
        planner: LlmPlanner | None = None,
    ):
        self._s = settings
        self._runs = run_store
        self._sessions = session_store
        self._factory = orchestrator_factory
        self._compare = compare
        self._planner = planner
        self._resume_event: asyncio.Event | None = None

    # ------------------------------------------------------------- message
    async def run_message(
        self,
        session: SessionRecord,
        message: str,
        cancel_event: asyncio.Event | None = None,
        resume_event: asyncio.Event | None = None,  # attended (Phase 5)
    ) -> SessionRecord:
        self._resume_event = resume_event
        started = time.monotonic()
        session.messages.append(SessionMessage(role="user", content=message, created_at=_now()))
        session.title = session.title or message[:80]
        urls = self._urls_within_cap(session, message)
        if not urls:
            if self._planner is not None:  # Phase 4: свободный диалог → LLM-план
                return await self._run_llm_plan(session, message, cancel_event, started)
            return self._finish(session, "failed", "I need at least one web address to work with.")
        intent = classify_research_intent(message, len(urls))
        session.research_intent = intent
        task = strip_urls(message) or message
        plan = self._rules_plan(session, intent, urls, task)
        unknown = next((c.name for c in plan if actions.get(c.name) is None), None)
        if unknown is not None:  # M-H1/A-H1
            return self._finish(session, "failed", f"I don't know how to do “{_action_name(unknown)}”.")

        session.status = "running_tools"
        self._sessions.save(session)
        say = self._phrases(task)
        crawled = await self._crawl_each(session, plan, len(urls), started, cancel_event, say)
        return await self._compare_stage(session, crawled, task, plan, cancel_event)

    def _urls_within_cap(self, session: SessionRecord, message: str) -> list[str]:
        """URL сообщения в пределах cap. Лишние не глотаем молча — говорим о них."""
        found = parse_urls(message, max_sites=None)  # все distinct; M-H2 cap ниже
        cap = session.config.max_sites
        if len(found) > cap:
            self._note(
                session,
                f"You gave {len(found)} links — I can take {cap} at a time, "
                f"so I'll work through the first {cap} and skip the rest.",
            )
        return found[:cap]

    @staticmethod
    def _rules_plan(
        session: SessionRecord, intent: ResearchIntent, urls: list[str], task: str
    ) -> list[ToolCall]:
        plan = build_plan(intent, urls, task)
        if session.config.rubric_override:
            for call in plan:
                if call.name == "compare_results":
                    call.args["rubric"] = session.config.rubric_override
        return plan

    def _phrases(self, task: str) -> Phrases:
        """Словарь фраз на языке запроса (doc 17 § Язык ответа)."""
        return Phrases.load(self._s.data_dir, task)

    async def _crawl_each(
        self,
        session: SessionRecord,
        plan: list[ToolCall],
        total: int,
        started: float,
        cancel_event: asyncio.Event | None,
        say: Phrases,
    ) -> list[RunRecord]:
        """Сайты по очереди (D-7), с cooldown между ними; бюджет и отмена — на границе."""
        crawled: list[RunRecord] = []
        for i, call in enumerate(plan):
            if call.name != "crawl_site":
                continue
            if self._session_expired(started):
                self._note(session, say.say("out_of_time_comparing"))
                break
            if cancel_event is not None and cancel_event.is_set():
                break
            site = _site_name(call.args["url"])
            self._note(
                session, say.say("reading_site", site=site, index=len(crawled) + 1, total=total)
            )  # M-S1
            record = await self._crawl_site(session, call, cancel_event)
            crawled.append(record)
            session.run_ids.append(record.id)
            self._sessions.save(session)
            if i + 1 < total:
                await asyncio.sleep(self._cooldown_s(total))
        return crawled

    # ------------------------------------------------------- llm plan path
    async def _run_llm_plan(
        self,
        session: SessionRecord,
        message: str,
        cancel_event: asyncio.Event | None,
        started: float,
    ) -> SessionRecord:
        """План от LLM-планнера (M-* уже enforced в нём); пустой план → reply."""
        if self._planner is None:  # вызывается только когда планнер сконфигурирован
            return self._finish(session, "failed", "I can only follow links you paste for now.")
        decision = await self._planner.plan(session, message, run_store=self._runs)
        if not decision.plan:
            return self._finish(session, "completed", decision.reply)
        session.status = "running_tools"
        self._sessions.save(session)

        crawled: list[RunRecord] = []
        reply_blocks: list[str] = []
        compare_call: ToolCall | None = None
        n_crawls = sum(1 for c in decision.plan if c.name == "crawl_site")
        for call in decision.plan:
            if cancel_event is not None and cancel_event.is_set():
                return self._finish(session, "failed", "Stopped at your request.")
            spec = actions.get(call.name)
            if spec is None:  # A-H1: планнер такое уже отбросил — двойная защита
                continue
            if call.name == "compare_results":
                compare_call = call  # enforced: максимум один, последним
            elif call.name == "crawl_site":
                if not await self._crawl_one_of(
                    session, call, crawled, n_crawls, started, cancel_event, self._phrases(message)
                ):
                    break  # бюджет сессии исчерпан
            else:
                reply_blocks += self._run_side_action(session, call, spec)

        if compare_call is not None:
            records = self._records_for_compare(session, compare_call, crawled)
            task = compare_call.args.get("comparison_task") or strip_urls(message) or message
            return await self._compare_stage(session, records, task, [compare_call], cancel_event)
        reply = "\n\n".join(b for b in (decision.reply.strip(), *reply_blocks) if b) or self._phrases(
            message
        ).say("done")
        return self._finish(session, "completed", reply)

    async def _crawl_one_of(
        self,
        session: SessionRecord,
        call: ToolCall,
        crawled: list[RunRecord],
        n_crawls: int,
        started: float,
        cancel_event: asyncio.Event | None,
        say: Phrases,
    ) -> bool:
        """Один сайт из плана планнера. `False` = бюджет сессии исчерпан, дальше не идём."""
        if self._session_expired(started):
            self._note(session, say.say("out_of_time"))
            return False
        self._note(session, say.say("reading", site=_site_name(call.args["url"])))  # M-S1
        record = await self._crawl_site(session, call, cancel_event)
        crawled.append(record)
        session.run_ids.append(record.id)
        self._sessions.save(session)
        if len(crawled) < n_crawls:
            await asyncio.sleep(self._cooldown_s(n_crawls))
        return True

    def _run_side_action(
        self,
        session: SessionRecord,
        call: ToolCall,
        spec: actions.ActionSpec,
    ) -> list[str]:
        """Действия, не связанные с обходом: экспорт, чтение результата и т.п.

        Tier ≥ 2 без подтверждения человека не исполняется (A-H2/A-H3) — вместо
        исполнения агент честно говорит, что пропустил и почему.
        """
        if spec.tier >= 2:
            self._note(
                session,
                f"Skipped “{_action_name(call.name)}” — it needs your go-ahead first.",
            )
            return []
        if spec.execute is None:
            return []
        self._note(session, spec.note(call) if spec.note else call.name)  # M-S1
        return [spec.execute(call, self._action_ctx(session))]

    def _records_for_compare(
        self,
        session: SessionRecord,
        call: ToolCall,
        crawled: list[RunRecord],
    ) -> list[RunRecord]:
        """Свежие crawls + прошлые runs по run_ids (пусто → все runs сессии)."""
        ids = call.args.get("run_ids") or list(session.run_ids)
        fresh = {r.id for r in crawled}
        stored = [self._runs.get(i) for i in ids if i not in fresh]
        return crawled + [r for r in stored if r is not None]

    def _action_ctx(self, session: SessionRecord) -> actions.ActionContext:
        """Контекст исполнения reply-block действий (registry, doc 25)."""
        return actions.ActionContext(
            session=session, run_store=self._runs, settings=self._s, session_store=self._sessions
        )

    # ---------------------------------------------------------- crawl tool
    async def _crawl_site(
        self,
        session: SessionRecord,
        call: ToolCall,
        cancel_event: asyncio.Event | None,
    ) -> RunRecord:
        args = dict(call.args)
        config = RunConfig(
            start_url=args["url"],
            task=args.get("task") or session.title,
            max_pages=args.get("max_pages", self._s.max_pages),
            # Глубина: явное указание сессии > настройка процесса > дефолт. Порядок такой
            # потому, что дважды обжёгся на «тихой» глубине: сперва `LWA_MAX_DEPTH` не
            # действовал на research-сессии вовсе (doc 26 § T-3a-2), потом два прогона
            # одной команды разошлись по глубине (2 против 3) и сорвали A/B — глубина
            # приходила из процесса API, и ни команда, ни ответ этого не говорили
            # (doc 26 § T-3f-1).
            max_depth=args.get("max_depth", session.config.max_depth or self._s.max_depth),
            capture_screenshots=args.get("capture_screenshots", "auto"),
            vision_enabled=args.get("vision_enabled", "auto"),
            attended=session.config.attended,  # Phase 5 (doc 24)
        )
        record = RunRecord(
            id=uuid.uuid4().hex[:12],
            config=config,
            status="running",
            session_id=session.id,
            started_at=_now(),
        )
        if args.get("intent"):
            record.intent = args["intent"]  # research-план фиксирует intent (doc 24)
        self._runs.save(record)
        orchestrator = self._factory()
        kwargs: dict[str, Any] = {"cancel_event": cancel_event}
        if config.attended and self._resume_event is not None:
            from app.orchestrator.attended import EventAttendedGate

            kwargs["attended_gate"] = EventAttendedGate(
                self._resume_event, self._runs, timeout_s=self._s.attended_wait_timeout_s
            )
        try:
            done: RunRecord = await orchestrator.run(record, **kwargs)
            return done
        except Exception as exc:
            # Один упавший сайт не валит сессию (M-H4): в excluded[] уедет короткая
            # причина, а стек виден только здесь.
            logger.exception("crawl_site %s failed inside session %s", config.start_url, session.id)
            record.status = "failed"
            record.error_message = (str(exc) or type(exc).__name__)[:500]
            self._runs.save(record)
            return record

    # -------------------------------------------------------- compare tool
    async def _compare_stage(
        self,
        session: SessionRecord,
        crawled: list[RunRecord],
        task: str,
        plan: list[ToolCall],
        cancel_event: asyncio.Event | None,
    ) -> SessionRecord:
        say = self._phrases(task)
        survivors = [r for r in crawled if r.status in COMPARABLE_STATUSES and r.result]
        survivor_urls = {r.config.start_url for r in survivors}
        excluded = [
            ExcludedSite(
                start_url=r.config.start_url,
                reason=say.exclusion_reason(
                    r.status,
                    r.metadata.get("blocked_by"),
                    r.error_message or _nav_error(r),
                    stage=str(r.metadata.get("failed_stage") or ""),
                    pages_read=r.pages_visited,
                ),
            )
            # сайт, перекраленный успешно (re-crawl через LLM-план), не excluded
            for r in crawled
            if r not in survivors and r.config.start_url not in survivor_urls
        ]
        compare_call = next((c for c in plan if c.name == "compare_results"), None)

        if not survivors:  # 0 выживших (doc 24 § Partial failure)
            return self._finish(
                session,
                "failed",
                say.say("none_worked", items="; ".join(e.reason for e in excluded)),
            )
        if compare_call is None or len(survivors) < 2:  # M-H4: single-site ответ
            first_result = survivors[0].result
            reply = (first_result.summary if first_result else "") or say.say("done")
            if excluded:
                items = "; ".join(f"{_site_name(e.start_url)} — {e.reason}" for e in excluded)
                reply += "\n\n" + say.say("left_out", items=items)
            return self._finish(session, "completed", reply)

        session.status = "comparing"
        self._sessions.save(session)
        if cancel_event is not None and cancel_event.is_set():
            return self._finish(session, "failed", say.say("stopped_before_compare"))
        comparison, compare_stats = await self._compare.compare(
            task=task,
            rubric_id=compare_call.args.get("rubric", "generic_merge"),
            inputs=[(r.id, r.result) for r in survivors if r.result is not None],
        )
        comparison.llm_stats = compare_stats  # иначе стадия compare неизмерима
        comparison.session_id = session.id
        comparison.excluded = excluded
        comparison.generated_at = _now()
        if excluded and comparison.status == "completed":
            comparison.status = "partial"
        session.comparison_result = comparison

        report = build_comparison_report(session, comparison, survivors)
        report_path = self._sessions.artifacts_dir(session.id) / "comparison_report.md"
        report_path.write_text(report, encoding="utf-8")
        return self._finish(
            session, "completed", self._chat_reply(comparison, report_path.name, say, survivors)
        )

    # ------------------------------------------------------------ helpers
    def _cooldown_s(self, n_sites: int) -> float:
        if n_sites >= HOT_QUEUE_SITES:
            return self._s.site_cooldown_hot_s  # thermal, fanless Air (doc 24)
        return self._s.site_cooldown_s

    def _session_expired(self, started_monotonic: float) -> bool:
        return (time.monotonic() - started_monotonic) > self._s.max_session_duration_min * 60

    def _note(self, session: SessionRecord, text: str) -> None:
        session.messages.append(SessionMessage(role="tool", content=text, created_at=_now()))
        self._sessions.save(session)

    def _finish(self, session: SessionRecord, status: str, reply: str) -> SessionRecord:
        session.status = status  # type: ignore[assignment]
        session.messages.append(SessionMessage(role="assistant", content=reply, created_at=_now()))
        session.finished_at = _now()
        self._sessions.save(session)
        return session

    @staticmethod
    def _incomplete_sites(survivors: list[RunRecord]) -> list[str]:
        """Сайты, где обход обрезали СВОИ лимиты: глубина/бюджет (`unreached`) или
        early stop. Признак тот же, что у приписки в разборе сайта (`note_limits`)."""
        return [
            _site_name(r.config.start_url)
            for r in survivors
            if r.metadata.get("unreached") or r.metadata.get("early_stop")
        ]

    @staticmethod
    def _chat_reply(
        comparison: ComparisonResult, report_name: str, say: Phrases, survivors: list[RunRecord]
    ) -> str:
        """Ответ в чат. Каркас берётся из словаря языка запроса — иначе наши строки
        («How they scored:») стояли бы английскими над русской прозой модели, и именно
        эта смесь была дефектом (doc 17 § Язык ответа).

        Оговорка про неполный обход добавляется **кодом**: живой прогон T-3f показал, что
        она есть в разборе каждого сайта, но в сравнении теряется, и итоговый ответ подаёт
        своё же ограничение как свойство сайта («материалов по теме нет»).
        """
        lines = []
        if comparison.winner:
            lines.append(say.say("winner", label=comparison.winner.label, reason=comparison.winner.reason))
        if comparison.rankings:
            scores = " · ".join(f"{_site_name(r.url)} {r.score}/100" for r in comparison.rankings)
            lines.append(say.say("scored", scores=scores))
        if comparison.narrative:
            lines.append(comparison.narrative[:600])
        incomplete = ResearchRunner._incomplete_sites(survivors)
        if incomplete:
            lines.append(say.say("reading_cut", items=", ".join(incomplete)))
        if comparison.excluded:
            items = "; ".join(f"{_site_name(e.start_url)} — {e.reason}" for e in comparison.excluded)
            lines.append(say.say("left_out", items=items))
        lines.append(say.say("report_saved", name=report_name))
        return "\n\n".join(lines)
