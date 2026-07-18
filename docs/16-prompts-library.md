# 16 — Prompts Library

> Local Web Agent · Design doc · **v0.5** · 2026-07-18  
> **Канон LLM parameters** — этот документ. Doc 07 зеркалит.

**Не храним тексты промптов в design docs.** Только: какие файлы, за что отвечают, variables, ссылка на output schema. Рабочие тексты — в `data/prompts/` при реализации (итерация через Phase 0/1 spike).

## File layout

```
data/prompts/
├── navigator_system.txt       # Qwen — PLAN step
├── navigator_user.j2          # Jinja2: task, snapshot, links, budget
├── synthesizer_system.txt     # R1 — per-site extraction
├── synthesizer_user.j2        # Jinja2: task, snapshots + vision_insights
├── vision_system.txt          # qwen2.5vl — screenshot analyze
├── vision_user.j2             # Jinja2: task, url, profile, dom_excerpt
├── compare_system.txt         # R1 — N-site comparison (doc 24)
├── compare_user.j2            # Jinja2: task, rubric, site_summaries[]
├── meta_system.txt            # Qwen — research tool planning (doc 24)
└── meta_user.j2               # Jinja2: message, urls[], session context

data/prompts/rubrics/
├── design_diff.txt            # UC-1 compare dimensions (bullets, not prose prompt)
├── content_completeness.txt   # UC-2 compare dimensions
└── generic_merge.txt
```

Reload: on each run start (no restart required in dev).

---

## LLM parameters (canonical)

> **Structured outputs (review):** Ollama принимает в `format` не только `"json"`, но и **полную JSON Schema** — sampling ограничивается схемой, невалидный JSON почти исчезает. Для nav/meta/vision передаём Pydantic-схему (`Model.model_json_schema()`). Это снимает бо́льшую часть retry-веток I-H7.
>
> **R1 + format=json несовместимы со strip_thinking:** constrained decoding заставляет JSON с первого токена и **подавляет thinking-фазу** — теряется смысл reasoning-модели. Для R1: `format` не задаём, `think: true` (Ollama ≥ 0.9 отдаёт рассуждения отдельным полем `message.thinking`), JSON парсим из `content`; `strip_thinking()` — fallback для утечек `<think>`.

```yaml
navigation:    # PLAN step → qwen3:14b single-model (D-2 closed 2026-07-18; fallback qwen2.5:14b-instruct)
  model: qwen3:14b
  think: false                      # qwen3 в Ollama думает по умолчанию — для nav выключать
  num_ctx: 8192
  temperature: 0.4                  # drift auto-tighten → 0.2 (doc 13)
  max_tokens: 400
  stream: false
  format: schema:AgentAction        # JSON Schema constrained (doc 04)

synthesis:     # SYNTHESIZE → qwen3:14b single-model (D-3 closed; fallback deepseek-r1:14b)
  model: qwen3:14b
  num_ctx: 16384
  temperature: 0.2
  max_tokens: 4096
  stream: false
  format: none                      # НЕ json: не душить thinking
  think: true                       # Ollama ≥0.9; thinking → message.thinking
  strip_thinking: fallback          # только при утечке <think> в content

vision:        # VISION batch → qwen2.5vl:7b (doc 23)
  model: qwen2.5vl:7b
  num_ctx: 8192
  temperature: 0.2
  max_tokens: 1200
  stream: false
  format: schema:VisionInsight
  fallback_model: gemma3:12b        # llava:7b — legacy (2023), не default

meta:          # Research meta-agent → qwen2.5:14b-instruct (doc 24)
  model: qwen2.5:14b-instruct
  num_ctx: 8192
  temperature: 0.3
  max_tokens: 800
  stream: false
  format: schema:ToolCallPlan

compare:       # COMPARE → deepseek-r1:14b (doc 24)
  model: deepseek-r1:14b
  num_ctx: 16384                    # 24576 при N>3 сайтов (doc 20); только R1 в RAM — допустимо
  temperature: 0.2
  max_tokens: 4096
  stream: false
  format: none
  think: true
  strip_thinking: fallback
```

Все pass'ы: `keep_alive: 0` на последнем запросе перед model swap (doc 14 § Swap mechanics).

---

## Prompt responsibilities (outline only)

| File | Model | Purpose | Output schema |
|------|-------|---------|---------------|
| `navigator_*` | Qwen | Pick next action among top-K links | `AgentAction` (doc 04) |
| `synthesizer_*` | R1 | Per-site facts + evidence from snapshots | `ExtractionResult` (doc 05) |
| `vision_*` | qwen2.5vl | Describe screenshot; task-relevant visible facts | `VisionInsight` (doc 23) |
| `meta_*` | Qwen | Plan tool calls for research session | tool call JSON (doc 24) |
| `compare_*` | R1 | Rank/compare N site results | `ComparisonResult` (doc 05) |
| `rubrics/*` | — | Dimension checklist injected into compare prompt | referenced by rubric id |

### Shared rules (all JSON prompts)

- Output valid JSON only; schema in linked doc
- No invented URLs, prices, emails without evidence
- Log prompt file hash/version in run/session config for reproducibility
- **Язык ответа = язык task/сообщения пользователя** (summary, narrative, chat reply); ключи JSON — всегда en snake_case

---

## Template variables

### navigator_user.j2

| Variable | Content |
|----------|---------|
| `task` | User task string |
| `current_url` | |
| `snapshot` | Truncated PageSnapshot |
| `visited` | List `{url, title}` max 10 |
| `links` | **Top-10 scored candidates** из CandidateQueue (doc 21) — не сырые links; было «15», выровнено с docs 04/21 |
| `pages_left` | int |
| `depth_left` | int |

### synthesizer_user.j2

| Variable | Content |
|----------|---------|
| `task` | |
| `snapshots` | PageSnapshot incl. `vision_insights` (doc 20 truncate) |
| `step_trace` | URLs visited in order |

### vision_user.j2

| Variable | Content |
|----------|---------|
| `task` | User task |
| `url` | Page URL |
| `profile` | desktop \| tablet \| mobile |
| `dom_excerpt` | First ~1500 chars of main_text |

Image: Ollama `images[]`, not in Jinja template.

### meta_user.j2

| Variable | Content |
|----------|---------|
| `message` | Latest user message |
| `urls` | Parsed URL list |
| `session_history` | Truncated prior turns |
| `tools` | Tool registry descriptions |

### compare_user.j2

| Variable | Content |
|----------|---------|
| `comparison_task` | User compare question |
| `rubric` | Rubric id + dimension bullets from `rubrics/` |
| `site_summaries` | Truncated ExtractionResult per run |

---

## Prompt versioning

- Version in file header when implementing (`data/prompts/`, not design doc)
- Store `prompt_versions` in `crawl_runs.config_json` / `research_sessions.config_json`

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial prompts library |
| 2026-07-05 | vision/synthesizer params; file layout |
| 2026-07-05 | compare_*, meta_*, rubrics/ (doc 24) |
| 2026-07-05 | **v0.3:** removed prompt body text from design; outlines + variables only |
| 2026-07-05 | **v0.4 (review):** structured outputs (JSON Schema в `format`) для nav/meta/vision; конфликт `format:json`×`strip_thinking` у R1 устранён → `think:true` + отдельное поле thinking; vision fallback → gemma3:12b; compare num_ctx 24576 при N>3; правило языка ответа |
| 2026-07-05 | **v0.4.1 (review-2):** navigator links = top-10 candidates (было 15 — рассинхрон с docs 04/21) |
| 2026-07-18 | **v0.5 (Phase 2 exit-бенчмарк):** synthesizer_system — vision-aware: evidence получил поле `source: dom\|vision`, правило «факт только из VISION-блока → source: vision»; добавлены prod-промпты `vision_system.txt` + `vision_user.j2` (doc 23); **канон nav/synth → `qwen3:14b` single-model** (D-2/D-3 closed по бенчмарку doc 06 v0.6; пара qwen2.5+r1 — fallback) |
