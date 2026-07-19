# 24 — Research Chat Agent (multi-site + compare)

> Local Web Agent · Design doc · **v0.7** · 2026-07-19

## Назначение

**Целевой UX продукта:** чат с агентом, куда пользователь кидает **один или несколько URL** и формулирует задачу на естественном языке. Агент **сам выбирает инструменты** (crawl, vision, compare), заходит на сайты, делает скрины при необходимости и возвращает **сводный ответ** — в т.ч. сравнительный («чем отличаются», «у кого полнее»).

**Не заменяет** crawl orchestrator (doc 04) — **оркестрирует** его как tool.

---

## Два слоя архитектуры

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 2 — Research Chat Agent (этот doc)                   │
│  Chat UI / CLI research  →  Meta-Agent  →  Compare Synth    │
└───────────────────────────────┬─────────────────────────────┘
                                │ tool calls
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 — Crawl Worker (docs 03–05, 21–23)                 │
│  crawl_site → browser → vision batch → ExtractionResult     │
└─────────────────────────────────────────────────────────────┘
```

| Слой | Отвечает на |
|------|-------------|
| **Layer 1** | «Что на этом сайте по sub-task?» |
| **Layer 2** | «Как разбить user message? Какие сайты? Как сравнить? Что ответить в чат?» |

**Инвариант:** chat-loop и crawl state machine **разделены**. ABC-контракты (doc 13) применяются только в Layer 1.

---

## Целевые сценарии (зафиксировано)

### UC-1: Comparative design audit

**User message (пример):**

> Вот 4 сайта: a.com, b.com, c.com, d.com — пройди по каждому и опиши дизайн, чем они отличаются друг от друга.

**Meta-agent plan:**

1. Parse URLs (1–N) + detect `research_intent = comparative_design`
2. For each URL **sequentially** (D-7):
   - `crawl_site(url, sub_task="Design audit: colors, layout, typography, mobile", intent=design_audit, max_pages=6)`
3. `compare_results(run_ids, rubric=design_diff)`
4. Reply in chat: per-site summary + diff table + narrative conclusion
5. Attach `comparison_report.md` in session artifacts

> **max_pages=6 для comparative_design** (не default 10): для сравнения дизайна хватает homepage + 3–5 ключевых страниц; 10 страниц × 3 viewport × vision на 4 сайтах не влезает в 20-минутный бюджет UC-1 (см. § Session time budget).

### UC-2: Competitive content analysis

**User message (пример):**

> Список конкурентов: x.com, y.com, z.com — найди статью про ставки на футбол, просмотри и скажи у кого самая полная статья и почему.

**Meta-agent plan:**

1. `research_intent = comparative_content`
2. For each URL sequentially:
   - `crawl_site(url, sub_task="Find the best article about football betting", intent=content_search, max_pages=12)`
   - Собрать до **3 статей-кандидатов** (`max_article_candidates`, doc 21) — **не** останавливаться на первой: вопрос «у кого самая полная», synthesis выбирает лучшую per site
3. `compare_results(run_ids, rubric=content_completeness)`
4. Reply: winner + rubric scores + quotes per site

---

## Research Session

Контейнер чата и связанных crawl runs.

```json
{
  "session_id": "uuid",
  "title": "Design compare: 4 competitors",
  "status": "active",
  "messages": [],
  "run_ids": ["run-a", "run-b"],
  "comparison_result": null,
  "created_at": "2026-07-05T..."
}
```

**Storage:** doc 12 — таблицы `research_sessions`, `session_messages`, FK `crawl_runs.session_id`.

**Lifecycle:** `active` → `running_tools` → `comparing` → `completed` | `failed`

---

## Meta-Agent

**Модуль:** `backend/app/research/meta_agent.py`  
**Model:** `qwen2.5:14b-instruct` (tool planning) — не R1; R1 только для structured compare output.

### Planner: rules fast-path + LLM для диалога (Phase 4 — реализовано)

Для фиксированных research intents план **полностью детерминирован** (URLs → intent → N × crawl_site → compare) — LLM-планирование здесь лишняя поверхность отказа (ещё один JSON-парсинг + контракты M-*). Поэтому:

| Mode | Когда | Что делает |
|------|-------|------------|
| rules fast-path (**всегда**, если в сообщении есть URL) | intent распознан по keywords + URLs распарсены regex'ом | План строится кодом по таблице research intents; LLM не вызывается до compare |
| `planner: llm` (**default**, Phase 4; `LWA_PLANNER=rules` отключает) | сообщение **без URL**: follow-up вопросы, re-compare по другой рубрике, «что уже сделано», замена/повтор сайта | `research/llm_planner.py`: meta-промпт (`data/prompts/meta_planner_*`) поверх nav-модели (qwen3 `think:false`, structured output) → `{"plan": [...], "reply": "..."}`; пустой план → reply прямо в чат |

**Пост-валидация LLM-плана (M-H1..M-H3, в `llm_planner._enforce`):** только известные tools; `crawl_site.url` — строго из ALLOWED URLS (текущее сообщение + прошлые user-сообщения сессии), выдуманный URL отбрасывается; `run_id` — только из runs сессии; рубрика вне списка → `generic_merge`; crawl'ов ≤ `max_sites` (M-H2), `max_pages` clamp ≤ 12; `compare_results` — максимум один и последним. Невалидный JSON от LLM → фоллбек-reply с просьбой уточнить (сессия не падает). В llm-пути runner'а действуют те же session-контракты, что и в rules: cooldown между crawl'ами, session time budget, M-S1 tool-notes, M-H4 в compare.

`agent research` CLI работает **целиком на rules** (URL передаются флагом — fast-path); LLM-планнер включается только в свободном диалоге Chat UI.

### Responsibilities

| Step | Behavior |
|------|----------|
| Parse user message | Extract URLs (regex + optional LLM cleanup), detect research_intent |
| Plan | Ordered tool calls; no parallel crawls on M5 |
| Execute | Invoke tools; stream progress events to chat |
| Summarize | Short chat reply; link full report |

### Research intents

| Intent | Triggers (keywords) | Per-site crawl defaults | Compare rubric |
|--------|---------------------|---------------------------|----------------|
| `comparative_design` | design, layout, colors, compare sites, отличия | `design_audit` matrix (doc 21) | `design_diff` |
| `comparative_content` | article, blog, найди текст, полнее, конкурент | `content_search` (doc 21) | `content_completeness` |
| `multi_site_research` | list of URLs + generic task | inherit from sub-task keywords | `generic_merge` |
| `single_site` | one URL | delegate directly to Layer 1; no compare | — |

If one URL only → **skip meta compare**; answer from single `ExtractionResult`.

---

## Tool registry

Meta-agent вызывает **только** эти tools (typed, validated):

### `crawl_site`

```json
{
  "name": "crawl_site",
  "arguments": {
    "url": "https://example.com",
    "task": "Design audit homepage and key pages",
    "intent": "design_audit",
    "max_pages": 10,
    "max_depth": 2,
    "vision_enabled": "auto",
    "capture_screenshots": "auto"
  }
}
```

**Returns:** `{ "run_id": "...", "status": "completed", "summary": "..." }`

Implementation: enqueue existing `POST /runs` pipeline; block until done (sequential queue).

### `get_run_result`

```json
{ "run_id": "...", "include": ["facts", "design_tokens", "article", "vision_insights"] }
```

**Returns:** subset of `ExtractionResult` + artifact paths.

### `compare_results`

```json
{
  "run_ids": ["...", "..."],
  "comparison_task": "How do these sites differ in design?",
  "rubric": "design_diff"
}
```

**Returns:** `ComparisonResult` (doc 05). Invokes **Compare Synthesizer** (R1).

### `list_session_runs`

Returns run_ids + status for current session (recovery / user ask «что уже сделано»).

> Phase 4: `get_run_result` / `list_session_runs` доступны **LLM-планнеру** (ответ собирается кодом из store — `runner._run_details` / `_runs_listing`); rules-путь их по-прежнему не использует. `compare_results` в LLM-плане принимает `run_ids` прошлых runs сессии (re-compare без нового crawl).

**Hard rule:** meta-agent **cannot** call Playwright or load arbitrary paths — only tools.

---

## Compare Synthesizer

**Модуль:** `backend/app/research/compare_synthesizer.py`  
**Model:** `deepseek-r1:14b`  
**Input:** N × `ExtractionResult` (truncated per doc 20) + comparison_task + rubric template  
**Output:** `ComparisonResult`

### Rubrics (data/prompts/rubrics/)

| Rubric ID | Used for | Dimensions |
|-----------|----------|------------|
| `design_diff` | UC-1 | colors, typography, layout, components, mobile vs desktop, brand feel |
| `content_completeness` | UC-2 | word count, sections/FAQ, data/examples, structure, freshness signals |
| `generic_merge` | multi_site_research | task-specific free-form |

### Compare pass (not per-site crawl)

```
All crawl runs done (sequential)
  → load ExtractionResults
  → build compare prompt (doc 16 compare_*)
  → R1 → ComparisonResult
  → store in session.comparison_result
  → meta-agent formats chat reply
```

---

## Article extraction mode (UC-2)

When crawl finds candidate article page:

| Signal | Action |
|--------|--------|
| URL path matches `/blog/`, `/article/`, `/news/`, `/guides/` + task keywords in title/h1 | `page_type: article` |
| LLM `extract_now` on long main_text page | `priority_snapshot: true` |
| Article found | Продолжать до `max_article_candidates: 3` (doc 21 § article candidates) |
| Synthesis | R1 выбирает лучшую из кандидатов → `article` block; остальные в `article_candidates_considered[]` (doc 05) |

**Article block:** `url`, `title`, `word_count`, `headings[]`, `main_text_excerpt` (up to **12000 chars** for compare — doc 20 extension), `published_date` if visible.

---

## Attended-режим — anti-bot challenge (Phase 5, реализовано 2026-07-19)

**Проблема:** сайты за активным Cloudflare managed challenge (403 + «just a moment» на каждый запрос, включая robots.txt) headless-агент не читает — и не должен обходить (контракт: no anti-bot bypass). Но контент доступен человеку, прошедшему проверку.

**Решение — human-in-the-loop, НЕ обход детекта.** Проверку проходит пользователь в видимом браузере; агент делает всё остальное. Fingerprint-спуфинг / автопрохождение challenge / solver-сервисы **вне scope навсегда** — они подделывают сигнал «я человек», что и запрещено.

| Шаг | Поведение |
|-----|-----------|
| Детект challenge | `observer/blockers.detect_status` → `captcha` (сигналы `cloudflare` / `checking your browser` / `cf-browser-verification` …) |
| attended off (default) | как Phase 2: `captcha` → `blocked` сразу |
| attended on | run → `waiting_user`, `metadata.challenge = {url, kind}`; браузер видимый (`headless=False`); ждём resume до `attended_wait_timeout_s` (300 s) |
| resume | пользователь прошёл проверку → `POST /sessions/{id}/resume` (или `/runs/{id}/resume`) → challenge-снапшот выброшен, страница переобсёрвивается (DOM настоящий), `cf_clearance`-cookie живёт в контексте run'а |
| timeout | не дождались → `blocked_by=captcha`, `challenge_timeout=True` → сайт в `excluded[]` (M-H4) |

**Реализация:** `orchestrator/attended.py` (`AttendedGate` Protocol + `EventAttendedGate` — пауза/resume/сброс, вынесено из loop.py ради ≤500 LOC); одна развилка на границе OBSERVE в `loop.py`; `EventAttendedGate` создаётся в `routes_runs` / `ResearchRunner` из `resume_event` (по образцу cancel_event). **D-12:** `active_run_id`/`startup_sweep` считают `waiting_user` занятым слотом (браузер открыт, лок держится; после рестарта — zombie → failed).

**SSE:** событие `challenge_wait {run_id, start_url, url, kind}` пока активный run сессии в `waiting_user` (doc 15). **Chat UI:** карточка-пауза с кнопкой «✓ Я прошёл — продолжить», тумблер «Attended-режим» при старте сессии (`ChallengeCard` в `Chat.tsx`).

**Пределы (честно):** `cf_clearance` привязан к IP+браузеру и живёт ограниченно — на длинной сессии challenge всплывёт снова; на N доменов за стенкой — N ручных прохождений. Снимает рутину обхода страниц, не сам факт проверки. Видимый браузер требует, чтобы агент и пользователь были на одной машине (для локального privacy-first инструмента — всегда так).

**Подтверждено вживую (2026-07-19, redib.org за CF managed challenge):** headless давал 403 + 0 страниц; attended headful — пауза `waiting_user` → пользователь прошёл проверку **один раз** → контент прочитан (`completed`, PT-страница про букмекеров). Баги, пойманные на живом Cloudflare и починенные:
- **OBSERVE падал** `Execution context was destroyed` — CF дёргает challenge-страницу редиректами; `raw_snapshot` теперь ретраит с ожиданием (`playwright_session`).
- **captcha не распознавалась** — детектор знал только «checking your browser»; добавлены актуальные CF-формулировки («just a moment», «enable javascript and cookies», «verifying you are human», …). Плюс **thin-guard**: сигнал засчитывается только в `title` или на «тонкой» странице-заглушке — иначе встроенный Turnstile-виджет на реальной контентной странице давал ложную паузу.
- **SPA-fallback давал challenge «проскочить»** — его networkidle-ожидание пропускаем на challenge-странице (`looks_like_challenge`), чтобы пауза была детерминированной.
- **две галочки** — после resume агент делал повторный `goto`, и CF показывал проверку ещё раз; теперь `reobserve_in_place` читает уже открытую пользователем страницу **без новой навигации** (`browser.page_url()`).

## Multi-site execution (D-7 closed)

| Rule | Value |
|------|-------|
| Parallel crawls | **❌ never** on M5 32 GB |
| Queue | Strict FIFO per session |
| Max sites per message | **10** default (`max_sites_per_session`) |
| Cooldown between sites | `site_cooldown_s: 2` default; **30–60 s при N ≥ 4** (fanless Air — thermal, см. риски doc 06) |
| Cross-domain | **✅ allowed** — each crawl has own domain scope |

User batch of 4 URLs → 4 sequential runs → 1 compare pass.

### Partial failure (M-H4 edge)

Один из сайтов blocked/failed — сессия **не** падает:

| Completed runs | Behavior |
|----------------|----------|
| ≥ 2 | Compare по выжившим; провалившиеся → `ComparisonResult.excluded[]` `{start_url, reason}`; в chat reply и отчёте — явное «site X исключён: captcha» |
| 1 | No compare; ответ из единственного ExtractionResult + список excluded |
| 0 | Session `failed`; в reply — per-site причины |

Blocked-сайт **не** ретраится автоматически (no bypass); пользователь может прислать замену follow-up сообщением (Phase 4).

### Session limits

| Param | Default | Why |
|-------|---------|-----|
| `max_sites_per_session` | 10 | M-H2 |
| `max_session_duration_min` | **60** | 10-сайтовая сессия на fanless Air — иначе не ограничена ничем; по таймеру — graceful: текущий crawl cancel, compare по завершённым (как partial failure) |

### Session time budget & model swaps (4-site UC-1, реалистичная математика)

Naive-последовательность (per-site: Qwen → VLM → R1) даёт **до 12 model swap'ов** на сессию:

| Статья | Оценка |
|--------|--------|
| Crawl per site (6 стр. × 8–12 s) | ~1–1.5 min |
| Vision per site (≤ 12 calls × 5–15 s) | ~1.5–3 min |
| Synthesis per site | ~1 min |
| Model swaps: 4 × (Qwen→VLM→R1) ≈ 12 загрузок × 5–15 s | **+1.5–3 min** |
| COMPARE + reply | ~1.5 min |
| **Итого 4 сайта** | **~17–26 min** — 20-минутная цель UC-1 достижима только с max_pages=6 |

### Phase-batched execution (Phase 5 optimization, backlog)

Свопы сокращаются с ~12 до **3**, если группировать фазы не по сайту, а по модели:

```
crawl(site1..4)   — Qwen загружен один раз; snapshots на диск
vision(site1..4)  — VLM загружен один раз
synth(site1..4) + compare — R1 загружен один раз
```

Экономия ~1.5–3 min + меньше thermal-пиков. Цена: `crawl_site` перестаёт возвращать готовый summary (synthesis отложен) — меняется семантика tool'а, поэтому **не в Phase 3 MVP**; фиксируем как backlog-оптимизацию.

---

## API & CLI

### REST (Phase 3)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/sessions` | Create research session |
| POST | `/sessions/{id}/messages` | User message → meta-agent run |
| GET | `/sessions/{id}` | Session + messages + runs + comparison |
| GET | `/sessions/{id}/events` | SSE: tool progress |

### CLI (Phase 3, before Chat UI)

```bash
agent research \
  --urls "https://a.com,https://b.com,https://c.com,https://d.com" \
  --task "Describe design of each site and how they differ" \
  --output comparison.json \
  --report comparison.md
```

Equivalent to one user chat message without UI.

---

## Chat UI (Phase 4 — primary product UX)

**Статус:** **реализован (2026-07-19)** — `frontend/` React 19 + Vite 7 + TS + Tailwind v4; структура компонентов и layout — doc 17 v0.4; SSE-протокол — doc 15 v0.6 (события `status`/`message`/`crawl_progress`/`done`, poll-паттерн поверх store, реконнект `?since_messages=N`). Экспорт отчёта — `GET /sessions/{id}/report`. Остаток Phase 4: exit-прогон UC-1/UC-2 из чата на реальных LLM + `planner: llm` для свободного диалога (rules-планнер пока единственный).

```
┌──────────────────────────────────────────────┐
│ Research Chat                          [+]   │
├──────────────────────────────────────────────┤
│ You: 4 sites … describe design …             │
│                                              │
│ Agent: Running design audit (1/4) a.com…     │
│        [████████░░░░] site 2/4               │
│                                              │
│ Agent: Summary + table + Open full report    │
├──────────────────────────────────────────────┤
│ [ Paste URLs or type task…          ] [Send] │
└──────────────────────────────────────────────┘
```

Side panel: run timeline, screenshots, comparison table.

Tech: React + Vite; SSE from `/sessions/{id}/events`; pattern ref Voice Interview Coach chat.

---

## Phase mapping

| Item | Phase |
|------|-------|
| Layer 1 single-site crawl | 1–2 |
| `ComparisonResult` schema + rubrics | **3** |
| `agent research` CLI + meta-agent tools | **3** |
| Research Session storage | **3** |
| Chat UI | **4** |
| Parallel multi-site crawls | ❌ not planned (M5) |

---

## Contracts (Layer 2)

| ID | Rule |
|----|------|
| M-H1 | Meta-agent only calls registered tools |
| M-H2 | `crawl_site` count ≤ `max_sites_per_session` |
| M-H3 | No tool args with filesystem paths / shell |
| M-H4 | Compare requires ≥2 completed runs OR explicit single-site answer |
| M-S1 | Progress events sent before each tool (transparency) |

Separate from crawl ABC — enforced in `research/tool_executor.py`.

---

## Testing

| Test | Type |
|------|------|
| URL extraction from message | unit |
| Intent → crawl defaults mapping | unit |
| Sequential queue: 3 mock crawls | integration |
| compare_results mock R1 → ComparisonResult | integration |
| UC-1 fixture: 2 local sites design compare | e2e |
| UC-2 fixture: 2 blogs football article | e2e |

---

## Requirements mapping

| Requirement | This doc |
|-------------|----------|
| FR-6 (new) | Research chat + multi-site |
| FR-6.1 | Parse N URLs from message |
| FR-6.2 | Sequential crawl queue |
| FR-6.3 | Compare synthesis |
| FR-6.4 | Research Session persistence |
| D-7 | Multi-site: **sequential only** ✅ |
| D-8 (new) | Two-layer architecture ✅ |
| D-9 (new) | Chat UI = Phase 4 primary UX ✅ |

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | v0.1: Research Chat Agent — UC-1/UC-2, tools, session, compare, phases |
| 2026-07-05 | **v0.2 (review):** planner rules-first (Phase 3 без LLM-планирования; LLM meta — Phase 4); UC-1 max_pages=6 + session time budget (swap-математика: naive = до 12 загрузок моделей); cooldown 30–60 s при N≥4 (thermal); phase-batched execution в backlog |
| 2026-07-05 | **v0.3 (review-2):** partial failure spec (compare по ≥2 выжившим, `excluded[]`, M-H4 edge); UC-2 — 3 article candidates per site; `max_session_duration_min: 60` graceful timeout |
| 2026-07-18 | **v0.4 (Phase 3 impl):** реализовано `research/{meta_agent,runner,compare_synthesizer,report}` + `/sessions` API + `agent research` CLI. Уточнения: (1) plan/execute слиты в ResearchRunner — отдельного tool_executor-модуля нет, контракты M-H1..M-H4 enforced в раннере; (2) get_run_result/list_session_runs как отдельные tools не нужны rules-планнеру (runner читает store напрямую), для Phase 4 LLM-планнера — вернуть; (3) session-level cancel_event пробрасывается в текущий crawl (одно событие отменяет и очередь, и активный run); (4) `GET /sessions/{id}/events` SSE отложен до Phase 4 (CLI поллит GET /sessions/{id}); (5) винner/rankings: run_id проставляет код по url — LLM оперирует только url/label, выдуманные сайты отбрасываются |
| 2026-07-19 | **v0.5 (Phase 4 Chat UI impl):** § Chat UI — реализован (`frontend/`, React 19 + Vite 7 + TS + Tailwind v4; детали doc 17 v0.4); SSE `/sessions/{id}/events` закрыт (протокол doc 15 v0.6 — poll-паттерн поверх store, M-S1 tool-notes идут событиями `message`); экспорт `GET /sessions/{id}/report`. Остаток Phase 4: UC-1/UC-2 exit-прогон из чата + `planner: llm` |
| 2026-07-19 | **v0.7 (Phase 5 attended):** § Attended-режим — human-in-the-loop прохождение anti-bot challenge (не обход детекта). `orchestrator/attended.py` (AttendedGate + EventAttendedGate), статус `waiting_user`, видимый браузер (`headless=False`), resume-эндпоинты, SSE `challenge_wait`, карточка-пауза + тумблер в Chat UI, CLI `--attended`. D-12: `waiting_user` держит лок. Границы: fingerprint-спуфинг/автопрохождение — вне scope навсегда |
| 2026-07-19 | **v0.6 (Phase 4 ✅ DONE):** § Planner — `planner: llm` реализован (`research/llm_planner.py` + `data/prompts/meta_planner_*`): rules fast-path при URL в сообщении, LLM для диалога без URL; пост-валидация M-H1..M-H3 (URL только из истории сессии, run_id только из runs сессии, невалидный JSON → фоллбек-reply); `get_run_result`/`list_session_runs` возвращены для LLM-пути, `compare_results` принимает run_ids прошлых runs (re-compare/re-crawl без потери сессии). Проверено на реальной модели из Chat UI: follow-up ответ из comparison-контекста; re-crawl упавшего сайта по фразе без URL + re-compare 4/4. Excluded-семантика уточнена: перекраленный успешно URL не остаётся в excluded[] |
