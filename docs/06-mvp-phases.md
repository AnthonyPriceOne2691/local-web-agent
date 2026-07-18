# 06 — MVP Phases & Delivery Plan

> Local Web Agent · Design doc · **v0.5** · 2026-07-18

## Engineering standards (все фазы)

С **Phase 1** — обязательны правила из **[18-engineering-standards.md](18-engineering-standards.md)**:

| Правило | Суть |
|---------|------|
| **≤ 500 LOC** | Любой файл в `backend/app/`, `cli/` |
| **SOLID** | Browser/LLM/Store за Protocols; DI |
| **DRY** | Prompts/contracts в `data/` |
| **Тесты** | Mocks для Playwright и Ollama |

**Phase 0** — только spike-скрипты в `scripts/spike/`.

## Phase overview

```
Phase 0       Phase 1–2         Phase 3              Phase 4
Benchmark ──▶ Crawl Worker ──▶ Research CLI    ──▶  Chat UI
(1–2 days)    Layer 1 MVP       + compare            (primary UX)
              (4–6 + 5–7 days)  (5–7 days)
```

## Phase 0 — Benchmark & spike

**Status: 🔲 NEXT**

**Goal:** доказать, что Playwright + local LLM на M5 находит ответ на типовой задаче с приемлемым временем и качеством.

**Deliverables:**
- [ ] Script: `scripts/spike/benchmark_crawl.py` — one URL, one task, manual task list
- [ ] Script: `scripts/spike/benchmark_vision.py` — fixture PNG → VLM (doc 19 § Vision)
- [ ] Measured: pages visited, wall time, extraction quality (manual rubric)
- [ ] Test sites: 3 static/local fixtures + 2 real public sites
- [ ] `docs/19-phase0-benchmark-results.md` filled

**Test tasks (suggested):**

| # | Site type | Task |
|---|-----------|------|
| 1 | Local fixture | Find phone number on contact page |
| 2 | Local fixture | Find product price on pricing page |
| 3 | Real (simple corporate) | Find company HQ city |
| 4 | Real (SPA-ish) | Find documentation link for API |
| 5 | Real | Find careers / jobs page URL |
| 6 | Local fixture (GEO slug) | Find contact via `/page/kontak` or `/kontak` only |
| 7 | A/B | Same tasks: **hints+LLM** vs **LLM-only** (doc 21) |
| 8 | Fixture SPA (empty DOM) | Find price — **DOM-only vs DOM+vision** (doc 19 § Vision) |
| 9 | Vision spike | 5 fixture PNGs → qwen2.5vl:7b rubric (doc 19 § Vision) |
| 10 | Nav model A/B | Tasks 1–6 на `qwen2.5:14b` vs **`qwen3:14b` (think off)** vs `gpt-oss:20b` (doc 14 § A/B) — одинаковый скрипт, разный `--model` |
| 11 | Sustained / thermal | 3 прогона подряд (fanless Air): run 3 vs run 1 latency degradation |

**Exit criteria:**
- [ ] ≥ **3/5** tasks: correct answer + evidence (baseline)
- [ ] A/B: hints mode **≤ pages** and **≥ success** vs LLM-only on task #6
- [ ] Vision spike: **≥ 4/5** fixture PNGs pass rubric; VLM p95 **≤ 20 s**; valid JSON **≥ 95%** (doc 19)
- [ ] Task #8: DOM+vision **≥** DOM-only success on SPA fixture (or tie + richer design fields)
- [ ] Task #10: winner зафиксирован в doc 19 → закрывает D-2 окончательно (single-model qwen3 = бонус: минус своп)
- [ ] Task #11: run 3 latency ≤ **1.5×** run 1 (иначе — cooldown-политика в doc 24 обязательна)
- [ ] Average **≤ 8 pages** per successful run
- [ ] Average wall time **≤ 5 min** per run
- [ ] Navigation step **≤ 8 s p50 / ≤ 10 s p95** warm (NFR-1.2)
- [ ] No OOM on 32 GB during browser + 14B model

**No app code required** — только scripts.

---

## Phase 1 — Minimal agent loop

**Status: ✅ DONE (2026-07-18)** — все deliverables и exit-критерии закрыты: `backend/app/` (10 модулей, 30 тестов, coverage **87%**, ruff clean, все файлы ≤ 500 LOC), `cli/`, `data/prompts/`; E2E 3/3 на fixture-сервере (в т.ч. RU-задача и несвязанный GEO-слаг), 0 контрактных нарушений. Сверх плана (перенесено из Phase 2 по итогам Phase 0): I-H8/I-H9 guards, F1-lite HTTP-фильтр проб, robots+Crawl-delay, startup sweep, SPA-fallback screenshot.

**Goal:** end-to-end без full contracts — «naive agent»: observe → LLM → navigate loop → final extract.

**Deliverables:**
- [ ] FastAPI: `/health`, `POST /runs`, `GET /runs/{id}`
- [ ] Playwright integration (single session)
- [ ] Page Observer (DOM snapshot + **screenshot PNG**, doc 22)
- [ ] Navigation hints: intent + `path_hints.yaml` + CandidateQueue + link_scorer (doc 21)
- [ ] Ollama Qwen — navigation JSON (top-K candidates only)
- [ ] Ollama R1 — final ExtractionResult
- [ ] Basic orchestrator (max pages, visited set — hardcoded limits)
- [ ] **Global run lock** (NFR-4.4 / D-12): второй POST /runs → 409
- [ ] Минимальные hard checks в orchestrator: I-H1, I-H6, **I-H8/I-H9** (private network, redirect re-check — doc 13)
- [ ] CLI: `agent crawl --url --task`
- [ ] JSON output to stdout + `data/runs/{id}.json`
- [ ] Page screenshots → `artifacts/{run_id}/screenshots/` (doc 22, `--screenshots`)

**Exit criteria:**
- [ ] **3 manual crawls** on fixture server without crash
- [ ] Step log persisted (JSON file minimum)
- [ ] ExtractionResult validates against Pydantic schema
- [ ] Unit tests: observer truncation, action parser, orchestrator transitions (mocks)
- [ ] Coverage `backend/app/` ≥ **70%**

---

## Phase 2 — Full MVP

**Status: 🟡 CODE COMPLETE (2026-07-18)** — все deliverables реализованы и покрыты юнитами (93 теста, coverage: contracts 95–100%, orchestrator ~94%, backend 94%). До закрытия фазы — ручные exit-прогоны с реальными LLM: 5-task benchmark (см. ниже), E2E на fixture-сервере, re-check PLAN p50 (gate doc 20).

**Goal:** production-quality solo tool — contracts, SQLite, robots.txt, reports.

**Deliverables:**
- [x] Contract Enforcer (ABC arXiv:2602.22302) + `data/contracts/crawl.contract.yaml` + `synthesis.contract.yaml` + `vision.contract.yaml` (doc 13 v0.7)
- [x] robots.txt integration (Phase 1) + `Sitemap:`-директивы + G-H5 в PLAN-shield
- [x] SQLite run store (doc 12 v0.5) + legacy-импорт + `runs delete`
- [x] Link scoring fallback (doc 21) + drift auto-tighten (doc 13 § Drift)
- [x] Early stop heuristics (G-S1: 3 страницы без новых релевантных ссылок)
- [x] HTTP probe tier F1 полный (GET 500 KB cap, links → queue) + escalate-маркер F2 (doc 03)
- [x] Blocker detection (login, captcha) — Phase 1
- [x] VisionLoader + VisionAnalyzer → `vision_insights` (doc 23); `--vision auto|always|never`
- [x] **Sitemap tier P2.5** (doc 21) — `use_sitemap`, фильтр по intent, top-20
- [x] **Cookie-banner dismissal** detect→hide→click reject-first (D-11, doc 22)
- [x] **Cancel run** (`POST /runs/{id}/cancel`, `agent runs cancel` — FR-3.8)
- [x] Markdown report export (`artifacts/{id}/report.md`, doc 05)
- [x] `agent runs list` / `agent runs show` (Phase 1) + `runs cancel` / `runs delete`
- [x] Rate limiting (G-H4 floor, private exempt) + configurable max depth + `--allow-private`
- [x] Checkpoint per step (save в SQLite на каждом шаге)

**Exit criteria (MVP definition of done):**
1. ✅ CLI crawl with full guardrails
2. 🔲 5-task benchmark ≥ **80%** success (reuse Phase 0 suite) — **ручной прогон с реальными LLM**
3. ✅ Every fact has evidence or explicit not_found (S-H2/S-H3 fuzzy + S-G1)
4. ✅ robots.txt respected
5. ✅ All local, no cloud API
6. ✅ Contract Enforcer blocks form submit / external URL
7. ✅ Vision batch: PNG → VLM → merged in ExtractionResult (mock-tested; real VLM — в ручном прогоне)

**Engineering exit criteria:**
- [x] Coverage: contracts ≥ 95%, orchestrator ≥ 90%, backend ≥ **85%** (факт: 95–100 / ~94 / 94)
- [x] No files > 500 LOC
- [x] `scripts/check_module_size.py` in CI/local check

---

## Phase 3 — Research Agent (Layer 2)

**Goal:** multi-site tasks из doc 24 — `agent research`, compare synthesis, sessions.

**Deliverables:**
- [ ] `ComparisonResult` schema + rubrics (`design_diff`, `content_completeness`)
- [ ] Compare Synthesizer (R1)
- [ ] Meta-agent + tool registry (`crawl_site`, `compare_results`, `get_run_result`)
- [ ] Sequential multi-site queue (D-7)
- [ ] Research Session storage (doc 12)
- [ ] `article` extraction block in ExtractionResult
- [ ] CLI: `agent research --urls ... --task "..."`
- [ ] REST: `POST /sessions`, `POST /sessions/{id}/messages`
- [ ] UC-1 benchmark: 2 fixture sites design compare
- [ ] UC-2 benchmark: 2 fixture blogs football article compare

**Exit criteria:**
- [ ] UC-1: 4 URLs design compare → ComparisonResult + report
- [ ] UC-2: 3 competitor URLs → correct winner with evidence quotes
- [ ] No parallel crawls; OOM-free on 32 GB for 4-site queue
- [ ] Meta-agent uses only registered tools (M-H1)

---

## Phase 4 — Research Chat UI

**Goal:** primary product UX — чат с агентом (doc 24).

**Deliverables:**
- [ ] React chat UI + session sidebar (runs, screenshots)
- [ ] SSE progress during tool execution
- [ ] Paste multiple URLs; message history
- [ ] Export comparison report from UI

**Exit criteria:**
- [ ] UC-1 and UC-2 runnable entirely from chat
- [ ] No WebSocket required (SSE poll pattern)

---

## Phase 5+ — Enhancements (backlog)

| Item | Priority | Effort |
|------|----------|--------|
| Screenshot gallery in Web UI | P2 | S |
| Structured schema input (`--schema`) | P1 | S |
| Regex assist pre-pass | P1 | S |
| **Phase-batched multi-site execution** (doc 24: 12 swaps → 3) | P1 | M |
| RSS feed source для content_search (doc 21) | P2 | S |
| Site-search probe `/?s=` (doc 21; нужен contract carve-out) | P2 | S |
| Cross-domain allowlist UI | P2 | S |
| Resume crashed run | P2 | M |
| Parallel tabs (same domain) | P2 | L |
| Auto-scroll для full_page + lazy-load (doc 22) | P2 | S |
| `agent runs prune --keep N` (retention) | P3 | S |
| Scheduled / batch crawls | P3 | M |
| Export CSV / Obsidian | P3 | S |
| Cloud LLM fallback (opt-in) | P3 | M |

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Local 14B too weak for navigation | Wrong links, no answer | Link scorer fallback; benchmark gate Phase 0; **A/B qwen3/gpt-oss (task #10)** |
| SPA sites empty DOM | Miss content | networkidle wait; **vision batch** (doc 23); SPA fallback capture (doc 03) |
| Anti-bot blocks headless | Runs fail | Detect + stop; no bypass; disclaimer |
| **Cookie/consent walls закрывают скриншоты** | **UC-1 design audit деградирует на EU-сайтах** | **D-11: best_effort dismissal Phase 2 (doc 22); vision `obstructed` детект** |
| Context overflow on large pages | Truncation loses info | doc 20 budget; prioritize headings + links; **non-Latin: токены считать по факту (doc 20)** |
| Hallucinated facts | Bad output | Evidence required; confidence rules; R1 for synthesis; **structured outputs (doc 16)** |
| Thermal throttle on Air (fanless) | Slow mid-run; multi-site session деградирует | Sequential pages; one model loaded; **Phase 0 task #11 замер; cooldown 30–60 s при N≥4 (doc 24)** |
| **Model swap overhead multi-site** | +1.5–3 min на 4-site сессию | keep_alive mechanics (doc 14); phase-batched execution (backlog) |
| Legal / ToS | User liability | CLI disclaimer; robots.txt default |
| Scope creep | Never ship | Phase gates; Layer 2 after Layer 1 exit |
| Multi-site OOM | 4+ sites queue fails | Strict sequential; browser closed between sites; **global run lock (D-12)** |
| Compare quality weak | Wrong winner UC-2 | Rubric in prompt; article excerpt budget 12K; **articles недостижимы без sitemap (P2.5, doc 21)** |

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial phased plan |
| 2026-07-05 | Phase 2: Contract Enforcer привязан к ABC arXiv:2602.22302 |
| 2026-07-05 | Navigation hints (doc 21) в Phase 1; Phase 0 benchmark +1; HTTP F1 в Phase 2 |
| 2026-07-05 | Vision analysis (doc 23) → Phase 2; removed from Phase 3 backlog |
| 2026-07-05 | Phase 0: vision spike script + tasks #8–9; exit criteria (doc 19) |
| 2026-07-05 | **v0.3:** Phase 3 Research Agent (doc 24); Phase 4 Chat UI; Phase 5+ backlog |
| 2026-07-05 | **v0.4 (review):** Phase 0 tasks #10 (nav model A/B) + #11 (sustained/thermal); Phase 1 + run lock и I-H8/I-H9; Phase 2 + sitemap/cookie-dismiss/cancel; риски: cookie walls, swap overhead, thermal; backlog: phase-batched, RSS, prune |
| 2026-07-18 | **v0.5:** Phase 2 CODE COMPLETE — все deliverables реализованы (SQLite v0.5, enforcer v0.7 + drift, S-H3 fuzzy, cancel, sitemap P2.5, F1 полный, early stop G-S1, cookie-dismiss D-11, vision batch, markdown report, --allow-private); engineering exit взят (93 теста, cov 94%); осталось: ручные exit-прогоны с реальными LLM (5-task benchmark, E2E fixtures, PLAN p50 doc 20) |
