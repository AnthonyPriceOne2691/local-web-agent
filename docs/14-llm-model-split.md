# 14 — LLM Model Split

> Local Web Agent · Design doc · **v0.5** · 2026-07-18

## Принцип (D-2/D-3 closed: single-model qwen3)

**Один text-модель `qwen3:14b` в двух режимах (`think:false` для hot loop, `think:true` для итогового JSON) · VLM для скриншотов.** Ноль свопов внутри text-пайплайна — главный выигрыш на 32 GB (Phase 0 A/B #10 + Phase 2 exit-бенчмарк).

| Pass | Latency sensitive? | Model (канон doc 16 v0.5) | Fallback |
|------|-------------------|---------------------------|----------|
| PLAN (each page) | ✅ Yes | `qwen3:14b` `think:false` | `qwen2.5:14b-instruct` |
| **VISION** (per PNG, batch) | ⚠️ Moderate | **`qwen2.5vl:7b`** (doc 23) | `gemma3:12b` |
| SYNTHESIZE (per site) | ❌ No | `qwen3:14b` `think:true` | `deepseek-r1:14b` |
| **META** (research plan) | — | **rules-planner Phase 3** (без LLM, doc 24); LLM Phase 4 → `qwen3:14b` `think:false` | |
| **COMPARE** (N sites) | ❌ No | `qwen3:14b` `think:true` | `deepseek-r1:14b` |

Правило: **навигация — think off; картинки — VLM; итог — think on.** Synthesis/compare не получают raw PNG — только текст `vision_insights`.

---

## Model responsibilities

### Qwen2.5 14B Instruct — Navigation

**Input:** task + PageSnapshot (DOM) + top-K links + budget  
**Output:** JSON `AgentAction` (doc 04)

### Qwen2.5-VL 7B — Vision analysis (D-6b)

> **Тег исправлен (review):** в реестре Ollama модель называется **`qwen2.5vl`** (3b/7b/32b/72b); тега `qwen2-vl` в library нет. Проверить `ollama pull qwen2.5vl:7b` в Phase 0.

**Input:** PNG base64 + task + url + profile + optional DOM excerpt  
**Output:** `VisionInsight` JSON (doc 23)

**Why separate model:** multimodal; не грузить в Qwen 14B text-only.

**When:** `vision_enabled: auto` — design_audit, sparse DOM, explicit visual task.

### DeepSeek R1 14B — Synthesis

**Input:** task + all snapshots (DOM + **vision_insights text**) + step trace  
**Output:** `ExtractionResult` (doc 05)

**Post-process:** Ollama ≥ 0.9 — `think: true` в запросе; thinking приходит отдельным полем `message.thinking`, JSON — в `content`. `strip_thinking()` — только fallback при утечке `<think>` (doc 16).

### Qwen2.5 14B Instruct — Meta-agent (Layer 2)

**Input:** user message + session history + tool results  
**Output:** tool call plan OR chat reply (doc 24)

**When:** Research Session message received. Does **not** navigate directly.

### DeepSeek R1 14B — Compare synthesis

**Input:** N × ExtractionResult (truncated) + comparison_task + rubric template  
**Output:** `ComparisonResult` JSON (doc 05)

**When:** after all `crawl_site` tools complete in session.

---

## Model swap timeline (32 GB Air)

```
Run start
  → load Qwen 14B + Chromium
  → loop N × PLAN
  → close browser, evict Qwen

Vision batch (if enabled)
  → load qwen2.5vl:7b
  → for each key page × profile: analyze PNG → vision_insights
  → evict VLM

Synthesis
  → load R1 14B
  → SYNTHESIZE once
  → unload

Research session (Layer 2, doc 24):
  → Meta Qwen (tool plan)
  → FOR each site: repeat crawl + vision + SYNTHESIZE timeline above
  → load R1 → COMPARE once → unload
```

**Never** two 14B models or 14B + VLM + Chromium together.

| Phase | Loaded | RAM ~ |
|-------|--------|-------|
| Crawl | Qwen + Chromium | ~14–16 GB |
| Vision batch | qwen2.5vl:7b | ~8–10 GB |
| Synthesis | R1 14B | ~10–12 GB |

### Swap mechanics (implementation)

Своп — не «надежда на Ollama», а явное управление:

| Механизм | Как |
|----------|-----|
| Выгрузка после pass | `keep_alive: 0` в последнем запросе pass'а (или `ollama stop <model>`) |
| Одна модель в памяти | env `OLLAMA_MAX_LOADED_MODELS=1` для daemon |
| Верификация | `GET /api/ps` перед загрузкой следующей модели; ждать освобождения ≤ 15 s |
| Загрузка 14B с SSD | ~5–15 s на M5 — учитывать в wall-time бюджете (doc 24: до 12 своп-циклов на 4-site сессию) |

---

## Fallback matrix

| If… | Then… |
|-----|--------|
| Qwen navigation weak | `qwen3:14b` (`think: false`) / `gpt-oss:20b` / `llama3.1:8b` + prompt tuning |
| qwen2.5vl:7b quality weak | `gemma3:12b` (multimodal) / `minicpm-v:8b` / `llama3.2-vision:11b`; `llava:7b` — legacy, последний вариант |
| qwen2.5vl too slow | vision on key pages only; desktop profile only |
| R1 JSON invalid | retry; fallback Qwen JSON mode |
| No vision model installed | DOM-only synthesis; warn in CLI |

---

## Phase 0 A/B candidates (модельный ландшафт 2025–26)

Выбор D-2/D-3 сделан по знакомому стеку — **провизорно**. Бенчмарк тех же задач стоит дёшево (параметр `--model` в spike-скрипте), а кандидаты заметно новее:

| Кандидат | Роль | Зачем пробовать |
|----------|------|-----------------|
| **`qwen3:14b`** (~9 GB) | nav (`think:false`) **и** synthesis (`think:true`) | Гибридный thinking → **одна модель на обе роли = ноль свопов Qwen↔R1**; новее qwen2.5 и r1-distill (обе — поколение до) |
| **`gpt-oss:20b`** (MoE 3.6B active, ~13 GB MXFP4) | nav / meta / synthesis | Быстрый на Apple Silicon, нативный tool-calling и reasoning effort |
| `deepseek-r1:14b` (базовый выбор) | synthesis | Distill Qwen-2.5 января 2025; обновление 0528 вышло только в 8b (qwen3-distill) — 14b не свежий |
| `gemma3:12b` (~8 GB, multimodal) | vision alt | Один из сильнейших открытых VLM-классов; заодно кандидат «vision+text одной моделью» |

**Gate:** если `qwen3:14b` в обоих режимах ≥ качества пары qwen2.5+r1 на Phase 0 задачах — упростить split до **двух** моделей (qwen3 + VLM) и убрать своп в hot path.

---

## D-6 resolution

| ID | Decision | Status |
|----|----------|--------|
| D-6a | Screenshot capture multi-viewport | ✅ doc 22 |
| **D-6b** | Vision model **`qwen2.5vl:7b`** via Ollama; loader + analyzer doc 23 | ✅ **design closed**; benchmark Phase 0/2 |

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial model split |
| 2026-07-05 | **v0.2:** three-model split + swap timeline; D-6b vision model (doc 23) |
| 2026-07-05 | **v0.3:** Meta-agent Qwen + Compare R1 (doc 24) |
| 2026-07-05 | **v0.4 (review):** vision-тег исправлен `qwen2-vl:7b` → **`qwen2.5vl:7b`** (реального тега qwen2-vl в Ollama library нет); fallback-матрица обновлена (gemma3/minicpm-v вместо llava:13b); swap mechanics (keep_alive=0, OLLAMA_MAX_LOADED_MODELS=1, /api/ps); Phase 0 A/B кандидаты qwen3:14b (single-model вариант) и gpt-oss:20b; strip_thinking → Ollama think param |
| 2026-07-18 | **v0.5 (D-2/D-3 closed):** канон — **`qwen3:14b` single-model** (PLAN `think:false` / SYNTHESIZE+COMPARE `think:true`), пара qwen2.5+r1 — fallback; META Phase 3 — rules-planner без LLM (doc 24 v0.4); свопы остаются только text↔VLM (vision batch) |
