# Design Documents Index

Планирование проекта ведётся через design docs в этой папке. Код пишется только после закрытия Phase 0 benchmark (см. [06-mvp-phases.md](06-mvp-phases.md)).

## Document map

| Doc | Status | Description |
|-----|--------|-------------|
| [00-project-overview.md](00-project-overview.md) | ✅ **v0.4** | Two-layer arch; Research Chat UX; action-capable (Phase 6) |
| [01-requirements.md](01-requirements.md) | ✅ **v0.5.2** | FR/NFR incl. FR-6/FR-7 (actions); SSRF, cancel, D-12, hop depth |
| [02-architecture.md](02-architecture.md) | ✅ **v0.2.1** | Layer 1 + Layer 2 |
| [03-browser-pipeline.md](03-browser-pipeline.md) | ✅ **v0.7** | Playwright; URL norm; redirect/landing policy; trafilatura |
| [04-crawl-orchestrator.md](04-crawl-orchestrator.md) | ✅ **v0.6** | Agent loop + VISION_BATCH; hop depth; landing domain |
| [05-extraction-schema.md](05-extraction-schema.md) | ✅ **v0.4** | ComparisonResult + excluded; article candidates |
| [06-mvp-phases.md](06-mvp-phases.md) | ✅ **v0.10** | **Phases 0–4 DONE**; Phase 5 attended-режим |
| [07-tech-stack.md](07-tech-stack.md) | ✅ **v0.2.1** | Stack + LLM settings (async_api, deps) |
| [12-session-storage.md](12-session-storage.md) | ✅ **v0.6** | SQLite + research sessions реализованы; legacy-импорт; sweep |
| [13-behavioral-contracts.md](13-behavioral-contracts.md) | ✅ **v0.8.2** | ABC; I-H10 click / I-H11 fill safety; I-H3 attended login |
| [14-llm-model-split.md](14-llm-model-split.md) | ✅ **v0.5** | qwen3 single-model канон; VLM; fallback-пара |
| [15-api-cli-spec.md](15-api-cli-spec.md) | ✅ **v0.7** | + SSE events, report, статика UI, attended resume/challenge_wait |
| [16-prompts-library.md](16-prompts-library.md) | ✅ **v0.5** | Params: structured outputs, think; top-10 |
| [17-ui-screens.md](17-ui-screens.md) | ✅ **v0.4** | Chat UI реализован: React 19 + Vite 7 + Tailwind v4 |
| [18-engineering-standards.md](18-engineering-standards.md) | ✅ **v0.2.1** | 500 LOC, SOLID, DRY, coverage; new fixtures |
| [19-phase0-benchmark-results.md](19-phase0-benchmark-results.md) | ✅ **v1.0 DONE** | Все гейты ✅; qwen3 single-model рекомендация |
| [20-context-token-budget.md](20-context-token-budget.md) | ✅ **v0.2.1** | Token budget; non-Latin; compare N>3 |
| [21-navigation-hints.md](21-navigation-hints.md) | ✅ **v0.7** | + content_search, sitemap P2.5, RU keywords |
| [22-page-screenshots.md](22-page-screenshots.md) | ✅ **v0.4** | PNG multi-viewport; D-11 closed (detect→hide→click) |
| [23-vision-analysis.md](23-vision-analysis.md) | ✅ **v0.3** | Key pages, failure modes; qwen2.5vl |
| [24-research-chat-agent.md](24-research-chat-agent.md) | ✅ **v0.8** | Phase 4 DONE; Phase 5 attended; Phase 6 attended-login + persist-session |
| [25-action-framework.md](25-action-framework.md) | 🛠 **v0.5** | Агент действует на сайте: Tier 1 click ✅, Tier 2 login+fill ✅, persist-session ✅; next submit (Phase 6) |

> Номера 08–11 не используются (историческая нумерация, выровнена с voice-interview-coach).

## Project status

| Phase | Status |
|-------|--------|
| Design docs | ✅ v0.5 review pass 2 (hop depth D-13, RU keywords, article candidates D-14, startup sweep, partial failure) + D-11 closed |
| Phase 0 Benchmark | ✅ **DONE 2026-07-13** — все exit-критерии пройдены ([doc 19](19-phase0-benchmark-results.md) v1.0); хвосты: real re-check p50, qwen3 на real перед финалом D-2/D-3 |
| Phase 1 Agent loop | ✅ **DONE 2026-07-18** — backend/app + cli + prompts; 30 тестов, coverage 87%, E2E 3/3 ([doc 06](06-mvp-phases.md) § Phase 1) |
| **Phase 2 Full MVP** | ✅ **DONE 2026-07-18** — exit-бенчмарк 4/5 (80% гейт) + vision E2E (#8) + PLAN p50 7.9 s ([doc 06](06-mvp-phases.md) § Phase 2); 96 тестов, cov 93% |
| **Phase 3 Research Agent** | ✅ **DONE 2026-07-18** — UC-1/UC-2 exit-бенчмарк пройден ([doc 06](06-mvp-phases.md) § Phase 3); 115 тестов |
| **Phase 4 Chat UI** | ✅ **DONE 2026-07-19** — UI + SSE + `planner: llm`; UC-1/UC-2 прогнаны целиком из чата в браузере (9.9 / 18.1 мин), follow-up диалог и re-crawl через планнер работают ([doc 06](06-mvp-phases.md) § Phase 4) |
| **Phase 5 attended-режим** | 🛠 **2026-07-19** — human-in-the-loop прохождение anti-bot challenge (видимый браузер, `waiting_user`, resume, SSE `challenge_wait`, Chat UI, CLI `--attended`); 135 тестов. Реальный Cloudflare-прогон — за пользователем ([doc 24](24-research-chat-agent.md) § Attended-режим) |

## Conventions

- Версия в шапке: `v0.x`
- **Changelog** в конце каждого документа
- Статусы: ✅ зафиксировано · 🔲 TBD · ❌ out of scope
- Новые docs: `21-`, `22-`, … по мере необходимости

## Review order (recommended)

1. Overview → Requirements
2. Architecture → Browser pipeline → **Context/token budget (20)**
3. Crawl orchestrator → **Navigation hints (21)** → Extraction schema
4. Behavioral contracts → MVP phases → **Vision (23)** → **Research Chat (24)** → Tech stack
5. Benchmark results (19) — перед стартом Phase 1

## Pending decisions

| ID | Decision | Status |
|----|----------|--------|
| D-1 | Browser runtime | ✅ Playwright (Chromium headless, **async_api**) — **подтверждён Phase 0** (0 браузерных сбоев) |
| D-2 | LLM planning + navigation | ✅ **CLOSED (2026-07-18):** `qwen3:14b` (`think:false`) — подтверждён Phase 2 exit-бенчмарком на real-сайтах (playwright.dev ✅, ollama.com ✅; PLAN p50 7.9 s). Канон doc 16 v0.5; qwen2.5:14b — fallback |
| D-3 | LLM structured extraction | ✅ **CLOSED (2026-07-18):** `qwen3:14b` (`think:true`) — **single-model split** (ноль свопов; synth max 95.9 s на python.org vs 203 s у r1 в Phase 0). r1:14b — fallback (doc 16 v0.5) |
| D-4 | Observation mode MVP | ✅ DOM-first + screenshots (doc 22) |
| D-5 | Interface Layer 1 | ✅ CLI + REST Phase 1–2 |
| D-5b | Primary product UX | ✅ **Research Chat UI Phase 4** ([doc 24](24-research-chat-agent.md)) |
| D-6a | Page screenshot capture | ✅ **CLOSED** ([doc 22](22-page-screenshots.md)) |
| D-6b | Vision LLM on screenshots | ✅ **CLOSED + подтверждён Phase 0:** `qwen2.5vl:7b` — 5/5 рубрика, JSON 100%, p95 14.3 s ([doc 19](19-phase0-benchmark-results.md) Part B) |
| D-7 | Multi-site execution | ✅ **CLOSED:** sequential queue only ([doc 24](24-research-chat-agent.md)) |
| D-8 | Two-layer architecture | ✅ **CLOSED** ([doc 24](24-research-chat-agent.md)) |
| D-9 | Chat as primary UX | ✅ **CLOSED** Phase 4 ([doc 24](24-research-chat-agent.md)) |
| **D-10** | **Site navigation strategy** | ✅ **CLOSED:** hybrid hints + LLM top-K ([doc 21](21-navigation-hints.md), ref SEOLB) |
| **D-11** | **Cookie-banner dismissal (design audit)** | ✅ **CLOSED:** detect → CSS-hide (default, без согласия) → CMP-click reject-first (fallback); Phase 1 honest capture ([doc 22](22-page-screenshots.md)) |
| **D-12** | **API concurrency** | ✅ **CLOSED:** 1 активный crawl глобально; 409 на второй POST; startup sweep ([doc 15](15-api-cli-spec.md), [doc 12](12-session-storage.md)) |
| **D-13** | **max_depth semantics** | ✅ **CLOSED:** hop depth (навигационные переходы), не сегменты URL — иначе UC-2/sitemap нерабочие ([doc 04](04-crawl-orchestrator.md) policy #2) |
| **D-14** | **content_search: сколько статей искать** | ✅ **CLOSED:** до 3 кандидатов per site, R1 выбирает лучшую — «самая полная», не «первая найденная» ([doc 21](21-navigation-hints.md)) |

## Reference

- **Agent Behavioral Contracts:** Bhardwaj, arXiv:[2602.22302](https://arxiv.org/abs/2602.22302) · локально: `/Users/anthony/Documents/2602.22302v1.pdf`
- **Navigation hints (боевой референс):** Linkbuilding `CONTACT_SCRAPER_FALLBACK_DESIGN.md` (SEOLB-499) → [doc 21](21-navigation-hints.md)
