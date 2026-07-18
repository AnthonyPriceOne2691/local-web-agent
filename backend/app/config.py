"""App settings — env prefix LWA_ (например LWA_NAV_MODEL=qwen3:14b)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LWA_", env_file=".env", extra="ignore")

    # API — bind только localhost (NFR-2.5)
    api_host: str = "127.0.0.1"
    api_port: int = 8001

    # LLM (канон doc 16 v0.5: qwen3:14b single-model — D-2/D-3 closed 2026-07-18;
    #   fallback-пара: LWA_NAV_MODEL=qwen2.5:14b-instruct LWA_SYNTH_MODEL=deepseek-r1:14b)
    ollama_url: str = "http://localhost:11434"
    nav_model: str = "qwen3:14b"
    synth_model: str = "qwen3:14b"
    nav_num_ctx: int = 8192
    synth_num_ctx: int = 16384
    nav_max_tokens: int = 400
    synth_max_tokens: int = 4096
    llm_timeout_s: float = 300.0

    # Vision batch (docs 16/23)
    vision_model: str = "qwen2.5vl:7b"
    vision_num_ctx: int = 8192
    vision_max_tokens: int = 1200
    max_vision_pages: int = 5
    max_vision_calls: int = 12

    # Crawl defaults (doc 04)
    max_pages: int = 10
    max_depth: int = 2  # hop depth, D-13
    rate_limit_ms: int = 1000
    page_timeout_ms: int = 30000
    respect_robots: bool = True
    top_k_candidates: int = 10

    # Research sessions (Phase 3, doc 24)
    max_sites_per_session: int = 10  # M-H2
    site_cooldown_s: float = 2.0
    site_cooldown_hot_s: float = 30.0  # N ≥ 4, fanless thermal
    max_session_duration_min: float = 60.0

    # Chat UI (Phase 4, doc 15 v0.6): SSE poll-паттерн + статика фронта
    sse_poll_interval_s: float = 0.7
    sse_heartbeat_s: float = 15.0
    ui_dist_dir: Path = REPO_ROOT / "frontend" / "dist"

    # Data layout
    data_dir: Path = REPO_ROOT / "data"
    runs_dir_override: Path | None = None  # тесты/сторонний размещение БД

    @property
    def runs_dir(self) -> Path:
        return self.runs_dir_override or self.data_dir / "runs"

    @property
    def artifacts_dir(self) -> Path:
        return self.runs_dir / "artifacts"

    @property
    def prompts_dir(self) -> Path:
        return self.data_dir / "prompts"

    @property
    def navigation_dir(self) -> Path:
        return self.data_dir / "navigation"

    @property
    def contracts_dir(self) -> Path:
        return self.data_dir / "contracts"


def get_settings() -> Settings:
    return Settings()
