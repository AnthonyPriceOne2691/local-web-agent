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
from app.contracts import guards
from app.contracts.enforcer import ContractEnforcer
from app.extraction.synthesis_validator import SynthesisValidator
from app.llm.navigator import Navigator
from app.llm.ollama_client import OllamaClient
from app.llm.synthesizer import Synthesizer
from app.navigation.candidate_queue import build_candidates
from app.navigation.intent import classify_intent
from app.navigation.path_hints import PathHints
from app.observer.blockers import looks_like_challenge
from app.observer.links import normalize_url, origin_of
from app.observer.snapshot import build_snapshot
from app.orchestrator.attended import AttendedGate, reobserve_in_place
from app.orchestrator.capture import SPA_TEXT_THRESHOLD, maybe_screenshot
from app.orchestrator.decide import plan_validated
from app.orchestrator.discovery import looks_like_article, probe_slugs, sitemap_urls
from app.orchestrator.interaction import act_on_element
from app.orchestrator.robots import RobotsPolicy
from app.orchestrator.states import State
from app.orchestrator.vision_batch import run_vision_batch
from app.reporting.markdown import build_report
from app.schemas.extraction import ExtractionResult
from app.schemas.run import CrawlStep, RunRecord
from app.schemas.snapshot import PageSnapshot
from app.storage.run_store import RunStore
from app.vision.analyzer import VisionAnalyzer

logger = logging.getLogger(__name__)

# Drift auto-tighten (doc 13 § Drift detection)
DRIFT_HARD_FOR_LOW_TEMP = 3  # hard violations ≥ 3/run → nav temperature 0.4 → 0.2
DRIFT_IH6_FOR_TOP5 = 2  # fabricated URL ≥ 2 → shrink candidate list to top 5
DRIFT_MIN_RECOVERIES = 2  # recovery success < 50% (при ≥2 попытках) → fallback-only
# G-S1 early stop: «релевантный» кандидат = сигнальный тег, не shallow-бонус
RELEVANT_TAGS = ("slug", "task-kw", "homepage+intent", "probe", "sitemap", "legal-contact")
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
        self._consent_click_used = False  # 1 попытка click на сайт (D-11)
        self._vision = VisionAnalyzer(llm_client, settings)

    # ------------------------------------------------------------------ run
    async def run(
        self,
        record: RunRecord,
        cancel_event: asyncio.Event | None = None,
        attended_gate: AttendedGate | None = None,  # Phase 5: пауза на challenge (doc 24)
    ) -> RunRecord:
        cfg = record.config
        t0 = time.perf_counter()
        record.started_at = record.started_at or _now()
        record.intent = classify_intent(cfg.task, self._hints)
        origin = origin_of(normalize_url(cfg.start_url))
        visited: set[str] = set()
        hops: dict[str, int] = {normalize_url(cfg.start_url): 0}
        snapshots: list[PageSnapshot] = []
        homepage: PageSnapshot | None = None
        violations_total = 0

        config_violations = self._enforcer.check_run_config(cfg)  # P-1/P-2 + G-H4/G-H6
        if any(v.severity == "hard" for v in config_violations):
            record.status = "failed"
            record.error_message = "; ".join(
                f"{v.constraint_id}: {v.message}" for v in config_violations if v.severity == "hard"
            )
            record.finished_at = _now()
            self._store.save(record)
            return record
        if config_violations:  # soft: rate floor / timeout cap — только лог
            record.metadata["config_notes"] = [v.message for v in config_violations]

        try:
            robots = await RobotsPolicy.load(origin, respect=cfg.respect_robots)
            rate_ms = max(
                self._enforcer.effective_rate_ms(cfg.rate_limit_ms, cfg.start_url),
                int(robots.crawl_delay_s * 1000),
            )
            alive_probes, legal_probes, probe_links = await probe_slugs(self._hints, record.intent, origin)
            sitemap_candidates = await sitemap_urls(  # P2.5
                record, origin, robots.sitemaps(), self._hints
            )
            profile = (
                self._s.profile_path(origin) if (cfg.persist_session or self._s.persist_session) else None
            )
            await self._browser.start(headless=not cfg.attended, storage_state_path=profile)

            current: PageSnapshot | None = None
            next_url: str | None = normalize_url(cfg.start_url)
            extract_streak = 0
            step_index = 0
            stale_pages = 0  # G-S1 early stop
            seen_relevant: set[str] = set()
            just_visited = False

            canceled = False
            while step_index < cfg.max_pages * 2:
                if _is_canceled(cancel_event):  # FR-3.8: граница state (перед OBSERVE)
                    canceled = True
                    break
                step_index += 1
                # ---------------- NAVIGATE + OBSERVE
                if next_url is not None:
                    nav = await self._navigate_observe(
                        record,
                        next_url,
                        origin,
                        robots,
                        first=not snapshots,
                        step_index=step_index,
                    )
                    next_url = None
                    if nav is None:  # skipped/failed — PLAN с прежней страницы
                        if current is None:
                            break
                        continue
                    current, origin = nav
                    just_visited = True
                    visited.add(current.url)
                    if record.intent == "content_search" and looks_like_article(current, cfg.task):
                        current.priority = True  # article candidate (doc 24) → 12K excerpt
                    snapshots.append(current)
                    homepage = homepage or current
                    record.pages_visited = len(visited)
                    record.current_url = current.url
                    if current.status in ("captcha", "login_wall"):  # blocker (doc 04)
                        # attended: и captcha (человек проходит проверку), и login_wall
                        # (человек логинится в видимом браузере — Tier 2, doc 25; паролей не храним)
                        if attended_gate is not None and await attended_gate.try_clear(
                            record, current, snapshots, visited
                        ):
                            current = await reobserve_in_place(  # без goto → CF не re-challenge
                                self._browser,
                                record,
                                origin=origin,
                                step_index=step_index,
                                snapshots=snapshots,
                                visited=visited,
                            )
                            homepage = homepage or current
                            continue  # next_url is None → сразу PLAN c этой страницей
                        record.metadata["blocked_by"] = current.status
                        break
                    self._store.save(record)

                # ---------------- PLAN
                if _is_canceled(cancel_event):  # FR-3.8: граница state (перед PLAN)
                    canceled = True
                    break
                if current is None:  # инвариант: к PLAN приходим только со снапшотом
                    break
                candidates = build_candidates(
                    snapshot=current,
                    homepage=homepage,
                    intent=record.intent,
                    task=cfg.task,
                    hints=self._hints,
                    origin=origin,
                    visited=visited,
                    alive_probes=alive_probes,
                    legal_probes=legal_probes,
                    sitemap_urls=sitemap_candidates,
                    probe_links=probe_links,
                    top_k=self._s.top_k_candidates,
                )
                if just_visited:  # G-S1: 3 страницы без новых релевантных ссылок → SYNTHESIZE
                    just_visited = False
                    fresh = {
                        normalize_url(c.href)
                        for c in candidates
                        if any(tag in c.reason for tag in RELEVANT_TAGS)
                    } - seen_relevant
                    if fresh:
                        stale_pages = 0
                        seen_relevant |= fresh
                    else:
                        stale_pages += 1
                        if stale_pages >= EARLY_STOP_STALE_PAGES:
                            record.metadata["early_stop"] = "G-S1: no new relevant links on 3 pages"
                            break
                pages_left = cfg.max_pages - len(visited)
                action, step_violations, llm_stats = await plan_validated(
                    record,
                    current,
                    candidates,
                    visited,
                    hops,
                    origin,
                    pages_left,
                    robots,
                    navigator=self._navigator,
                    enforcer=self._enforcer,
                )
                violations_total += len(step_violations)

                step = CrawlStep(
                    index=step_index,
                    state=State.ACT,
                    url=current.url,
                    action=action.action,
                    target_url=action.url,
                    reasoning=action.reasoning[:300],
                    violations=step_violations,
                    llm_stats=llm_stats,
                )
                record.steps.append(step)
                self._store.save(record)

                # ---------------- ACT
                if action.action == "navigate" and action.url:
                    target = normalize_url(action.url)
                    hops[target] = min(hops.get(target, 99), hops.get(current.url, 0) + 1)
                    next_url = target
                    extract_streak = 0
                    await self._browser.wait(rate_ms)
                    continue
                if action.action == "extract_now":
                    current.priority = True
                    extract_streak += 1
                    if extract_streak >= 2 or pages_left <= 0:  # loop guard, policy #11
                        break
                    continue
                if action.action in ("click", "fill") and action.element_index is not None:  # doc 25
                    current = await act_on_element(
                        self._browser,
                        record,
                        action,
                        current,
                        origin=origin,
                        step_index=step_index,
                        snapshots=snapshots,
                        visited=visited,
                        rate_ms=rate_ms,
                        gate=attended_gate,
                        destructive_signals=self._enforcer.destructive_signals,
                    )  # I-H12
                    if current is None:  # Tier 2 submit не подтверждён человеком
                        break
                    homepage = homepage or current
                    just_visited = True
                    continue
                break  # stop

            # ---------------- SYNTHESIZE (пропускается при cancel — doc 15)
            if canceled or _is_canceled(cancel_event):
                record.status = "canceled"
                record.metadata["canceled_by_user"] = True
                record.finished_at = _now()
                self._store.save(record)
                await self._safe_close()
                return record
            await run_vision_batch(  # doc 23
                record=record,
                snapshots=snapshots,
                settings=self._s,
                store=self._store,
                llm=self._llm,
                analyzer=self._vision,
                close_browser=self._safe_close,
                cancel_event=cancel_event,
            )
            result = await self._synthesize(record, snapshots)
        except Exception as exc:
            logger.exception("crawl run %s crashed at %s", record.id, record.current_url)
            record.status = "failed"
            # str(httpx.ReadTimeout) пуст — без имени типа excluded[] нечитаем (M-H4)
            record.error_message = (str(exc) or type(exc).__name__)[:500]
            record.finished_at = _now()
            self._store.save(record)
            await self._safe_close()
            return record

        await self._safe_close()
        result.run_id = record.id
        result.task = cfg.task
        result.start_url = cfg.start_url
        result.pages_visited = len(visited)
        result.duration_seconds = round(time.perf_counter() - t0, 1)
        result.generated_at = _now()
        if record.metadata.get("blocked_by"):
            result.status = "blocked"
        record.result = self._synth_validator.validate(result, snapshots)  # S-H2/H3/H6, S-G1/G2
        record.status = record.result.status
        record.metadata["violations_total"] = violations_total
        record.finished_at = _now()
        self._store.save(record)
        try:  # markdown report (doc 05) — не валит run
            report_path = self._store.artifacts_dir(record.id) / "report.md"
            report_path.write_text(build_report(record, snapshots), encoding="utf-8")
        except Exception as exc:
            # Результат в БД уже есть; без лога пропавший report.md выглядел бы
            # как «отчёт не предусмотрен», а не как сбой записи.
            logger.warning("report.md not written for run %s (%s: %s)", record.id, type(exc).__name__, exc)
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
        if not robots.allowed(url):  # G-H5
            record.steps.append(
                CrawlStep(index=step_index, state=State.OBSERVE, url=url, note="robots_disallow — skipped")
            )
            return None
        t_nav = time.perf_counter()
        final_url = None
        timeout_ms = self._enforcer.effective_timeout_ms(self._s.page_timeout_ms)  # G-H6
        for attempt in (1, 2):  # retry 1× (doc 03)
            try:
                final_url = await self._browser.goto(url, timeout_ms=timeout_ms)
                break
            except Exception as exc:
                if attempt == 2:
                    logger.warning("goto %s failed twice (%s: %s)", url, type(exc).__name__, str(exc)[:150])
                    record.steps.append(
                        CrawlStep(
                            index=step_index,
                            state=State.OBSERVE,
                            url=url,
                            note=f"nav_error: {str(exc)[:150]}",
                        )
                    )
                    return None
                logger.debug("goto %s failed, retrying (%s)", url, type(exc).__name__)
                await self._browser.wait(2000)

        if final_url is None:  # оба attempt вернули бы None раньше — страховка для чекера
            return None
        ok, new_origin = guards.check_redirect(final_url, origin, first_navigation=first)  # I-H9
        if not ok:
            record.steps.append(
                CrawlStep(index=step_index, state=State.OBSERVE, url=url, note="redirect_offsite — discarded")
            )
            return None
        if new_origin != origin:
            record.metadata["landing_domain_adopted"] = new_origin

        raw = await self._browser.raw_snapshot()
        # SPA-fallback пропускаем на challenge-странице: его networkidle-ожидание даёт
        # anti-bot проверке пройти и проскочить attended-паузу (doc 24)
        if len(raw.get("main_text") or "") < SPA_TEXT_THRESHOLD and not looks_like_challenge(raw):
            try:
                await self._browser.wait_networkidle(10000)
            except Exception as exc:
                # Штатный best-effort: у SPA networkidle может не наступить вовсе,
                # снапшот всё равно снимаем. Уровень debug, а не warning.
                logger.debug("networkidle wait skipped for %s (%s)", final_url, type(exc).__name__)
            raw = await self._browser.raw_snapshot()
        snapshot = build_snapshot(raw, page_url=final_url, origin=new_origin)
        await maybe_screenshot(
            self._browser, self._store, self._dismiss_consent, record, snapshot, step_index
        )
        record.steps.append(
            CrawlStep(
                index=step_index,
                state=State.OBSERVE,
                url=snapshot.url,
                duration_ms=int((time.perf_counter() - t_nav) * 1000),
                screenshot_paths={s.profile: s.relative_path for s in snapshot.screenshots},
            )
        )
        return snapshot, new_origin

    async def _dismiss_consent(self, record: RunRecord, url: str) -> None:
        """D-11: detect → hide → click(reject-first); статус в metadata (честность UC-1)."""
        cfg = record.config
        try:
            status = await self._consent.dismiss(
                self._browser,
                mode=cfg.consent_handling,
                click_mode=cfg.consent_click,
                site_click_used=self._consent_click_used,
            )
        except Exception as exc:
            # Cookie-баннер не убрали — скриншоты будут с оверлеем (D-11);
            # status="failed" уедет в metadata.consent, но причину знает только лог.
            logger.warning("consent dismissal failed on %s (%s: %s)", url, type(exc).__name__, str(exc)[:150])
            status = "failed"
        if status.startswith("clicked"):
            self._consent_click_used = True
        if status != "none":
            record.metadata.setdefault("consent", {})[url] = status

    async def _synthesize(self, record: RunRecord, snapshots: list[PageSnapshot]) -> ExtractionResult:
        if not snapshots:
            return ExtractionResult(status="failed", summary="no pages observed")
        record.steps.append(CrawlStep(index=len(record.steps) + 1, state=State.SYNTHESIZE))
        self._store.save(record)
        await self._llm.unload(self._s.nav_model)  # swap nav → synth (doc 14)
        result, stats = await self._synthesizer.synthesize(
            task=record.config.task, snapshots=snapshots, intent=record.intent
        )
        record.steps[-1].llm_stats = stats
        return result

    async def _safe_close(self) -> None:
        try:
            await self._browser.close()
        except Exception as exc:
            # Закрытие идёт в finally-путях, в том числе после уже случившейся
            # ошибки: ронять run из-за неудачного close нельзя, но молчать о
            # висящем браузере тоже (следующий run упрётся в лок).
            logger.warning("browser close failed (%s: %s)", type(exc).__name__, exc)
