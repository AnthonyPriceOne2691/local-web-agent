# 24 — Research Chat Agent (multi-site + compare)

> Local Web Agent · Design doc · **v0.3** · 2026-07-05

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

### Planner: rules-first (Phase 3), LLM — Phase 4

Для фиксированных research intents план **полностью детерминирован** (URLs → intent → N × crawl_site → compare) — LLM-планирование здесь лишняя поверхность отказа (ещё один JSON-парсинг + контракты M-*). Поэтому:

| Mode | Когда | Что делает |
|------|-------|------------|
| `planner: rules` (**default Phase 3**) | intent распознан по keywords + URLs распарсены regex'ом | План строится кодом по таблице research intents; LLM не вызывается до compare |
| `planner: llm` (Phase 4) | Chat UI: свободный диалог, follow-up вопросы, ambiguous intent | Qwen meta-prompt → tool call plan (контракты M-*) |

`agent research` CLI (Phase 3) работает **целиком на rules** — меньше рисков, быстрее, проще тестировать. LLM meta-agent подключается в Phase 4, когда появляется настоящий диалог.

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

**Статус:** целевой интерфейс продукта (обновляет D-5, OQ-1).

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
