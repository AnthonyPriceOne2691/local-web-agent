# 07 — Tech Stack (Local M5) — Recommended

> Local Web Agent · Design doc · **v0.2.1** · 2026-07-05  
> Status: **recommended for implementation**

## Принципы выбора

1. **Local-first** — zero cloud в MVP  
2. **Familiar** — FastAPI, Python (стек Voice Interview Coach)  
3. **Minimal moving parts** — без LangChain/LangGraph на старте  
4. **Correctness over speed** — tracing + contracts важнее sub-second LLM  
5. **Real browser** — Playwright, не curl/httpx alone  

---

## LLM strategy: navigation + extraction split

```
Qwen 14B instruct          DeepSeek R1 14B
(navigation decisions)  +  (final JSON synthesis)
        │                              │
        └──────────▶ Crawl loop ◀──────┘
```

| Role | Model | Why |
|------|-------|-----|
| **Navigation / PLAN step** | `qwen2.5:14b-instruct` | Fast instruct following; JSON actions |
| **Extraction / SYNTHESIZE** | `deepseek-r1:14b` | Reasoning over multiple pages → structured JSON |

**Не держать обе 14B одновременно** (~18 GB models). Swap: Qwen during loop → evict → load R1 for synthesis (как Voice Interview Coach Mode 1 → summary).

**Fallback:** если Qwen navigation качество слабое в Phase 0 — try `llama3.1:8b` (faster, dumber).

---

## Stack at a glance

```
┌─────────────────────────────────────────────────────────────┐
│  CLI: typer → REST client (or in-process)                    │
└───────────────────────────┬─────────────────────────────────┘
                            │ http://localhost:8001
┌───────────────────────────▼─────────────────────────────────┐
│  Python 3.12 · FastAPI · uvicorn                             │
│  ┌─────────────┐ ┌──────────────┐ ┌─────────────────────┐  │
│  │ Orchestrator│ │ Contract     │ │ Run Store           │  │
│  │             │ │ Enforcer     │ │ SQLite              │  │
│  └──────┬──────┘ └──────┬───────┘ └─────────────────────┘  │
│         └───────────────┼──────────────────────────────────│
│                         ▼                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Playwright   │  │ Qwen 14B     │  │ Page Observer    │  │
│  │ Chromium     │  │ + R1 14B     │  │ (DOM extract)    │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         Ollama daemon (brew) · Playwright browsers (playwright install)
```

---

## Layer-by-layer

### Runtime & packaging

| Choice | Version | Why |
|--------|---------|-----|
| **Python** | 3.12 | Async, ecosystem |
| **Package manager** | **uv** | Fast; same as voice-interview-coach |
| **Process** | 1× uvicorn + Ollama + Playwright subprocess | Solo tool |

### Backend framework

| Choice | Why |
|--------|-----|
| **FastAPI** | Async, background tasks for long crawls |
| **uvicorn** | ASGI |
| **httpx** | Ollama streaming |
| **pydantic v2** | ExtractionResult, configs |
| **structlog** | Structured crawl logs |

**Not MVP:** Celery, Redis, Docker, LangChain.

### Browser

| Choice | Why |
|--------|-----|
| **Playwright** | Best headless JS; Python API |
| **playwright** pip package | **`async_api` с самого начала** — FastAPI event loop async; sync_api блокировал бы loop / требовал thread-обвязки. Сниппеты в docs 22/23 уже async — противоречие v0.1 устранено |
| Install | `playwright install chromium` |

**Not MVP:** Selenium (heavier), raw httpx (no JS).

### LLM — Ollama

> Канон params — [16-prompts-library.md](16-prompts-library.md) · A/B кандидаты Phase 0 — [14-llm-model-split.md](14-llm-model-split.md)

| Role | Model | RAM ~ |
|------|-------|-------|
| Navigation | `qwen2.5:14b-instruct` (provisional; A/B: qwen3:14b, gpt-oss:20b) | ~9 GB |
| Synthesis | `deepseek-r1:14b` (provisional) | ~9 GB |
| Vision | `qwen2.5vl:7b` (Phase 2, doc 23) | ~6 GB |

**Daemon env:** `OLLAMA_MAX_LOADED_MODELS=1` (гарантия одной модели в RAM); выгрузка между pass'ами — `keep_alive: 0` (doc 14 § Swap mechanics).

### CLI

| Choice | Why |
|--------|-----|
| **typer** | Clean subcommands |
| **rich** | Progress bars, tables for `runs list` |

### Storage

| Choice | Why |
|--------|-----|
| **SQLite** | Single file |
| **SQLAlchemy 2.0 + aiosqlite** | Async writes per step |

### robots.txt

| Choice | Why |
|--------|-----|
| **urllib.robotparser** | Stdlib MVP |
| Upgrade P2 | `robotexclusionrulesparser` if edge cases |

---

## Project structure

```
local-web-agent/
├── backend/
│   ├── pyproject.toml
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── api/
│       ├── browser/
│       ├── observer/
│       ├── orchestrator/
│       ├── contracts/
│       ├── llm/
│       ├── extraction/
│       └── storage/
├── cli/
│   └── main.py
├── data/
│   ├── contracts/
│   ├── prompts/
│   └── runs/
└── scripts/
    ├── setup_mac.sh
    └── spike/
```

---

## `pyproject.toml` (core deps)

```toml
[project]
name = "local-web-agent"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "httpx>=0.28",
  "pydantic>=2.10",
  "pydantic-settings>=2.6",
  "sqlalchemy[asyncio]>=2.0",
  "aiosqlite>=0.20",
  "playwright>=1.49",
  "pyyaml>=6.0",
  "structlog>=24.0",
  "typer>=0.15",
  "rich>=13.0",
  "tldextract>=5.0",      # registrable domain (OQ-2, doc 03); offline PSL snapshot
  "rapidfuzz>=3.0",       # S-H3 fuzzy quote match ≥0.85 (doc 13)
  # "trafilatura>=1.8",   # Phase 2: article main-text для content_search (doc 03) — решение по Phase 0 spike
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "pytest-cov", "ruff", "mypy"]
```

---

## System setup (Mac M5)

```bash
brew install ollama
ollama pull qwen2.5:14b-instruct
ollama pull deepseek-r1:14b
ollama pull qwen2.5vl:7b          # vision (Phase 2; тег проверить — doc 14)

cd local-web-agent
uv sync
uv run playwright install chromium
./scripts/setup_mac.sh   # when written
```

Disk: ~9 + 9 + 6 GB моделей + ~1 GB Chromium ≈ **25 GB** — OK на 512 GB (NFR-3.3).

---

## Memory budget (32 GB)

| Phase | Loaded | RAM ~ |
|-------|--------|-------|
| **Crawl loop** | Qwen 14B + Chromium + Python | ~12–16 GB |
| **Synthesis** | R1 14B (+ browser closing) | ~10–14 GB |
| **Headroom** | macOS | ~14 GB ✅ |

---

## Port & dev workflow

Default API port **8001** (avoid clash with voice-interview-coach :8000).

```bash
# T1
ollama serve

# T2
cd backend && uv run uvicorn app.main:app --reload --port 8001

# T3
uv run python -m cli.main crawl --url https://example.com --task "..."
```

> ⚠️ Путь `Other:Another` — **`uv run` может ломаться**; вызывать `.venv/bin/` напрямую (урок из voice-interview-coach).

---

## Explicitly avoided

| Tech | Reason |
|------|--------|
| Cloud browsing APIs | Privacy |
| LangChain agents | Opaque; hard to test |
| Scrapy | Not interactive; no «human» navigation |
| Electron UI MVP | CLI enough |
| PostgreSQL | Single user |

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial stack recommendation |
| 2026-07-05 | **v0.2 (review):** async_api (не sync — противоречило async-сниппетам docs 22/23); +tldextract, +rapidfuzz; vision model в setup + disk budget; OLLAMA_MAX_LOADED_MODELS=1 + keep_alive; модели помечены provisional до Phase 0 |
| 2026-07-05 | **v0.2.1 (review-2):** trafilatura как optional dep (Phase 0 spike решает, doc 03) |
