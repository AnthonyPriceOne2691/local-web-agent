# 20 — Context & Token Budget

> Local Web Agent · Design doc · **v0.3** · 2026-07-31

## Назначение

Ограничить размер **PageSnapshot** и **multi-page context**, чтобы Qwen (8K) и R1 (16K) не переполнялись и не деградировали по latency/quality.

---

## Model context windows

| Pass | Model | `num_ctx` | Usable after system prompt |
|------|-------|-----------|----------------------------|
| PLAN | Qwen 14B | 8192 | ~6500 tokens |
| SYNTHESIZE | R1 14B | 16384 | ~14000 tokens |

Rule of thumb: **1 token ≈ 4 chars** English → 6500 tokens ≈ **26K chars** budget per PLAN call.

> ⚠️ **Non-Latin поправка (review):** проект целится в GEO-сайты (SEA/MENA) и русскоязычные задачи. Кириллица ≈ **2–3 chars/token**, тайский/арабский — ещё плотнее: реальный бюджет в chars может быть **~2× меньше** англоязычной оценки. Планировать по **3 chars/token** для non-Latin страниц; в Phase 0 записывать фактический `prompt_eval_count` из Ollama (doc 19) и калибровать капы. Переполнение `num_ctx` в Ollama **тихо обрезает голову промпта** — системный промпт уходит первым, это надо ловить по телеметрии, не по ошибке.

---

## PageSnapshot truncation (PLAN step)

Priority order when building snapshot for LLM:

| Priority | Field | Max chars |
|----------|-------|-----------|
| 1 | task (in system) | — |
| 2 | `title` + `meta_description` | 500 |
| 3 | `headings[]` | 2000 total |
| 4 | `links[]` (unvisited first) | 40 links × ~80 chars |
| 5 | `main_text` | **fill remainder** up to 6000 chars |
| 6 | visited summary | 800 |

**Hard cap `main_text` extraction from DOM:** 8000 chars (observer); **LLM-facing cap:** 6000 unless room left.

If truncated: set `truncated: true` in snapshot metadata.

---

## PLAN prompt budget (per step)

```
System prompt (navigator)     ~800 tokens
User template overhead        ~200 tokens
Current snapshot              ~1500 tokens (typical)
Visited list (10 URLs)        ~300 tokens
Link candidates (top-10, doc 21) ~300 tokens
Budget reminder               ~50 tokens
─────────────────────────────────────────
Total                         ~3150 tokens ✅ within 8192
```

**History:** MVP does **not** include full text of previous pages in PLAN — only visited URL titles. Full text deferred to SYNTHESIZE.

---

## SYNTHESIZE prompt budget

Assume max **10 pages** stored:

| Component | Budget |
|-----------|--------|
| System + schema | ~1200 tokens |
| Task + step trace | ~300 tokens |
| Per page (10×) | ~1200 tokens each → **12000** |

**Per page in synthesis bundle:**
- url + title: 100 chars
- headings: 500 chars
- main_text: **1000 chars** (aggressive truncate)
- **vision_insights** (if any): **400 chars** per profile (description + extracted JSON compact)
- links: omitted unless task-specific

If total > 14000 tokens → drop oldest pages' main_text first; keep all urls in trace.

---

## COMPARE prompt budget (Layer 2, doc 24)

UC-2: `article.main_text_excerpt` до **12000 chars** (~3K tokens EN / до 5–6K non-Latin) на сайт:

| N sites | Budget | Fits 16K? |
|---------|--------|-----------|
| 2–3 | ~7–11K tokens + rubric/overhead | ✅ |
| 4+ | 14K+ tokens | ⚠️ на границе |

Правило: при **N > 3** — либо excerpt cap **8000 chars**/сайт, либо `num_ctx: 24576` для compare pass (только R1 в RAM — допустимо на 32 GB; KV-cache overhead ~1–2 GB). Канон параметров — doc 16.

---

## KV-cache note (Qwen PLAN)

Unlike voice loop, PLAN prompt **changes every step** (new snapshot) — prefix cache hit limited to stable **system prompt only**. Expect full prefill each step.

Phase 0 must measure warm PLAN latency with **production-sized** snapshot (~1500 tokens), not toy prompts.

---

## Re-benchmark gate (Phase 1)

Before Phase 2 exit, re-run PLAN latency with:
- 6000 char main_text fixture
- 10 link candidates (top-K, doc 21)
- 10 visited entries

**Pass:** p95 PLAN **< 10 s** on M5.

---

## R1 thinking tokens

Reserve `max_tokens: 4096` for synthesis — thinking block may consume ~1500 before JSON.

**Замер 2026-07-31 — где на самом деле лежит время синтеза.** Разложение 21
синтез-шага: **87–97 % времени = генерация** (`eval_duration`), вход (511–1316
prompt-токенов) стоит 3–7 s из 37–174 s. Практический вывод для этого документа:
**урезание входных cap'ов почти не влияет на скорость** — оно влияет только на
полноту фактов. Резать надо выход, и на извлекающих интентах это делает быстрый
синтез (doc 16 § Быстрый синтез: мысли занимали 48–73 % выхода, `−68 %` токенов
при идентичном ответе). Cap'ы входа (`PAGE_TEXT_CAP` 1000 / `PRIORITY_TEXT_CAP`
4000 / `ARTICLE_TEXT_CAP` 12000) остаются как есть — они про качество, не про
латентность.

Ollama ≥ 0.9: `think: true` → рассуждения приходят отдельным полем `message.thinking`, JSON — в `content` (doc 16). `strip_thinking()` — fallback при утечке `<think>`. Empty content → retry once → `status: partial` with raw text in error log.

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial token budget; adapted from voice-interview-coach doc 20 |
| 2026-07-05 | SYNTHESIZE: vision_insights text budget per profile (doc 23) |
| 2026-07-05 | **v0.2 (review):** non-Latin токен-поправка (3 chars/token, prompt_eval_count калибровка, тихая обрезка num_ctx); COMPARE budget для N>3 (excerpt cap 8K или num_ctx 24576); think-param вместо strip_thinking |
| 2026-07-05 | **v0.2.1 (review-2):** PLAN budget — top-10 candidates (было 15), итог ~3150 tokens |
| 2026-07-31 | **v0.3 (замер синтеза):** § R1 thinking tokens дополнена разложением времени — 87–97 % синтеза это генерация, вход стоит 3–7 s из 37–174 s. Следствие: урезание входных cap'ов не ускоряет синтез (они про полноту фактов), рычаг — выход (doc 16 § Быстрый синтез) |
