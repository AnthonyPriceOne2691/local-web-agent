# 04 — Crawl Orchestrator

> Local Web Agent · Design doc · **v0.8** · 2026-08-06

## Назначение

Управление **agent loop** — не свободный chat, а state machine с лимитами, visited set и deterministic stop conditions. LLM **выбирает among top-K candidates**; оркестратор строит очередь кандидатов (Navigation hints, doc 21) и решает, можно ли выполнить действие (Contract Enforcer).

## State machine (MVP)

```
                    ┌─────────┐
                    │  IDLE   │
                    └────┬────┘
                         │ start_run
                         ▼
                    ┌─────────┐
                    │  INIT   │──── fetch robots.txt, open browser
                    └────┬────┘
                         │
                         ▼
                    ┌─────────┐
         ┌─────────│ OBSERVE │◀──────────────┐
         │         └────┬────┘               │
         │              │ snapshot ready     │
         │              ▼                    │
         │         ┌─────────┐               │
         │         │  PLAN   │──── LLM propose action
         │         └────┬────┘               │
         │              │                    │
         │              ▼                    │
         │         ┌─────────┐               │
         │         │ VALIDATE│──── Contract Enforcer
         │         └────┬────┘               │
         │         reject│                    │
         │              │ accept             │
         │              ▼                    │
         │    ┌─────────────────────┐       │
         │    │ ACT                 │       │
         │    │ navigate | extract  │       │
         │    │ | stop              │       │
         │    └─────────┬───────────┘       │
         │              │                    │
         │     navigate └───────────────────┘
         │     extract  → accumulate snapshot
         │     stop     ▼
         │         ┌─────────────┐
         └────────▶│VISION_BATCH │──── optional VLM batch (doc 23)
                   └──────┬──────┘
                          │
                          ▼
                   ┌─────────┐
                   │SYNTHESIZE│──── R1 extraction pass
                   └────┬────┘
                        │
                        ▼
                   ┌─────────┐
                   │  DONE   │
                   └─────────┘
```

## States — behavior

### IDLE
- Ожидание API/CLI start
- Optional: pre-warm Ollama model (Qwen)

### INIT
- Create run record in SQLite
- Parse crawl config: max_pages, max_depth, allowed_domains
- **Landing domain:** если **первая** навигация редиректит на другой registrable domain (ребрендинг, переезд сайта) — `allowed_domains` деривятся от **финального** URL + заметный log warning; со step 1 действует строгий I-H9 (doc 03 § Redirect policy)
- Classify **task intent** (doc 21)
- Load `data/navigation/path_hints.yaml`
- Fetch robots.txt
- Launch Playwright browser context
- **Homepage-first:** normalize to site root when `normalize_to_root: auto` and task is site-wide (doc 21)
- Navigate to start URL → first OBSERVE; cache **homepage snapshot** for candidate queue

### OBSERVE
- Page Observer → PageSnapshot
- **Screenshot** (if `capture_screenshots` — doc 22): PNG after DOM extract
- **Mark `priority_snapshot`** per rules (doc 23): extract_now target, intent title match, high-score navigate
- Append to run's snapshot list
- Increment `pages_visited`
- Detect blockers (login, captcha) → transition to SYNTHESIZE or DONE with partial result

### PLAN
- Build **CandidateQueue** (P0–P4, doc 21) from current + homepage snapshots + slug probes
- Score links → **top 10** candidates
- Build prompt: task + intent + current snapshot + visited summary + **top-K candidates only**
- Call Qwen instruct → JSON action (url must ∈ candidates)
- Parse via Action Planner

**Context included in PLAN prompt:**
- User task (immutable) + detected `task_intent`
- Current page snapshot (truncated)
- List of visited URLs (titles only, max 10)
- **Top 10 scored candidates** `{href, text, score, reason}` — not raw 40 links
- Remaining budget: `{pages_left}, {depth_left}`

### VALIDATE
- Contract Enforcer checks proposed action
- Reject → log violation → PLAN with rejection reason (max 2 retries) → fallback heuristic

### ACT

| Action | Behavior |
|--------|----------|
| `navigate(url)` | Check not visited; check depth; goto → OBSERVE (+ post-redirect re-check I-H9, doc 13) |
| `extract_now()` | Mark current page **`priority_snapshot: true`** → **сразу назад в PLAN** (без re-OBSERVE, страница не тратит budget повторно); LLM обязан следующим действием выбрать `navigate` или `stop`. **Guard:** 2-й подряд `extract_now` на той же странице → форс `stop` (loop protection, policy #11) |
| `stop(reason)` | Transition to **VISION_BATCH** (if enabled) else SYNTHESIZE |

### VISION_BATCH

- Close Playwright browser (free RAM for VLM)
- Build vision queue from snapshots (doc 23 key pages heuristic)
- For each (page, profile): VisionLoader → VisionAnalyzer → attach `vision_insights[]`
- Evict VLM model
- Transition **SYNTHESIZE**

Skip entirely if `vision_enabled: never` or no screenshots captured.

### SYNTHESIZE
- Load all accumulated snapshots + **vision_insights**
- R1 extraction pass → ExtractionResult
- Save result; transition DONE

### DONE
- Close browser
- Final status: `completed` | `partial` | `failed` | `blocked`

## Deterministic policies (orchestrator-owned, not LLM)

| # | Rule |
|---|------|
| 1 | **Max pages** — hard stop when `pages_visited >= max_pages` |
| 2 | **Max depth = hop depth** — расстояние в **навигационных переходах** от старта (глубина в дереве обхода), **не** сегменты URL-пути: `/blog/2024/03/slug` в один клик с homepage = depth 1; slug probes / sitemap-кандидаты = depth 1. Path-глубина — только сигнал link scorer (+3 за короткий путь). Иначе max_depth=2 отвергал бы статьи UC-2 и sitemap tier |
| 3 | **Visited set** — never revisit same normalized URL |
| 4 | **Same domain** — reject external URLs unless `--allow-external` |
| 5 | **robots.txt** — reject disallowed paths |
| 6 | **Rate limit** — sleep `rate_limit_ms` between navigations |
| 7 | **Blocker pages** — captcha/login → stop with status `blocked` |
| 8 | **No progress** — 3 consecutive pages with no new relevant links → stop |
| 9 | **Early stop** — ≥2 pages with intent match in title/h1 → optional SYNTHESIZE (doc 21) |
| 10 | **Candidate queue order** — localized slugs before budget cut (SEOLB lesson) |
| 11 | **extract_now loop guard** — 2-й подряд extract_now на той же странице → force stop |
| 12 | **Post-redirect check** — финальный URL после goto вне allowed domains → discard snapshot, `redirect_offsite` (I-H9) |
| 13 | **Cancel flag** — проверяется на каждой границе state (FR-3.8); cancel → skip SYNTHESIZE, `status: canceled` |

## Link scoring heuristic

> Полная формула и intent boost — [21-navigation-hints.md](21-navigation-hints.md). Ниже — fallback when LLM fails.

When LLM returns invalid action twice, orchestrator picks next link from **CandidateQueue** (highest score):

```
score(link) =
  +15 if on homepage AND matches intent keywords
  +12 if href matches path_hints slug for intent
  +10 if link.text matches task keywords
  +8  if intent=contact AND legal slug (contact_legal)
  +5  if href path matches keywords
  +3  if shorter path depth
  -8  if legal/cookie path AND intent ≠ contact
  -10 if login/signup/cart/checkout
```

Pick highest score unvisited same-domain link → navigate.

## LLM action schema

```json
{
  "action": "navigate" | "extract_now" | "stop",
  "url": "https://...",           // required if navigate
  "reasoning": "Pricing page likely has enterprise tier",
  "confidence": "high" | "medium" | "low",
  "task_progress": "not_started" | "in_progress" | "likely_complete"
}
```

**Orchestrator ignores** `task_progress: likely_complete` unless action is `stop` or `extract_now` — prevents premature exit without synthesis.

## Run configuration

```yaml
start_url: https://example.com
task: "Find enterprise pricing and contact email for sales"
max_pages: 10
max_depth: 3          # дефолт поднят 2 → 3 (doc 26 § Проверка эталона)
same_domain_only: true
allowed_domains: []          # empty = derive from start_url
rate_limit_ms: 1000
page_timeout_ms: 30000
max_article_candidates: 3         # content_search: не останавливаться на первой статье (doc 21/24)
respect_robots: true
normalize_to_root: auto
use_sitemap: auto                 # doc 21 P2.5 (Phase 2)
consent_handling: auto            # D-11 doc 22: detect→hide→click-reject (Phase 2)
consent_click: reject_first       # reject_first | accept | never
capture_screenshots: auto
screenshot_viewports: all          # design_audit auto; else desktop — doc 22
screenshot_full_page: false
vision_enabled: auto              # doc 23
max_vision_pages: 5
max_vision_calls: 12
vision_profiles: auto             # doc 21 matrix
early_stop_min_pages: 2
```

## Checkpointing

After every ACT:
- Persist `CrawlStep` to SQLite (see doc 12)
- Flush snapshot to disk if > 50 KB cumulative in memory

Crash recovery (P1): resume from last checkpoint — not MVP.

## Реализация: одна стадия — одна функция

`CrawlOrchestrator.run()` собирает контекст и вызывает стадии; сама она решений не
принимает. Состояние прогона живёт в `RunState` (`orchestrator/run_state.py`), исход
шага — в `StepOutcome`:

| Исход | Значение для цикла |
|---|---|
| `CONTINUE` | следующая итерация (новая страница или повторный PLAN) |
| `PROCEED` | дальше по той же итерации (страница уже открыта) |
| `STOP` | выход из цикла к VISION_BATCH/SYNTHESIZE |

| Стадия | Функция | Что решает |
|---|---|---|
| INIT | `_config_allows_run` + `_prepare` | hard-нарушение конфига → отказ до браузера; robots, темп, пробы, sitemap, видимость окна |
| OBSERVE | `_observe_step` → `observe.navigate_and_observe` | переход с ретраем, I-H9 redirect-guard, SPA-fallback, скриншот |
| — | `_handle_blocker` | captcha/login_wall: attended-пауза или `blocked_by` |
| PLAN | `_plan_step` + `_early_stop` | кандидаты, G-S1, решение навигатора с валидацией |
| ACT | `_act_step` → `_repeats_too_often` / `_interact_step` | навигация, extract_now, тиры 1–3, анти-залипание |
| DONE | `finalize.finalize_run` | поля результата, S-*-валидация, `report.md` |

**Почему так, а не одной функцией.** До поставки `orchestrator-complexity`
(2026-08-02) `run()` была на 160 statements и 30 ветвлений: все инварианты прогона
(отмена на границах состояний, ранняя остановка, attended-паузы, тиры действий,
анти-залипание) читались вперемешку, а девять дефектов живого прогона Tier 3
нашлись именно там. Порядок проверок при этом **содержателен** и сохранён:
отмена — на каждой границе состояний (FR-3.8), handoff-ветка — раньше
submit-confirm (doc 25 § Tier 3).

## Testing strategy

| Test type | Cases |
|-----------|-------|
| Unit | State transitions; depth calculation; visited dedup |
| Unit | Link scorer ranking + intent boost |
| Unit | CandidateQueue: localized slugs not truncated by budget |
| Unit | Homepage-first normalization |
| Unit | Max pages enforced at boundary |
| Integration | Mock browser + mock LLM → full loop 3 steps |
| Fixture sites | Static HTML files served locally (no network flake) |

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial crawl orchestrator state machine |
| 2026-07-05 | **v0.2:** hybrid navigation — CandidateQueue, top-K LLM, link scorer from doc 21 (SEOLB ref) |
| 2026-07-05 | **v0.3:** OBSERVE screenshot step (doc 22) |
| 2026-07-05 | **v0.4:** VISION_BATCH state; priority_snapshot; vision config (doc 23) |
| 2026-07-05 | **v0.5 (review):** extract_now семантика определена (назад в PLAN без re-OBSERVE + loop guard #11); policies #12 redirect re-check, #13 cancel flag; config: use_sitemap, dismiss_cookie_banners |
| 2026-07-05 | **v0.6 (review-2):** max_depth = **hop depth**, не path-сегменты (иначе ломались UC-2 и sitemap tier); INIT landing-domain rule (редирект первой навигации переопределяет allowed_domains); max_article_candidates |
| 2026-08-02 | **v0.7:** § Реализация — стадии как функции, `RunState` + `StepOutcome`; поведение не менялось (поставка `orchestrator-complexity`) |
| 2026-08-06 | **v0.8:** дефолт `max_depth` 2 → 3 (doc 26 § Проверка эталона: обучающие статьи на реальных порталах лежат на 2–3 хопах, при 2 путь недостижим по построению) |
