"""Crawl Orchestrator — agent loop (doc 04): детерминированная state machine,
LLM выбирает только среди top-K кандидатов, contract-lite guards до Playwright.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from app.browser.base import BrowserSession
from app.browser.consent import ConsentHandler
from app.config import Settings
from app.contracts.enforcer import ContractEnforcer
from app.extraction.synthesis_validator import SynthesisValidator
from app.llm.model_router import NavRouting
from app.llm.navigator import Navigator
from app.llm.ollama_client import OllamaClient
from app.llm.synthesizer import Synthesizer
from app.navigation.candidate_queue import RELEVANT_TAGS, build_candidates
from app.navigation.intent import classify_intent
from app.navigation.path_hints import PathHints
from app.observer.links import normalize_url, origin_of
from app.orchestrator.attended import AttendedGate, pause_with_window, reobserve_in_place
from app.orchestrator.capture import dismiss_consent, step_capturer
from app.orchestrator.decide import plan_validated
from app.orchestrator.discovery import looks_like_article, probe_slugs, sitemap_urls
from app.orchestrator.finalize import fail_run, finalize_run
from app.orchestrator.interaction import REPEAT_LIMITS, act_on_element, action_signature
from app.orchestrator.observe import navigate_and_observe
from app.orchestrator.robots import RobotsPolicy
from app.orchestrator.run_state import Prepared, RunState, StepOutcome
from app.orchestrator.states import State
from app.orchestrator.synthesize import run_synthesis
from app.orchestrator.vision_batch import run_vision_batch
from app.reporting.phrasing import Phrases
from app.schemas.run import CrawlStep, RunRecord
from app.schemas.snapshot import AgentAction, Candidate, PageSnapshot
from app.storage.run_store import RunStore
from app.vision.analyzer import VisionAnalyzer

logger = logging.getLogger(__name__)

# Drift auto-tighten (doc 13 § Drift detection)
DRIFT_HARD_FOR_LOW_TEMP = 3  # hard violations ≥ 3/run → nav temperature 0.4 → 0.2
DRIFT_IH6_FOR_TOP5 = 2  # fabricated URL ≥ 2 → shrink candidate list to top 5
DRIFT_MIN_RECOVERIES = 2  # recovery success < 50% (при ≥2 попытках) → fallback-only
EARLY_STOP_STALE_PAGES = 3


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _is_canceled(cancel_event: asyncio.Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


class CrawlOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        browser: BrowserSession,
        navigator: Navigator,
        synthesizer: Synthesizer,
        llm_client: OllamaClient,
        store: RunStore,
        hints: PathHints,
        enforcer: ContractEnforcer | None = None,
    ):
        self._s = settings
        self._browser = browser
        self._navigator = navigator
        self._synthesizer = synthesizer
        self._llm = llm_client
        self._store = store
        self._hints = hints
        self._enforcer = enforcer or ContractEnforcer.load(settings.contracts_dir)
        self._synth_validator = SynthesisValidator.load(settings.contracts_dir)
        self._consent = ConsentHandler.load(settings.navigation_dir)
        self._routing = NavRouting.load(settings)  # лёгкая/тяжёлая nav-модель (doc 16)
        self._consent_click_used = False  # 1 попытка click на сайт (D-11)
        # Скриншот шага для стадий, которые не знают про store (интеракция, attended).
        self._capture = step_capturer(browser, store, self._dismiss_consent)
        self._vision = VisionAnalyzer(llm_client, settings)

    # ------------------------------------------------------------------ run
    # ------------------------------------------------------------------ run
    async def run(
        self,
        record: RunRecord,
        cancel_event: asyncio.Event | None = None,
        attended_gate: AttendedGate | None = None,  # Phase 5: пауза на challenge (doc 24)
    ) -> RunRecord:
        """OBSERVE → PLAN → ACT до бюджета или остановки, затем vision и синтез.

        Стадии живут в отдельных методах, состояние — в `RunState`, решение шага —
        в `StepOutcome`. Порядок проверок содержателен: отмена проверяется на каждой
        границе состояний (FR-3.8), а не «где-нибудь в цикле».
        """
        cfg = record.config
        t0 = time.perf_counter()
        record.started_at = record.started_at or _now()
        record.intent = classify_intent(cfg.task, self._hints)
        if not self._config_allows_run(record):  # P-1/P-2 + G-H4/G-H6
            return record

        start = normalize_url(cfg.start_url)
        st = RunState(origin=origin_of(start), next_url=start, hops={start: 0})

        try:
            prep = await self._prepare(record, st)
            await self._crawl_loop(record, st, prep, cancel_event, attended_gate)
            if st.canceled or _is_canceled(cancel_event):  # синтез при отмене пропускаем (doc 15)
                return await self._finish_canceled(record)
            await run_vision_batch(  # doc 23
                record=record,
                snapshots=st.snapshots,
                settings=self._s,
                store=self._store,
                llm=self._llm,
                analyzer=self._vision,
                close_browser=self._safe_close,
                cancel_event=cancel_event,
            )
            result = await run_synthesis(
                record,
                st.snapshots,
                synthesizer=self._synthesizer,
                llm=self._llm,
                store=self._store,
                settings=self._s,
            )
        except Exception as exc:
            logger.exception("crawl run %s crashed at %s", record.id, record.current_url)
            failed = fail_run(
                record,
                exc,
                store=self._store,
                snapshots=st.snapshots,
                say=Phrases.load(self._s.data_dir, record.config.task),
            )
            await self._safe_close()
            return failed

        await self._safe_close()
        return finalize_run(
            record,
            result,
            st.snapshots,
            visited=st.visited,
            violations_total=st.violations_total,
            started_perf=t0,
            validator=self._synth_validator,
            store=self._store,
        )

    # -------------------------------------------------------------- стадии
    def _config_allows_run(self, record: RunRecord) -> bool:
        """Hard-нарушение конфига — отказ до открытия браузера; soft — только заметка."""
        violations = self._enforcer.check_run_config(record.config)
        hard = [v for v in violations if v.severity == "hard"]
        if hard:
            record.status = "failed"
            record.error_message = "; ".join(f"{v.constraint_id}: {v.message}" for v in hard)
            record.finished_at = _now()
            self._store.save(record)
            return False
        if violations:  # soft: rate floor / timeout cap — только лог
            record.metadata["config_notes"] = [v.message for v in violations]
        return True

    async def _prepare(self, record: RunRecord, st: RunState) -> Prepared:
        """robots, темп, пробы, sitemap и открытый браузер — до первого шага."""
        cfg = record.config
        # Греем nav-модель параллельно сетевой подготовке: иначе первое решение
        # агента оплачивает загрузку весов уже при открытом браузере (8.7 s против
        # 3.6 s у последующих — замер живого прогона Tier 3).
        warmup = asyncio.create_task(self._llm.warmup(self._routing.first_step_model(cfg.task)))
        robots = await RobotsPolicy.load(st.origin, respect=cfg.respect_robots)
        rate_ms = max(
            self._enforcer.effective_rate_ms(cfg.rate_limit_ms, cfg.start_url),
            int(robots.crawl_delay_s * 1000),
        )
        alive_probes, legal_probes, probe_links = await probe_slugs(self._hints, record.intent, st.origin)
        sitemap_candidates = await sitemap_urls(record, st.origin, robots.sitemaps(), self._hints)  # P2.5
        profile = (
            self._s.profile_path(st.origin) if (cfg.persist_session or self._s.persist_session) else None
        )
        await warmup  # к открытию браузера модель уже в памяти
        # Окно сразу — только для задач-действий: перезапуск в видимый режим
        # потерял бы заполненную форму (doc 24 § Видимость окна).
        headed = cfg.attended and self._routing.expects_human_action(cfg.task)
        await self._browser.start(headless=not headed, storage_state_path=profile)
        return Prepared(
            robots=robots,
            rate_ms=rate_ms,
            alive_probes=alive_probes,
            legal_probes=legal_probes,
            probe_links=probe_links,
            sitemap_candidates=sitemap_candidates,
        )

    async def _crawl_loop(
        self,
        record: RunRecord,
        st: RunState,
        prep: Prepared,
        cancel_event: asyncio.Event | None,
        gate: AttendedGate | None,
    ) -> None:
        while st.step_index < record.config.max_pages * 2:
            if _is_canceled(cancel_event):  # FR-3.8: граница state (перед OBSERVE)
                st.canceled = True
                return
            st.step_index += 1

            outcome = await self._observe_step(record, st, prep, gate)
            if outcome is StepOutcome.STOP:
                return
            if outcome is StepOutcome.CONTINUE:
                continue

            if _is_canceled(cancel_event):  # FR-3.8: граница state (перед PLAN)
                st.canceled = True
                return
            if st.current is None:  # инвариант: к PLAN приходим только со снапшотом
                return

            action, outcome = await self._plan_step(record, st, prep)
            if action is None or outcome is StepOutcome.STOP:
                return
            if await self._act_step(record, st, action, prep, gate) is StepOutcome.STOP:
                return

    async def _observe_step(
        self,
        record: RunRecord,
        st: RunState,
        prep: Prepared,
        gate: AttendedGate | None,
    ) -> StepOutcome:
        """NAVIGATE + OBSERVE. `next_url is None` = страница уже открыта, сразу PLAN."""
        if st.next_url is None:
            return StepOutcome.PROCEED
        nav = await self._navigate_observe(
            record,
            st.next_url,
            st.origin,
            prep.robots,
            first=not st.snapshots,
            step_index=st.step_index,
        )
        st.next_url = None
        if nav is None:  # skipped/failed — PLAN с прежней страницы
            return StepOutcome.STOP if st.current is None else StepOutcome.CONTINUE

        snapshot, st.origin = nav
        if record.intent == "content_search" and looks_like_article(snapshot, record.config.task):
            snapshot.priority = True  # article candidate (doc 24) → 12K excerpt
        st.remember(snapshot)
        record.pages_visited = len(st.visited)
        record.current_url = snapshot.url
        if snapshot.status in ("captcha", "login_wall"):  # blocker (doc 04)
            return await self._handle_blocker(record, st, gate)
        self._store.save(record)
        return StepOutcome.PROCEED

    async def _handle_blocker(
        self, record: RunRecord, st: RunState, gate: AttendedGate | None
    ) -> StepOutcome:
        """attended: и captcha (человек проходит проверку), и login_wall (человек
        логинится в видимом браузере — Tier 2, doc 25; паролей не храним)."""
        assert st.current is not None  # вызывается сразу после успешного OBSERVE
        if gate is not None and await pause_with_window(
            self._browser,
            gate.try_clear(record, st.current, st.snapshots, st.visited),
            hide_after=True,  # cookie получен — дальше окно не нужно
        ):
            st.adopt(
                await reobserve_in_place(  # без goto → CF не re-challenge
                    self._browser,
                    record,
                    origin=st.origin,
                    step_index=st.step_index,
                    snapshots=st.snapshots,
                    visited=st.visited,
                    capture=self._capture,
                )
            )
            return StepOutcome.CONTINUE  # next_url is None → сразу PLAN c этой страницей
        record.metadata["blocked_by"] = st.current.status
        return StepOutcome.STOP

    async def _plan_step(
        self, record: RunRecord, st: RunState, prep: Prepared
    ) -> tuple[AgentAction | None, StepOutcome]:
        """Кандидаты → ранняя остановка → решение навигатора с валидацией."""
        assert st.current is not None
        cfg = record.config
        candidates = build_candidates(
            snapshot=st.current,
            homepage=st.homepage,
            intent=record.intent,
            task=cfg.task,
            hints=self._hints,
            origin=st.origin,
            visited=st.visited,
            alive_probes=prep.alive_probes,
            legal_probes=prep.legal_probes,
            sitemap_urls=prep.sitemap_candidates,
            probe_links=prep.probe_links,
            top_k=self._s.top_k_candidates,
        )
        if st.just_visited and self._early_stop(record, st, candidates):
            return None, StepOutcome.STOP

        action, step_violations, llm_stats = await plan_validated(
            record,
            st.current,
            candidates,
            st.visited,
            st.hops,
            st.origin,
            cfg.max_pages - len(st.visited),
            prep.robots,
            navigator=self._navigator,
            enforcer=self._enforcer,
            routing=self._routing,
        )
        st.violations_total += len(step_violations)
        record.steps.append(
            CrawlStep(
                index=st.step_index,
                state=State.ACT,
                url=st.current.url,
                action=action.action,
                target_url=action.url,
                reasoning=action.reasoning[:300],
                violations=step_violations,
                llm_stats=llm_stats,
            )
        )
        self._store.save(record)
        return action, StepOutcome.PROCEED

    @staticmethod
    def _early_stop(record: RunRecord, st: RunState, candidates: list[Candidate]) -> bool:
        """G-S1: 3 страницы подряд без новых релевантных ссылок → SYNTHESIZE."""
        st.just_visited = False
        fresh = {
            normalize_url(c.href) for c in candidates if any(tag in c.reason for tag in RELEVANT_TAGS)
        } - st.seen_relevant
        if fresh:
            st.stale_pages = 0
            st.seen_relevant |= fresh
            return False
        st.stale_pages += 1
        if st.stale_pages >= EARLY_STOP_STALE_PAGES:
            record.metadata["early_stop"] = "G-S1: no new relevant links on 3 pages"
            return True
        return False

    async def _act_step(
        self,
        record: RunRecord,
        st: RunState,
        action: AgentAction,
        prep: Prepared,
        gate: AttendedGate | None,
    ) -> StepOutcome:
        assert st.current is not None
        cfg = record.config
        if action.action == "navigate" and action.url:
            target = normalize_url(action.url)
            st.hops[target] = min(st.hops.get(target, 99), st.hops.get(st.current.url, 0) + 1)
            st.next_url = target
            st.extract_streak = 0
            await self._browser.wait(prep.rate_ms)
            return StepOutcome.CONTINUE
        if action.action == "extract_now":
            st.current.priority = True
            st.extract_streak += 1
            if st.extract_streak >= 2 or cfg.max_pages - len(st.visited) <= 0:  # guard, policy #11
                return StepOutcome.STOP
            return StepOutcome.CONTINUE
        if action.action in ("fill_form", "click", "fill"):
            if self._repeats_too_often(record, st, action):
                return StepOutcome.STOP
            return await self._interact_step(record, st, action, gate)
        return StepOutcome.STOP  # stop

    @staticmethod
    def _repeats_too_often(record: RunRecord, st: RunState, action: AgentAction) -> bool:
        """Анти-залипание: повтор того же действия по тем же целям.

        fill/fill_form тем же значением второй раз бессмыслен, click («показать
        ещё», пагинация) законно повторяется — отсюда разные лимиты.
        """
        signature = action_signature(action)
        st.repeats[signature] = st.repeats.get(signature, 0) + 1
        if st.repeats[signature] <= REPEAT_LIMITS.get(action.action, 2):
            return False
        record.metadata["action_loop_guard"] = (
            f"{action.action} повторён {st.repeats[signature]}× — остановка ACT"
        )
        return True

    async def _interact_step(
        self,
        record: RunRecord,
        st: RunState,
        action: AgentAction,
        gate: AttendedGate | None,
    ) -> StepOutcome:
        """Tier 1/2/3 интеракция (doc 25): click/fill/fill_form по индексу элемента."""
        assert st.current is not None
        batch = action.action == "fill_form" and bool(action.fields)
        single = action.action in ("click", "fill") and action.element_index is not None
        if not (batch or single):
            return StepOutcome.STOP

        current = await act_on_element(
            self._browser,
            record,
            action,
            st.current,
            origin=st.origin,
            step_index=st.step_index,
            snapshots=st.snapshots,
            visited=st.visited,
            gate=gate,
            destructive_signals=self._enforcer.destructive_signals,
            capture=self._capture,
        )  # I-H12
        if current is None:  # Tier 2 submit не подтверждён человеком
            return StepOutcome.STOP
        if single and record.metadata.get("handoff_done"):
            # Tier 3: необратимый шаг сделан человеком — дальше только зафиксировать
            # исход. Иначе агент искал следующую кнопку и на живом прогоне потянулся
            # к «Удалить корзину». Пачка полей до handoff не доходит по построению.
            current.priority = True
            st.current = current
            return StepOutcome.STOP
        st.adopt(current)
        return StepOutcome.CONTINUE

    async def _finish_canceled(self, record: RunRecord) -> RunRecord:
        record.status = "canceled"
        record.metadata["canceled_by_user"] = True
        record.finished_at = _now()
        self._store.save(record)
        await self._safe_close()  # браузер закрывается и на отменённом прогоне
        return record

    # ------------------------------------------------------------ internals
    async def _navigate_observe(
        self,
        record: RunRecord,
        url: str,
        origin: str,
        robots: RobotsPolicy,
        *,
        first: bool,
        step_index: int,
    ) -> tuple[PageSnapshot, str] | None:
        return await navigate_and_observe(
            self._browser,
            record,
            url,
            origin,
            robots,
            first=first,
            step_index=step_index,
            store=self._store,
            enforcer=self._enforcer,
            page_timeout_ms=self._s.page_timeout_ms,
            dismiss_consent=self._dismiss_consent,
        )

    async def _dismiss_consent(self, record: RunRecord, url: str) -> None:
        """D-11: обёртка над общей механикой — держит счётчик «1 клик на сайт»."""
        status = await dismiss_consent(
            self._consent, self._browser, record, url, click_used=self._consent_click_used
        )
        if status.startswith("clicked"):
            self._consent_click_used = True

    async def _safe_close(self) -> None:
        try:
            await self._browser.close()
        except Exception as exc:
            # Закрытие идёт в finally-путях, в том числе после уже случившейся
            # ошибки: ронять run из-за неудачного close нельзя, но молчать о
            # висящем браузере тоже (следующий run упрётся в лок).
            logger.warning("browser close failed (%s: %s)", type(exc).__name__, exc)
