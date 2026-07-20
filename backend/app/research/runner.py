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
import time
import uuid
from datetime import UTC, datetime

from app.config import Settings
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
    SessionMessage,
    SessionRecord,
)
from app.schemas.run import RunConfig, RunRecord
from app.storage.run_store import RunStore
from app.storage.session_store import SessionStore

COMPARABLE_STATUSES = ("completed", "partial", "not_found")  # есть result → участвует
HOT_QUEUE_SITES = 4  # N ≥ 4 → длинный cooldown (thermal, doc 24)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ResearchRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        run_store: RunStore,
        session_store: SessionStore,
        orchestrator_factory,
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
        self, session: SessionRecord, message: str,
        cancel_event: asyncio.Event | None = None,
        resume_event: asyncio.Event | None = None,  # attended (Phase 5)
    ) -> SessionRecord:
        self._resume_event = resume_event
        started = time.monotonic()
        session.messages.append(SessionMessage(role="user", content=message, created_at=_now()))
        session.title = session.title or message[:80]
        found = parse_urls(message, max_sites=None)  # все distinct; M-H2 cap ниже — с предупреждением
        cap = session.config.max_sites
        urls = found[:cap]
        if len(found) > cap:  # не глотаем лишние URL молча (честность перед пользователем)
            self._note(session, f"В сообщении {len(found)} URL — беру первые {cap} "
                                f"(лимит max_sites={cap}); отброшено {len(found) - cap}")
        if not urls:
            if self._planner is not None:  # Phase 4: свободный диалог → LLM-план
                return await self._run_llm_plan(session, message, cancel_event, started)
            return self._finish(session, "failed", "no URLs found in message")
        intent = classify_research_intent(message, len(urls))
        session.research_intent = intent
        task = strip_urls(message) or message
        plan = build_plan(intent, urls, task)
        if session.config.rubric_override:
            for call in plan:
                if call.name == "compare_results":
                    call.args["rubric"] = session.config.rubric_override
        session.status = "running_tools"
        self._sessions.save(session)

        crawled: list[RunRecord] = []
        for i, call in enumerate(plan):
            if actions.get(call.name) is None:  # M-H1/A-H1
                return self._finish(session, "failed", f"unknown tool '{call.name}'")
            if call.name == "crawl_site":
                if self._session_expired(started):
                    self._note(session, "session time budget exhausted — comparing partial set")
                    break
                if cancel_event is not None and cancel_event.is_set():
                    break
                self._note(session, f"crawl_site {call.args['url']} "
                                    f"({len(crawled) + 1}/{len(urls)})")  # M-S1
                record = await self._crawl_site(session, call, cancel_event)
                crawled.append(record)
                session.run_ids.append(record.id)
                self._sessions.save(session)
                if i + 1 < len(urls):
                    await asyncio.sleep(self._cooldown_s(len(urls)))
        return await self._compare_stage(session, crawled, task, plan, cancel_event)

    # ------------------------------------------------------- llm plan path
    async def _run_llm_plan(
        self, session: SessionRecord, message: str,
        cancel_event: asyncio.Event | None, started: float,
    ) -> SessionRecord:
        """План от LLM-планнера (M-* уже enforced в нём); пустой план → reply."""
        decision = await self._planner.plan(session, message, run_store=self._runs)
        if not decision.plan:
            return self._finish(session, "completed", decision.reply)
        session.status = "running_tools"
        self._sessions.save(session)

        n_crawls = sum(1 for c in decision.plan if c.name == "crawl_site")
        crawled: list[RunRecord] = []
        reply_blocks: list[str] = []
        compare_call: ToolCall | None = None
        for call in decision.plan:
            if cancel_event is not None and cancel_event.is_set():
                return self._finish(session, "failed", "canceled by user")
            spec = actions.get(call.name)
            if spec is None:  # A-H1: планнер такое уже отбросил — двойная защита
                continue
            if call.name == "crawl_site":
                if self._session_expired(started):
                    self._note(session, "session time budget exhausted")
                    break
                self._note(session, f"crawl_site {call.args['url']}")  # M-S1
                record = await self._crawl_site(session, call, cancel_event)
                crawled.append(record)
                session.run_ids.append(record.id)
                self._sessions.save(session)
                if len(crawled) < n_crawls:
                    await asyncio.sleep(self._cooldown_s(n_crawls))
            elif call.name == "compare_results":
                compare_call = call  # enforced: максимум один, последним
            elif spec.tier >= 2:  # A-H2/A-H3: без подтверждения не исполняем
                self._note(session, f"{call.name}: Tier {spec.tier} требует "
                                    f"подтверждения — пропущено")
            elif spec.execute is not None:  # reply-block действия — через реестр
                self._note(session, spec.note(call) if spec.note else call.name)  # M-S1
                reply_blocks.append(spec.execute(call, self._action_ctx(session)))

        if compare_call is not None:
            records = self._records_for_compare(session, compare_call, crawled)
            task = compare_call.args.get("comparison_task") or strip_urls(message) or message
            return await self._compare_stage(session, records, task, [compare_call],
                                             cancel_event)
        reply = "\n\n".join(b for b in (decision.reply.strip(), *reply_blocks) if b) or "done"
        return self._finish(session, "completed", reply)

    def _records_for_compare(
        self, session: SessionRecord, call: ToolCall, crawled: list[RunRecord],
    ) -> list[RunRecord]:
        """Свежие crawls + прошлые runs по run_ids (пусто → все runs сессии)."""
        ids = call.args.get("run_ids") or [r for r in session.run_ids]
        fresh = {r.id for r in crawled}
        stored = [self._runs.get(i) for i in ids if i not in fresh]
        return crawled + [r for r in stored if r is not None]

    def _action_ctx(self, session: SessionRecord) -> actions.ActionContext:
        """Контекст исполнения reply-block действий (registry, doc 25)."""
        return actions.ActionContext(session=session, run_store=self._runs,
                                     settings=self._s, session_store=self._sessions)

    # ---------------------------------------------------------- crawl tool
    async def _crawl_site(
        self, session: SessionRecord, call: ToolCall,
        cancel_event: asyncio.Event | None,
    ) -> RunRecord:
        args = dict(call.args)
        config = RunConfig(
            start_url=args["url"],
            task=args.get("task") or session.title,
            max_pages=args.get("max_pages", self._s.max_pages),
            capture_screenshots=args.get("capture_screenshots", "auto"),
            vision_enabled=args.get("vision_enabled", "auto"),
            attended=session.config.attended,  # Phase 5 (doc 24)
        )
        record = RunRecord(id=uuid.uuid4().hex[:12], config=config, status="running",
                           session_id=session.id, started_at=_now())
        if args.get("intent"):
            record.intent = args["intent"]  # research-план фиксирует intent (doc 24)
        self._runs.save(record)
        orchestrator = self._factory()
        kwargs: dict = {"cancel_event": cancel_event}
        if config.attended and self._resume_event is not None:
            from app.orchestrator.attended import EventAttendedGate

            kwargs["attended_gate"] = EventAttendedGate(
                self._resume_event, self._runs, timeout_s=self._s.attended_wait_timeout_s)
        try:
            return await orchestrator.run(record, **kwargs)
        except Exception as exc:  # noqa: BLE001 — один сайт не валит сессию (M-H4 edge)
            record.status = "failed"
            record.error_message = (str(exc) or type(exc).__name__)[:500]
            self._runs.save(record)
            return record

    # -------------------------------------------------------- compare tool
    async def _compare_stage(
        self, session: SessionRecord, crawled: list[RunRecord], task: str,
        plan: list[ToolCall], cancel_event: asyncio.Event | None,
    ) -> SessionRecord:
        survivors = [r for r in crawled if r.status in COMPARABLE_STATUSES and r.result]
        survivor_urls = {r.config.start_url for r in survivors}
        excluded = [
            ExcludedSite(
                start_url=r.config.start_url,
                reason=f"{r.status}: "
                       f"{r.metadata.get('blocked_by') or r.error_message or 'no result'}",
            )
            # сайт, перекраленный успешно (re-crawl через LLM-план), не excluded
            for r in crawled if r not in survivors and r.config.start_url not in survivor_urls
        ]
        compare_call = next((c for c in plan if c.name == "compare_results"), None)

        if not survivors:  # 0 выживших (doc 24 § Partial failure)
            return self._finish(session, "failed",
                                "all sites failed: " + "; ".join(e.reason for e in excluded))
        if compare_call is None or len(survivors) < 2:  # M-H4: single-site ответ
            reply = survivors[0].result.summary or "done"
            if excluded:
                reply += "\n\nExcluded: " + "; ".join(f"{e.start_url} ({e.reason})" for e in excluded)
            return self._finish(session, "completed", reply)

        session.status = "comparing"
        self._sessions.save(session)
        if cancel_event is not None and cancel_event.is_set():
            return self._finish(session, "failed", "canceled before compare")
        comparison, _ = await self._compare.compare(
            task=task, rubric_id=compare_call.args.get("rubric", "generic_merge"),
            inputs=[(r.id, r.result) for r in survivors],
        )
        comparison.session_id = session.id
        comparison.excluded = excluded
        comparison.generated_at = _now()
        if excluded and comparison.status == "completed":
            comparison.status = "partial"
        session.comparison_result = comparison

        report = build_comparison_report(session, comparison, survivors)
        report_path = self._sessions.artifacts_dir(session.id) / "comparison_report.md"
        report_path.write_text(report, encoding="utf-8")
        return self._finish(session, "completed", self._chat_reply(comparison, report_path.name))

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
    def _chat_reply(comparison: ComparisonResult, report_name: str) -> str:
        lines = []
        if comparison.winner:
            lines.append(f"Winner: {comparison.winner.label} — {comparison.winner.reason}")
        if comparison.rankings:
            lines.append("Rankings: " + " · ".join(
                f"{r.url} ({r.score})" for r in comparison.rankings))
        if comparison.narrative:
            lines.append(comparison.narrative[:600])
        if comparison.excluded:
            lines.append("Excluded: " + "; ".join(
                f"{e.start_url} ({e.reason})" for e in comparison.excluded))
        lines.append(f"Full report: artifacts/{comparison.session_id}/{report_name}")
        return "\n\n".join(lines)
