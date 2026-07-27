"""FastAPI wiring (< 150 LOC, doc 18). DI: фабрика оркестратора в app.state —
тесты подменяют её на моки."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes_health import router as health_router
from app.api.routes_runs import router as runs_router
from app.api.routes_sessions import router as sessions_router
from app.browser.playwright_session import PlaywrightSession
from app.config import Settings, get_settings
from app.contracts.enforcer import ContractEnforcer
from app.llm.navigator import Navigator
from app.llm.ollama_client import OllamaClient
from app.llm.synthesizer import Synthesizer
from app.navigation.path_hints import PathHints
from app.orchestrator.loop import CrawlOrchestrator
from app.research.compare_synthesizer import CompareSynthesizer
from app.research.llm_planner import LlmPlanner
from app.research.runner import ResearchRunner
from app.storage.session_store import SqliteSessionStore
from app.storage.sqlite_store import SqliteRunStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.llm_client = OllamaClient(settings.ollama_url, timeout_s=settings.llm_timeout_s)
        app.state.run_store = SqliteRunStore(settings.runs_dir)
        app.state.session_store = SqliteSessionStore(settings.runs_dir)
        app.state.hints = PathHints.load(settings.navigation_dir)
        app.state.enforcer = ContractEnforcer.load(settings.contracts_dir)  # fail fast (doc 13)
        app.state.background_tasks = set()
        app.state.cancel_events = {}  # run_id → asyncio.Event (FR-3.8)
        app.state.session_cancel_events = {}  # session_id → asyncio.Event (doc 24)
        app.state.resume_events = {}  # run_id → asyncio.Event (attended, Phase 5)
        app.state.session_resume_events = {}  # session_id → asyncio.Event (attended)
        swept = app.state.run_store.startup_sweep()  # zombie runs (doc 12)
        swept += app.state.session_store.startup_sweep()  # zombie sessions
        if swept:
            print(f"startup sweep: {swept} orphaned record(s) → failed")

        def orchestrator_factory() -> CrawlOrchestrator:
            return CrawlOrchestrator(
                settings=settings,
                browser=PlaywrightSession(),
                navigator=Navigator(app.state.llm_client, settings),
                synthesizer=Synthesizer(app.state.llm_client, settings),
                llm_client=app.state.llm_client,
                store=app.state.run_store,
                hints=app.state.hints,
                enforcer=app.state.enforcer,
            )

        app.state.orchestrator_factory = orchestrator_factory

        def research_runner_factory() -> ResearchRunner:
            planner = (
                LlmPlanner(app.state.llm_client, settings) if settings.planner == "llm" else None
            )  # doc 24 § Planner
            return ResearchRunner(
                settings=settings,
                run_store=app.state.run_store,
                session_store=app.state.session_store,
                orchestrator_factory=app.state.orchestrator_factory,
                compare=CompareSynthesizer(app.state.llm_client, settings),
                planner=planner,
            )

        app.state.research_runner_factory = research_runner_factory
        yield
        await app.state.llm_client.aclose()

    app = FastAPI(title="Local Web Agent", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(runs_router)
    app.include_router(sessions_router)
    if settings.ui_dist_dir.is_dir():  # Chat UI (Phase 4): same-origin статика, без CORS
        app.mount("/", StaticFiles(directory=settings.ui_dist_dir, html=True), name="ui")
    return app


app = create_app()
