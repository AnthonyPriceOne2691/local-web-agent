# 06 — MVP Phases & Delivery Plan

> Local Web Agent · Design doc · **v0.12.1** · 2026-08-03

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

**Status: ✅ DONE (2026-07-18)** — все deliverables реализованы (96 тестов, coverage: contracts 95–100%, orchestrator ~94%, backend 93%), exit-бенчмарк прогнан на реальных LLM (qwen3:14b single-model + qwen2.5vl:7b vision):

| Task | Результат |
|------|-----------|
| #1 phone (fixture) | ✅ high + цитата, 2 стр., 65 s |
| #2 Pro price (fixture) | ✅ high, 1 стр., 43 s |
| #2b RU-задача (fixture) | ✅ оба аспекта ($29 + enterprise email), 46 s |
| #6 GEO slug `/page/kontak` (fixture) | ✅ через F1-пробу, 2 стр., 85 s |
| **#8 SPA price в CSS (vision)** | ✅ **$49/mo через VISION_BATCH** — DOM не видит, VLM находит, merged `source: vision, medium` (S-H6) |
| #4 playwright.dev (real) | ✅ `…/python/docs/api/…`, high, 3 стр., 90 s |
| #5 ollama.com (real) | ✅ `ollama.com/search` (S-H3c URL-факт), 2 стр., 84 s |
| #3 python.org (real) | ❌ known-fail: intent docs теперь срабатывает и `/dev`-проба в очереди, но LLM уходит в docs.python.org и листает версии; честный not_found. Backlog: аннотация проб интентом, penalty версионных ссылок |

**Формальная пятёрка (#1–#5): 4/5 = 80% — гейт взят.** С #6/#8: 7/8. PLAN p50 **7.9 s ≤ 8 s** чисто (gate doc 20; Phase 0 мерил 10–11 s при фоновом pull); p95 11.6 s (NFR-1.2 цель 10 s — превышение только на real-страницах с тяжёлыми сниппетами, зафиксировано как хвост тюнинга doc 20). Synth max 95.9 s на python.org против 203 s в Phase 0 (−53%). Бенчмарк поймал и починил 3 продовых бага: S-H3b (vision-цитаты резались DOM-проверкой → reclass через token_set_ratio), S-H3c (URL-факты убивались без цитаты → визит = self-evidence, cap medium), флак юнитов от живого fixtures-сервера (autouse-мок проб).

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
2. ✅ 5-task benchmark ≥ **80%** success — 4/5 (таблица выше), 2026-07-18
3. ✅ Every fact has evidence or explicit not_found (S-H2/S-H3 fuzzy + S-G1)
4. ✅ robots.txt respected
5. ✅ All local, no cloud API
6. ✅ Contract Enforcer blocks form submit / external URL
7. ✅ Vision batch: PNG → VLM → merged in ExtractionResult — подтверждён реальным qwen2.5vl (task #8: CSS-цена)

**Engineering exit criteria:**
- [x] Coverage: contracts ≥ 95%, orchestrator ≥ 90%, backend ≥ **85%** (факт: 95–100 / ~94 / 94)
- [x] No files > 500 LOC
- [x] `scripts/check_module_size.py` in CI/local check

---

## Phase 3 — Research Agent (Layer 2)

**Status: ✅ DONE (2026-07-18)** — код + exit-бенчмарк на реальных LLM (qwen3 single-model + qwen2.5vl):

| UC | Результат |
|----|-----------|
| **UC-2** (3 блог-фикстуры, content_completeness) | ✅ winner **blog_alpha 95** > gamma 75 > beta 50 — спроектированный порядок полноты; dimensions по всем сайтам; narrative цитирует конкретику (примеры кэфов, таблица вероятностей, FAQ, банкролл); ~11 мин |
| **UC-1** (4 сайта, design_diff, vision always) | ✅ ComparisonResult + report: 6 рубрик-dimensions × 4 сайта, narrative различает тёмную/светлую схемы и структуру; winner=None (корректно для diff-рубрики); vision 0 сбоев; **~18.5 мин — в 20-минутный бюджет doc 24**; пик RAM Ollama 13 GB, OOM нет |

Бенчмарк поймал и починил: `_host()` без порта (фикстуры на 127.0.0.1:* сливались в один сайт), article-excerpt перепечатывался LLM в output и резался `max_tokens` (теперь excerpt 12K подставляет код из снапшота — S-семантика verbatim гарантирована), невалидный article-блок ронял весь синтез в пустой partial (теперь отбрасывается только блок), word_count-коэрция.

**Deliverables:**
- [x] `ComparisonResult` schema + rubrics (`design_diff`, `content_completeness`, `generic_merge`)
- [x] Compare Synthesizer (synth-модель, wide ctx 24K при N>3; run_id мапит код, выдуманные сайты отбрасываются)
- [x] Meta-agent rules-planner + tools `crawl_site`/`compare_results` (M-H1..M-H4 в раннере; doc 24 v0.4)
- [x] Sequential multi-site queue (D-7) + cooldown (30 s при N≥4) + session timeout 60 min graceful
- [x] Research Session storage (doc 12 v0.6) + startup sweep + session cancel
- [x] `article` extraction block (excerpt 12K заполняет код из снапшота)
- [x] CLI: `agent research --urls ... --task ... --output --report`
- [x] REST: `POST /sessions`, `POST /sessions/{id}/messages`, GET/cancel/DELETE
- [x] UC-1 / UC-2 benchmarks (fixtures: blog_alpha/beta/gamma + pricing/simple_contact)

**Exit criteria:**
- [x] UC-1: 4 URLs design compare → ComparisonResult + report
- [x] UC-2: 3 competitor URLs → correct winner (blog_alpha) with evidence quotes
- [x] No parallel crawls; OOM-free on 32 GB for 4-site queue (пик 13 GB)
- [x] Meta-agent uses only registered tools (M-H1)

---

## Phase 4 — Research Chat UI

**Status: ✅ DONE (2026-07-19)** — UI + SSE + LLM-планнер; exit-прогоны на реальных LLM (qwen3 + qwen2.5vl) **целиком через Chat UI в браузере** (Playwright по собранной статике):

| Прогон из чата | Результат |
|----------------|-----------|
| **UC-2** (3 блог-фикстуры) | ✅ **9.9 мин** (CLI Phase 3: ~11): winner blog_alpha **95** > gamma 70 > beta 40 — порядок Phase 3 воспроизведён; UI: лента + tool-notes, 3 RunCard, Comparison-таб (rankings/dimensions/narrative), Export, report 200 |
| **UC-1** (4 сайта, design_diff, vision) | ✅ **18.1 мин ≤ 20-мин бюджета**: 3/4 сайта в сравнении (5 dimensions, narrative с реальными hex фикстур), 8906 — synth-таймаут 300 s → **excluded[] в UI/отчёте (M-H4 partial отработал вживую)**; 3 скриншот-тумба в RunCard |
| **planner: llm смоук 1** (follow-up без URL) | ✅ вопрос «почему 8902 последний?» → план пуст, reply из comparison-контекста (120 слов, только базовые понятия) |
| **planner: llm смоук 2** (re-crawl + re-compare) | ✅ «сайт на 8906 упал — прогони заново и пересравни» (в сообщении **нет URL**): планнер взял URL из истории, re-crawl ok, re-compare **4/4**: 8907 (88) > 8905 (75) > 8904 (65) > 8906 (50), 6 dimensions |

Фиксы по прогонам: `error_message` больше не пустой при `str(exc)==""` (httpx ReadTimeout → имя типа); stale excluded при re-crawl того же URL убран. 129 тестов.

**Goal:** primary product UX — чат с агентом (doc 24).

**Deliverables:**
- [x] React chat UI + session sidebar (runs, screenshots)
- [x] SSE progress during tool execution (`/sessions/{id}/events` + `crawl_progress` из чекпоинтов store)
- [x] Paste multiple URLs; message history
- [x] Export comparison report from UI (`GET /sessions/{id}/report`)
- [x] `planner: llm` для свободного диалога / follow-up (doc 24 § Planner; rules-планнер остаётся fast-path)

**Exit criteria:**
- [x] UC-1 and UC-2 runnable entirely from chat (2026-07-19, таблица выше)
- [x] No WebSocket required (SSE poll pattern)

**Наблюдения (не блокеры):** (1) synth-таймаут 300 s может ронять отдельный сайт на холодном свопе qwen2.5vl→qwen3 — партиал-семантика отрабатывает, ретрай follow-up'ом через планнер добирает сайт; тюнинг таймаута/промпта — вместе с p95-хвостом doc 20. (2) narrative re-compare может уходить в английский при русском вопросе — язык ответа в compare-промпт (doc 16) при случае.

---

## Phase 6–7 — Action Framework (doc 25)

Фазы после MVP+attended; дизайн, тиры и контракты — [doc 25](25-action-framework.md).

| Phase | Объём | Exit-критерий | Статус |
|-------|-------|---------------|--------|
| **6** | Tier 1 click · Tier 2 login/fill/submit · persist-session · Tier 0 sinks (Google Docs + файл) · Action registry (`research/actions/`, A-H1/A-H2) | сценарий «найди статью → скопируй в Google Docs» из чата; registry: новое действие = модуль + промпт-файл | ✅ **DONE 2026-07-20** (doc 25 v0.9) |
| **7** ✅ | Tier 3 handoff — «агент готовит, человек нажимает» (I-H12 destructive-словарь; `handoff_action` на attended-субстрате; SSE `challenge_wait` +`action`, kind=`handoff`) | референс-сценарий на фикстуре `store_checkout`: fill формы заказа → click «Оплатить заказ» → handoff-пауза → **человек жмёт сам** → «Заказ принят» в результате; unattended destructive → reject | ✅ **DONE 2026-07-30** — живой прогон: `order_number = WX9-1337` зафиксирован после клика человека (doc 25 v1.1) |

## Phase 5+ — Enhancements (backlog)

| Item | Priority | Effort |
|------|----------|--------|
| **Attended-режим (anti-bot challenge, human-in-the-loop)** | ✅ **DONE 2026-07-19** — doc 24 § Attended; видимый браузер + `waiting_user` + resume + SSE `challenge_wait` + Chat UI карточка + CLI `--attended`; 135 тестов |
| Persist `cf_clearance` между сессиями (attended follow-up) | ✅ **DONE 2026-07-20 (Phase 6)** — `storage_state` по хостам в `runs/profiles/<host>.json`, `Settings.persist_session` opt-in; вход/проверка один раз на домен, пока cookie жив. Паролей не храним (doc 25 § persist-session) |
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
| 2026-07-18 | **v0.6: Phase 2 ✅ DONE** — exit-бенчмарк на реальных LLM: 4/5 формальной пятёрки (80%), 7/8 с #6/#8; vision E2E подтверждён (#8 CSS-цена через qwen2.5vl); PLAN p50 7.9 s ≤ 8 s чисто; synth python.org 95.9 s (−53% vs Phase 0). Починены по итогам: S-H3b vision-reclass, S-H3c URL-факты (doc 13 v0.7.1), synthesizer-промпт vision-aware (doc 16), docs-словарь + develop/contribut (doc 21); #3 python.org — known-fail (backlog: аннотация проб) |
| 2026-07-18 | **v0.7: Phase 3 ✅ DONE** — Layer 2 реализован (research/{meta_agent,runner,compare_synthesizer,report}, sessions storage/API/CLI; 115 тестов, cov 93%) и exit-бенчмарк пройден: UC-2 winner blog_alpha 95>75>50 с цитатами (~11 мин), UC-1 4-site design compare + report (~18.5 мин ≤ 20-мин бюджета, vision 0 сбоев, пик RAM 13 GB). Фиксы по бенчмарку: `_host` с портом, article-excerpt заполняет код (не LLM-перепечатка), устойчивость синтеза к невалидному article-блоку. Next: Phase 4 Chat UI |
| 2026-07-19 | **v0.8: Phase 4 CODE COMPLETE** — Chat UI (`frontend/`: React 19 + Vite 7 + TS + Tailwind v4, три колонки: sidebar/чат/side panel) + бэкенд: SSE `/sessions/{id}/events` (poll-паттерн, doc 15 v0.6), `GET /sessions/{id}/report`, `GET /runs/{id}/steps/{pos}/screenshot`, статика `frontend/dist` с FastAPI (same-origin). 120 тестов. Остаток: UC-1/UC-2 exit из чата (реальные LLM) + `planner: llm` |
| 2026-07-19 | **v0.10: Phase 5 attended-режим** — human-in-the-loop прохождение anti-bot challenge (doc 24 § Attended-режим): видимый браузер, статус `waiting_user`, resume-эндпоинты, SSE `challenge_wait`, Chat UI карточка-пауза + тумблер, CLI `--attended`; D-12 lock учитывает `waiting_user`; 135 тестов. Fingerprint-спуфинг/обход детекта — вне scope навсегда (контракт no anti-bot bypass) |
| 2026-07-19 | **v0.9: Phase 4 ✅ DONE** — `planner: llm` реализован (`research/llm_planner.py`, doc 24 v0.6: rules fast-path + LLM для диалога, M-H1..M-H3 пост-валидация) и exit-прогоны пройдены целиком из Chat UI в браузере: UC-2 9.9 мин (winner 95>70>40), UC-1 18.1 мин (partial M-H4 вживую: 8906 synth-таймаут → excluded, затем добран follow-up'ом через планнер до 4/4: 88/75/65/50). Фиксы: error_message при пустом str(exc), stale excluded при re-crawl. 129 тестов |
| 2026-07-20 | **v0.11: секция Phase 6–7 Action Framework** (объёмы/exit-критерии, дизайн в doc 25): Phase 6 ✅ DONE (Tier 0/1/2 + persist + registry, doc 25 v0.9), Phase 7 Tier 3 handoff 🛠 (I-H12 + `handoff_action`, референс `store_checkout`, doc 25 v1.0) |
| 2026-08-03 | **v0.12.1:** § Phase 5+ — строка «Persist `cf_clearance` между сессиями» помечена сделанной: persist-session реализован в Phase 6 (`storage_state` по хостам, opt-in), а в бэклоге оставался P2 |
| 2026-07-30 | **v0.12: Phase 7 ✅ DONE** — Tier 3 handoff подтверждён живым exit-прогоном на фикстуре `store_checkout`: `fill_form` → выбор «Оплатить заказ» → пауза `handoff` → человек нажал → агент зафиксировал `WX9-1337`. Девять дефектов, найденных прогоном (значения полей в снапшоте, batch-fill, режимные пометки элементов, формулировка выбора, прогрев модели, окно браузера, устойчивость к закрытию, один необратимый шаг за прогон) — исправлены, doc 25 v1.1. 200 тестов |
