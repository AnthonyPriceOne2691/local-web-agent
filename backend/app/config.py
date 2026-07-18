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

    # LLM (канон doc 16; single-model qwen3 — рекомендация Phase 0, doc 19:
    #   LWA_NAV_MODEL=qwen3:14b LWA_SYNTH_MODEL=qwen3:14b)
    ollama_url: str = "http://localhost:11434"
    nav_model: str = "qwen2.5:14b-instruct"
    synth_model: str = "deepseek-r1:14b"
    nav_num_ctx: int = 8192
    synth_num_ctx: int = 16384
    nav_max_tokens: int = 400
    synth_max_tokens: int = 4096
    llm_timeout_s: float = 300.0

    # Crawl defaults (doc 04)
    max_pages: int = 10
    max_depth: int = 2  # hop depth, D-13
    rate_limit_ms: int = 1000
    page_timeout_ms: int = 30000
    respect_robots: bool = True
    top_k_candidates: int = 10

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
