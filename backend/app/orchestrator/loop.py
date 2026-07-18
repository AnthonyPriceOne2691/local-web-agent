"""Crawl Orchestrator — agent loop (doc 04): детерминированная state machine,
LLM выбирает только среди top-K кандидатов, contract-lite guards до Playwright.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import httpx

from app.browser.base import BrowserSession
from app.config import Settings
from app.contracts import guards
from app.contracts.context import ActionContext
from app.contracts.enforcer import ContractEnforcer
from app.extraction.synthesis_validator import SynthesisValidator
from app.llm.navigator import Navigator
from app.llm.ollama_client import OllamaClient
from app.llm.synthesizer import Synthesizer
from app.navigation.candidate_queue import build_candidates
from app.navigation.intent import classify_intent
from app.navigation.path_hints import PathHints
from app.navigation.probes import filter_alive
from app.observer.links import normalize_url, origin_of
from app.observer.snapshot import build_snapshot
from app.orchestrator.robots import RobotsPolicy
from app.orchestrator.states import State
from app.schemas.extraction import ExtractionResult
from app.schemas.run import CrawlStep, RunRecord, Violation
from app.schemas.snapshot import AgentAction, Candidate, PageSnapshot, ScreenshotRef
from app.storage.run_store import RunStore

SPA_TEXT_THRESHOLD = 200
# Drift auto-tighten (doc 13 § Drift detection)
DRIFT_HARD_FOR_LOW_TEMP = 3   # hard violations ≥ 3/run → nav temperature 0.4 → 0.2
DRIFT_IH6_FOR_TOP5 = 2        # fabricated URL ≥ 2 → shrink candidate list to top 5
DRIFT_MIN_RECOVERIES = 2      # recovery success < 50% (при ≥2 попытках) → fallback-only


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

    # ------------------------------------------------------------------ run
    async def run(
        self, record: RunRecord, cancel_event: asyncio.Event | None = None
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
            alive_probes, legal_probes = await self._probe_slugs(record.intent, origin)
            await self._browser.start()

            current: PageSnapshot | None = None
            next_url: str | None = normalize_url(cfg.start_url)
            extract_streak = 0
            step_index = 0

            canceled = False
            while step_index < cfg.max_pages * 2:
                if _is_canceled(cancel_event):  # FR-3.8: граница state (перед OBSERVE)
                    canceled = True
                    break
                step_index += 1
                # ---------------- NAVIGATE + OBSERVE
                if next_url is not None:
                    nav = await self._navigate_observe(
                        record, next_url, origin, robots,
                        first=not snapshots, step_index=step_index,
                    )
                    next_url = None
                    if nav is None:  # skipped/failed — PLAN с прежней страницы
                        if current is None:
                            break
                        continue
                    current, origin = nav
                    visited.add(current.url)
                    snapshots.append(current)
                    homepage = homepage or current
                    record.pages_visited = len(visited)
                    record.current_url = current.url
                    if current.status in ("captcha", "login_wall"):  # blocker → stop (doc 04)
                        record.metadata["blocked_by"] = current.status
                        break
                    self._store.save(record)

                # ---------------- PLAN
                if _is_canceled(cancel_event):  # FR-3.8: граница state (перед PLAN)
                    canceled = True
                    break
                candidates = build_candidates(
                    snapshot=current, homepage=homepage, intent=record.intent, task=cfg.task,
                    hints=self._hints, origin=origin, visited=visited,
                    alive_probes=alive_probes, legal_probes=legal_probes,
                    top_k=self._s.top_k_candidates,
                )
                pages_left = cfg.max_pages - len(visited)
                action, step_violations, llm_stats = await self._plan_validated(
                    record, current, candidates, visited, hops, origin, pages_left, robots,
                )
                violations_total += len(step_violations)

                step = CrawlStep(
                    index=step_index, state=State.ACT, url=current.url,
                    action=action.action, target_url=action.url,
                    reasoning=action.reasoning[:300], violations=step_violations, llm_stats=llm_stats,
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
                break  # stop

            # ---------------- SYNTHESIZE (пропускается при cancel — doc 15)
            if canceled or _is_canceled(cancel_event):
                record.status = "canceled"
                record.metadata["canceled_by_user"] = True
                record.finished_at = _now()
                self._store.save(record)
                await self._safe_close()
                return record
            result = await self._synthesize(record, snapshots)
        except Exception as exc:  # noqa: BLE001 — run не должен терять запись
            record.status = "failed"
            record.error_message = str(exc)[:500]
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
        return record

    # ------------------------------------------------------------ internals
    async def _probe_slugs(self, intent: str, origin: str) -> tuple[list[str], list[str]]:
        cache: dict[str, bool] = {}
        async with httpx.AsyncClient() as client:
            alive = await filter_alive(client, origin, self._hints.slugs_for(intent), cache)
            legal = (
                await filter_alive(client, origin, self._hints.legal_slugs, cache)
                if intent == "contact"
                else []
            )
        return alive, legal

    async def _navigate_observe(
        self, record: RunRecord, url: str, origin: str, robots: RobotsPolicy,
        *, first: bool, step_index: int,
    ) -> tuple[PageSnapshot, str] | None:
        if not robots.allowed(url):  # G-H5
            record.steps.append(CrawlStep(index=step_index, state=State.OBSERVE, url=url,
                                          note="robots_disallow — skipped"))
            return None
        t_nav = time.perf_counter()
        final_url = None
        timeout_ms = self._enforcer.effective_timeout_ms(self._s.page_timeout_ms)  # G-H6
        for attempt in (1, 2):  # retry 1× (doc 03)
            try:
                final_url = await self._browser.goto(url, timeout_ms=timeout_ms)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    record.steps.append(CrawlStep(index=step_index, state=State.OBSERVE, url=url,
                                                  note=f"nav_error: {str(exc)[:150]}"))
                    return None
                await self._browser.wait(2000)

        ok, new_origin = guards.check_redirect(final_url, origin, first_navigation=first)  # I-H9
        if not ok:
            record.steps.append(CrawlStep(index=step_index, state=State.OBSERVE, url=url,
                                          note="redirect_offsite — discarded"))
            return None
        if new_origin != origin:
            record.metadata["landing_domain_adopted"] = new_origin

        raw = await self._browser.raw_snapshot()
        if len(raw.get("main_text") or "") < SPA_TEXT_THRESHOLD:
            try:
                await self._browser.wait_networkidle(10000)
            except Exception:  # noqa: BLE001
                pass
            raw = await self._browser.raw_snapshot()
        snapshot = build_snapshot(raw, page_url=final_url, origin=new_origin)
        await self._maybe_screenshot(record, snapshot, step_index)
        record.steps.append(CrawlStep(index=step_index, state=State.OBSERVE, url=snapshot.url,
                                      duration_ms=int((time.perf_counter() - t_nav) * 1000),
                                      screenshot_paths={s.profile: s.relative_path
                                                        for s in snapshot.screenshots}))
        return snapshot, new_origin

    async def _maybe_screenshot(self, record: RunRecord, snapshot: PageSnapshot, step_index: int) -> None:
        mode = record.config.capture_screenshots
        spa_fallback = len(snapshot.main_text) < SPA_TEXT_THRESHOLD  # docs 03/22
        if mode == "never" or (mode == "auto" and not spa_fallback):
            return
        rel = f"screenshots/{step_index:03d}_desktop.png"
        path = self._store.artifacts_dir(record.id) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await self._browser.screenshot(str(path))
            snapshot.screenshots.append(
                ScreenshotRef(profile="desktop", relative_path=rel, width=1440, height=900)
            )
        except Exception:  # noqa: BLE001 — скриншот не валит run
            pass

    def _action_ctx(
        self, record: RunRecord, current: PageSnapshot, candidates: list[Candidate],
        visited: set[str], hops: dict[str, int], origin: str, robots: RobotsPolicy,
    ) -> ActionContext:
        return ActionContext(
            origin=origin, start_url=record.config.start_url, current_url=current.url,
            intent=record.intent, candidates={normalize_url(c.href) for c in candidates},
            visited=visited, hops=hops, max_pages=record.config.max_pages,
            max_depth=record.config.max_depth, pages_visited=len(visited), robots=robots,
        )

    async def _plan_validated(
        self,
        record: RunRecord,
        current: PageSnapshot,
        candidates: list[Candidate],
        visited: set[str],
        hops: dict[str, int],
        origin: str,
        pages_left: int,
        robots: RobotsPolicy,
    ) -> tuple[AgentAction, list[Violation], dict]:
        violations: list[Violation] = []
        llm_stats: dict = {}
        retry_note = ""
        drift = record.metadata.setdefault(
            "drift", {"hard_total": 0, "ih6": 0, "replan_ok": 0, "replan_fail": 0, "fallbacks": 0}
        )
        cands = candidates[: 5 if drift["ih6"] >= DRIFT_IH6_FOR_TOP5 else None]
        ctx = self._action_ctx(record, current, cands, visited, hops, origin, robots)

        replans_used = 0
        if not self._fallback_only(drift):
            for attempt in range(self._enforcer.max_replans_per_step + 1):
                temperature = 0.2 if drift["hard_total"] >= DRIFT_HARD_FOR_LOW_TEMP else 0.4
                action, llm_stats = await self._navigator.propose(
                    task=record.config.task, intent=record.intent, snapshot=current,
                    candidates=cands, visited=visited, pages_left=pages_left,
                    retry_note=retry_note, temperature=temperature,
                )
                replans_used = attempt
                if action is None:  # I-H7 invalid schema
                    violations.append(Violation(constraint_id="I-H7", message="unparseable action",
                                                recovered=False))
                    drift["hard_total"] += 1
                    retry_note = "response was not valid action JSON"
                    continue
                if action.action != "navigate":
                    self._mark_recovered(violations, replans_used, drift)
                    return action, violations, llm_stats
                hard, softs = self._enforcer.validate_navigate(action, ctx)
                violations.extend(softs)
                if hard is None:
                    self._mark_recovered(violations, replans_used, drift)
                    return action, violations, llm_stats
                violations.append(hard)
                drift["hard_total"] += 1
                if hard.constraint_id == "I-H6":
                    drift["ih6"] += 1
                    if drift["ih6"] >= DRIFT_IH6_FOR_TOP5:  # auto-tighten: top-5 (doc 13)
                        cands = cands[:5]
                        ctx.candidates = {normalize_url(c.href) for c in cands}
                if hard.constraint_id == "G-H1":  # budget → форс stop, не replan
                    return (AgentAction(action="stop", reasoning="page budget exhausted"),
                            violations, llm_stats)
                retry_note = f"{hard.constraint_id}: {hard.message}"
            drift["replan_fail"] += 1

        # fallback: детерминированный link scorer (recovery R2, doc 13)
        drift["fallbacks"] += 1
        for cand in candidates:
            fallback = AgentAction(action="navigate", url=cand.href,
                                   reasoning="fallback: top candidate")
            hard, _ = self._enforcer.validate_navigate(fallback, ctx)
            if hard is None:
                for v in violations:
                    v.recovered = True
                return fallback, violations, llm_stats
        return AgentAction(action="stop", reasoning="no valid candidates"), violations, llm_stats

    @staticmethod
    def _fallback_only(drift: dict) -> bool:
        """Recovery success < 50% при ≥2 попытках → link_scorer до конца run (doc 13)."""
        attempts = drift["replan_ok"] + drift["replan_fail"]
        return attempts >= DRIFT_MIN_RECOVERIES and drift["replan_ok"] / attempts < 0.5

    @staticmethod
    def _mark_recovered(violations: list[Violation], replans_used: int, drift: dict) -> None:
        if not violations:
            return
        for v in violations:
            v.recovered = True
        if replans_used > 0:
            drift["replan_ok"] += 1

    async def _synthesize(self, record: RunRecord, snapshots: list[PageSnapshot]) -> ExtractionResult:
        if not snapshots:
            return ExtractionResult(status="failed", summary="no pages observed")
        record.steps.append(CrawlStep(index=len(record.steps) + 1, state=State.SYNTHESIZE))
        self._store.save(record)
        await self._llm.unload(self._s.nav_model)  # swap nav → synth (doc 14)
        result, stats = await self._synthesizer.synthesize(task=record.config.task, snapshots=snapshots)
        record.steps[-1].llm_stats = stats
        return result

    async def _safe_close(self) -> None:
        try:
            await self._browser.close()
        except Exception:  # noqa: BLE001
            pass
