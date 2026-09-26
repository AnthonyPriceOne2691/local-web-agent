# 02 — Architecture

> Local Web Agent · Design doc · **v0.2.1** · 2026-07-05

## High-level diagram

```
┌─────────────────────────────────────────────────────────────────┐
│              Layer 2 — Research Chat (Phase 3–4, doc 24)       │
│  Chat UI / agent research  →  Meta-Agent  →  Compare Synth     │
└───────────────────────────────┬─────────────────────────────────┘
                                │ tools: crawl_site, compare_results
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Layer 1 — Crawl Worker (Phase 1–2)                  │
│  Client (CLI / curl)  │  crawl --url --task                     │
└───────────────────────────────┬─────────────────────────────────┘
                                │ REST
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI, local)                      │
│                                                                  │
│  ┌─────────────────┐    ┌──────────────────────────────────┐   │
│  │ Crawl API       │───▶│ Crawl Orchestrator               │   │
│  │ (routes)        │    │ (agent loop, state machine)      │   │
│  └─────────────────┘    └──────────────┬───────────────────┘   │
│                                        │                        │
│         ┌──────────────────────────────┼──────────────────┐    │
│         │                              │                  │    │
│  ┌──────▼──────┐              ┌────────▼────────┐  ┌─────▼────┐│
│  │ Browser     │              │ LLM Engine      │  │ Contract ││
│  │ (Playwright)│              │ (Ollama)        │  │ Enforcer ││
│  └──────┬──────┘              └────────┬────────┘  └─────▲────┘│
│         │                              │                  │    │
│  ┌──────▼──────┐              ┌────────▼────────┐         │    │
│  │ Page        │─────────────▶│ Action Planner  │─────────┘    │
│  │ Observer    │   snapshot   │ (parse LLM JSON)│              │
│  └─────────────┘              └─────────────────┘              │
│                                                                  │
│  ┌─────────────────┐    ┌──────────────────────────────────┐   │
│  │ Run Store       │    │ Extraction Synthesizer           │   │
│  │ (SQLite)        │    │ (final JSON pass, R1)            │   │
│  └─────────────────┘    └──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Компоненты

### 1. Client (CLI)

**Назначение:** запуск crawl, мониторинг прогресса, просмотр результатов.

**MVP scope:**
- `agent crawl --url URL --task "..." [--max-pages 10] [--max-depth 2]`
- `agent runs list` / `agent runs show <id>`
- Progress: step counter, current URL, last action
- Output: JSON file + optional Markdown report

**Технология:** Python `typer` или Click; thin wrapper над REST (или in-process для CLI).

### 2. Crawl API

**Назначение:** REST endpoints для старта run, polling, получения result; **global run lock** (D-12: 1 активный crawl, второй POST → 409) и cancel-флаг (FR-3.8).

**MVP:** см. [15-api-cli-spec.md](15-api-cli-spec.md)

### 3. Browser (Playwright)

**Назначение:** реальный headless Chromium — navigate, wait, extract DOM.

**Ответственность:**
- Launch / reuse browser context per run
- Navigate to URL with timeout
- Wait for page ready (networkidle or domcontentloaded)
- Return Page handle to Observer
- Execute validated actions: `click_link`, `go_back` (MVP: navigate by URL only)

**Interface:** `BrowserSession` Protocol — `goto(url)`, `get_page_state()`, `close()`

### 4. Page Observer

**Назначение:** превращает live page в **compact snapshot** для LLM.

**MVP snapshot fields:**
- `url`, `title`, `meta_description`
- `headings[]` (h1–h3)
- `main_text` (truncated, см. doc 20)
- `links[]` — `{href, text, same_domain}` capped at N
- `status`: login_wall | captcha | ok | error

**Не в MVP:** full HTML, accessibility tree. **Screenshots:** doc 22 (Phase 1).

### 5. LLM Engine

**Назначение:** два режима — **navigation** (Qwen instruct) и **extraction** (R1 JSON).

**См.:** [14-llm-model-split.md](14-llm-model-split.md), [16-prompts-library.md](16-prompts-library.md)

### 6. Action Planner

**Назначение:** парсит structured output LLM → typed `AgentAction`.

```python
# Conceptual
AgentAction = Navigate(url) | ExtractNow() | Stop(reason)
```

**Recovery:** malformed JSON → 1 regenerate → heuristic fallback (first relevant link).

### 7. Contract Enforcer (ABC-lite)

**Назначение:** runtime проверка **каждого действия** перед Playwright — реализация Agent Behavioral Contracts (Bhardwaj, arXiv:2602.22302).

**См.:** [13-behavioral-contracts.md](13-behavioral-contracts.md) · статья: [arXiv:2602.22302](https://arxiv.org/abs/2602.22302)

**MVP:** domain allowlist, URL ∈ snapshot links, no submit/auth, robots.txt; dual enforcement с orchestrator (max pages/depth). Recovery = replan (≤2) → link scorer. **< 10 ms/action**.

### 8. Crawl Orchestrator

**Назначение:** agent loop — state machine + **CandidateQueue** (doc 21).

**См.:** [04-crawl-orchestrator.md](04-crawl-orchestrator.md), [21-navigation-hints.md](21-navigation-hints.md)

### 9. Navigation Hints

**Назначение:** deterministic site access — intent classification, slug dictionaries, link scoring, homepage-first.

**См.:** [21-navigation-hints.md](21-navigation-hints.md) · data: `data/navigation/path_hints.yaml`

### 10. Extraction Synthesizer

**Назначение:** после crawl + **vision batch** — финальный R1 pass → `ExtractionResult` JSON.

**Input:** DOM snapshots + **`vision_insights[]` text** (doc 23); R1 не получает raw PNG.

**MVP:** один вызов в конце run; incremental extract on `ExtractNow` — P1.

### 11. Vision (Loader + Analyzer)

**Назначение:** загрузить PNG с диска → Ollama VLM → structured `VisionInsight` → attach к snapshot.

**Модули:** `backend/app/vision/` — `loader.py`, `analyzer.py`, `ollama_vision.py`

**См.:** [23-vision-analysis.md](23-vision-analysis.md) · model: `qwen2.5vl:7b` (doc 14)

**Phase:** batch после crawl loop, перед SYNTHESIZE (Phase 2).

### 12. Run Store

**Назначение:** персистентность runs, steps, snapshots, **research sessions** (Phase 3).

**См.:** [12-session-storage.md](12-session-storage.md)

### 13. Research Chat Agent (Layer 2)

**Назначение:** meta-agent + tool executor + compare synthesizer; multi-site sequential queue.

**Модули:** `backend/app/research/` — `meta_agent.py`, `tool_executor.py`, `compare_synthesizer.py`, `session_store.py`

**См.:** [24-research-chat-agent.md](24-research-chat-agent.md)

**Phase:** CLI `agent research` — Phase 3; Chat UI — Phase 4.

**Не смешивать** с crawl orchestrator state machine.

## Основной поток (happy path)

```
1. User: crawl https://example.com --task "find enterprise pricing"
2. Orchestrator: INIT → intent + path_hints → robots.txt → homepage-first
3. Loop:
   a. Observer → PageSnapshot
   b. CandidateQueue → top-K candidates (doc 21)
   c. LLM (Qwen) → pick among candidates
   d. Contract Enforcer → validate
   e. Execute (navigate) OR accumulate snapshot
   f. Checkpoint to Run Store
   g. Stop if: early stop | max pages | dead end
4. Vision batch (if enabled): VisionLoader → VisionAnalyzer → vision_insights on snapshots
5. Extraction Synthesizer (R1) → ExtractionResult
6. CLI/API: JSON + trace
```

### Happy path — multi-site (Layer 2, doc 24)

```
1. User (chat): [url1..url4] + "describe design and differences"
2. Meta-agent: intent=comparative_design → plan 4 × crawl_site
3. Sequential queue (D-7):
   each → Layer 1 happy path → ExtractionResult
4. compare_results(run_ids, rubric=design_diff) → ComparisonResult
5. Chat reply + comparison_report.md
```

## Границы MVP

| In MVP | Post-MVP |
|--------|----------|
| Sequential page visits | Parallel tabs |
| Playwright-only fetch | HTTP probe tier (F1) + Playwright escalate (F2) |
| path_hints + intent (Phase 1) | Expanded GEO slugs from production runs |
| DOM observation + screenshot PNG | Vision batch in hot loop |
| Vision VLM (`vision_insights`) | Web UI gallery |
| Same-domain default | Cross-domain with allowlist UI |
| CLI + REST (Layer 1) | Research Chat UI (Layer 2) |
| Single-site crawl | Multi-site compare (doc 24) |
| SQLite runs | Research Session store |
| Navigate by URL | Click by selector / coord |

## Repo layout (planned)

**Инженерные ограничения:** каждый файл в `backend/app/` — **≤ 500 LOC**; см. [18-engineering-standards.md](18-engineering-standards.md).

```
local-web-agent/
├── README.md
├── docs/                    # design documents (this folder)
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI wiring
│   │   ├── config.py
│   │   ├── api/             # routes (thin)
│   │   ├── schemas/
│   │   ├── browser/         # Playwright behind protocol
│   │   ├── observer/        # snapshot builder
│   │   ├── orchestrator/    # crawl loop + state machine
│   │   ├── navigation/      # intent, path_hints, candidate_queue, link_scorer
│   │   ├── contracts/       # ABC-lite enforcer
│   │   ├── llm/
│   │   ├── vision/          # loader + VLM analyzer (doc 23)
│   │   ├── extraction/      # synthesizer + parsers
│   │   ├── research/        # meta-agent, compare, sessions (doc 24)
│   │   └── storage/
│   ├── tests/
│   └── pyproject.toml
├── cli/
│   └── main.py              # typer entrypoint
├── data/
│   ├── contracts/
│   ├── navigation/          # path_hints.yaml, viewports.yaml
│   ├── prompts/
│   │   └── rubrics/         # design_diff, content_completeness (doc 24)
│   └── runs/                # SQLite + run artifacts
└── scripts/
    ├── setup_mac.sh
    ├── download_models.sh
    ├── check_module_size.py
    └── spike/               # Phase 0 benchmark
```

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial architecture |
| 2026-07-05 | Contract Enforcer: явная привязка к ABC arXiv:2602.22302 |
| 2026-07-05 | Navigation Hints component + path_hints.yaml; hybrid happy path (doc 21) |
| 2026-07-05 | Vision component (doc 23); happy path: vision batch before SYNTHESIZE |
| 2026-07-05 | **v0.2:** Layer 2 Research Chat (doc 24); research/ module; multi-site happy path |
| 2026-07-05 | **v0.2.1 (review):** fix вложенного code fence в happy path; Crawl API + run lock (D-12) и cancel |
