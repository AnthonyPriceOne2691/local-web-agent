# 23 — Vision Analysis (screenshot → LLM)

> Local Web Agent · Design doc · **v0.3** · 2026-07-05

## Назначение

**Достать скриншот с диска → локальная vision-модель → описание + structured insights** → передать в SYNTHESIZE вместе с DOM. Замыкает цикл: Playwright снимает PNG (doc 22) → код загружает файл → LLM «видит» страницу → полезная информация в результате.

**D-6b:** не облако; только Ollama multimodal на Mac.

---

## Pipeline

```
OBSERVE (doc 03, 22)
  → screenshots[] on disk
        │
        ▼
VisionLoader.read(relative_path) → bytes / base64
        │
        ▼
VisionAnalyzer.analyze(png, task, profile)   # Ollama + VLM
        │
        ▼
VisionInsight JSON → PageSnapshot.vision_insights[]
        │
        ▼
SYNTHESIZE (R1): DOM text + vision_insights + task → ExtractionResult
```

**Когда вызывать:** **batch** в состоянии `VISION_BATCH` после crawl loop, перед `SYNTHESIZE` (doc 04). Не блокирует navigation loop.

---

## Key pages heuristic (`auto` mode)

**Оптимальный баланс:** vision на **малом числе высокосигнальных страниц**, не на каждом шаге.

### Кто всегда попадает в vision queue

| Rule | Pages |
|------|-------|
| **R0** | Step index **0** (homepage / start URL after normalize) |
| **R1** | Любой snapshot с `priority_snapshot: true` (см. ниже) |
| **R2** | `main_text` length **< 200** после settle — **desktop profile only** |
| **R3** | `task_intent = design_audit` — **все visited** с captured screenshots |

> **R2 требует «SPA fallback capture» (docs 03/22):** при пустом DOM observer **принудительно** снимает desktop PNG даже при `capture_screenshots: never` — иначе к моменту VISION_BATCH страница уже покинута и анализировать нечего.

### Когда orchestrator ставит `priority_snapshot: true`

| Trigger | Where |
|---------|-------|
| ACT `extract_now` | Current page |
| PLAN `stop` + `task_progress: likely_complete` | Current page |
| Title or h1 matches intent keywords (doc 21) | That page |
| Link scorer: page was **target of navigate** with score ≥ 15 | That page |
| Early stop fired (≥2 intent pages) | Last 2 intent-matching pages |

Set in OBSERVE after snapshot; persisted in `artifacts/.../steps/{n}.json`.

### Caps (default config)

| Param | Default | Purpose |
|-------|---------|---------|
| `max_vision_pages` | **5** | Hard cap on distinct URLs analyzed |
| `max_vision_calls` | **12** | pages × profiles ceiling |
| `vision_profiles` | `auto` | см. doc 21 matrix |

**Selection order** when queue exceeds cap:

```
1. design_audit → all visited (ignore cap except max_vision_calls)
2. Else: R0 homepage
3. Else: priority_snapshot pages by step_index desc (most recent first)
4. Else: empty-DOM pages (R2)
5. Truncate tail; log vision_skipped_pages[] in run metadata
```

`--vision always` bypasses page cap (still subject to `max_vision_calls` safety default **30**).

### Profiles per page

| Intent / condition | Profiles analyzed |
|--------------------|-------------------|
| `design_audit` | desktop + tablet + mobile (if captured) |
| `main_text < 200` | desktop only |
| Other priority pages | **desktop + mobile** (skip tablet — save 33% calls) |
| `--vision-profiles desktop` | override |

---

## Failure modes & degraded output

Vision **не валит run** — worst case: DOM-only synthesis с warning в metadata.

### Per-call outcomes (`VisionInsight.status`)

| status | When | Synthesis impact |
|--------|------|------------------|
| `ok` | Valid JSON; analysis completed | Full merge |
| `skipped` | PNG missing; vision disabled for page; cap exceeded | No insight; log only |
| `failed` | Timeout / Ollama unreachable after retry | Empty extracted[]; `description` explains |
| `degraded` | Invalid JSON after retry; partial parse | Use fields that validated; confidence forced **low** |

### Error handling table

| Error | Detection | Recovery | User-visible |
|-------|-----------|----------|--------------|
| PNG missing | Loader 404 | `status: skipped`, reason `file_missing` | `runs show` warning count |
| Image > 5 MB | Loader size check | skip + log | metadata |
| Ollama timeout | 45 s per call | **1 retry** (same PNG) | `failed` if 2× |
| Invalid JSON | Pydantic fail | **1 retry** with «fix JSON only» suffix | `degraded` if 2× |
| Blank / white image | VLM `screen_status: blank` | no extracted[] | synthesis not_found |
| Cookie / consent wall | VLM `screen_status: obstructed` | no business facts | report appendix |
| OOM during batch | process memory | skip remaining; continue R1 | `vision_partial: true` |
| VLM model missing | health check pre-batch | skip entire batch; DOM-only | CLI stderr hint `ollama pull qwen2.5vl:7b` |

### Extended `VisionInsight` schema

```json
{
  "profile": "desktop",
  "url": "https://example.com/pricing",
  "status": "ok",
  "screen_status": "ok",
  "description": "...",
  "extracted": [],
  "design": {},
  "text_not_in_dom": [],
  "confidence": "high",
  "error": null
}
```

`screen_status` enum: `ok` | `blank` | `obstructed` | `error_page` | `unknown`

Run-level flags in `crawl_runs.metadata_json`:

```json
{
  "vision_enabled": "auto",
  "vision_pages_analyzed": 3,
  "vision_calls_total": 7,
  "vision_failures": 1,
  "vision_partial": false,
  "vision_skipped_pages": ["https://example.com/blog/post-12"]
}
```

**ExtractionResult.status** не меняется из-за vision alone — только synthesis outcome. Vision failure → `partial` только если task required visual evidence (`design_audit`) and zero ok insights.

---

## VisionLoader

**Модуль:** `backend/app/vision/loader.py`

| Method | Behavior |
|--------|----------|
| `resolve(run_id, relative_path)` | Absolute path under `artifacts/{run_id}/` |
| `read_bytes(path)` | Raw PNG; 404 if missing |
| `read_base64(path)` | For Ollama `images[]` API |
| `list_step_screenshots(run_id, step_index)` | All profiles for step |

**Контракт:** только пути из `PageSnapshot.screenshots[]` — не arbitrary filesystem (ABC: no path injection).

---

## VisionAnalyzer

**Модуль:** `backend/app/vision/analyzer.py`  
**Interface:** `VisionAnalyzer` Protocol → `OllamaVisionClient`

```python
async def analyze(
    self,
    *,
    image_base64: str,
    task: str,
    url: str,
    profile: Literal["desktop", "tablet", "mobile"],
    dom_excerpt: str | None,   # first 1500 chars — avoid duplicate extraction
) -> VisionInsight:
```

**Output schema (`VisionInsight`):**

```json
{
  "profile": "mobile",
  "url": "https://example.com/pricing",
  "description": "Pricing page with three tier cards; Pro plan highlighted in blue.",
  "extracted": [
    {"key": "pro_price_visible", "value": "$29/mo", "confidence": "high"},
    {"key": "primary_button", "value": "Start free trial", "confidence": "high"}
  ],
  "design": {
    "colors_approx": ["#2563eb", "#ffffff", "#1e293b"],
    "layout": "three-column cards, sticky header",
    "responsive_note": "hamburger menu, single column cards"
  },
  "text_not_in_dom": [],
  "confidence": "high"
}
```

`text_not_in_dom` — текст, видимый на скрине, но отсутствующий в DOM excerpt (canvas, image text, lazy fail).

---

## Когда включать vision

| `vision_enabled` | Behavior |
|------------------|----------|
| `never` | Skip; DOM-only synthesis |
| `auto` (default) | See table below |
| `always` | Every captured screenshot profile |

### `auto` triggers

| Condition | Vision |
|-----------|--------|
| `task_intent` = **`design_audit`** | ✅ all captured profiles |
| `main_text` length < **200** after settle | ✅ desktop (+ mobile if captured) |
| `capture_screenshots` = on + task mentions «look», «design», «screenshot», «layout», «color» | ✅ |
| Plain info task + rich DOM | ❌ skip (save time) |

CLI: `--vision`, `--no-vision`.

---

## Model (D-6b — provisional, тег исправлен)

> **Review note:** в Ollama library модель называется **`qwen2.5vl`** (не `qwen2-vl`) — тег исправлен по всем докам; проверить `ollama pull qwen2.5vl:7b` в Phase 0.

| Role | Model | RAM ~ | Phase |
|------|-------|-------|-------|
| **Vision analyze** | **`qwen2.5vl:7b`** (primary) | ~6 GB | 2 |
| Fallback | `gemma3:12b` (multimodal) | ~8 GB | 2 |
| Fallback 2 | `minicpm-v:8b` / `llama3.2-vision:11b` | ~6–8 GB | benchmark |
| Legacy | `llava:7b` (2023-класс, слабее современных) | ~5 GB | last resort |

Benchmark Phase 0/2 validates quality vs latency; model choice fixed in design, swap in Phase 0 optional spike.

**Canonical params** — doc 16 § `vision`.

### Swap timeline (32 GB Air)

```
1. Crawl loop: Qwen 14B + Chromium        (~14–16 GB)
2. Close browser
3. Vision batch: qwen2.5vl:7b            (~6 GB) — N × analyze
4. Evict VLM → load R1 14B              (~9 GB)
5. SYNTHESIZE (DOM + vision_insights text, no images in R1 prompt)
```

**Never** Qwen + R1 + VLM одновременно. R1 получает **текстовые** vision_insights, не raw PNG — экономия контекста.

---

## Ollama API (multimodal)

```python
await client.chat(
    model="qwen2.5vl:7b",
    messages=[{
        "role": "user",
        "content": prompt,  # from vision_user.j2
        "images": [base64_png],
    }],
    format="json",
    options={"temperature": 0.2, "num_ctx": 8192},
)
```

Prompt: extract task-relevant facts; describe layout for design; output JSON matching `VisionInsight`; do not invent text not visible.

---

## Integration with PageSnapshot

```json
{
  "url": "https://example.com/pricing",
  "main_text": "...",
  "screenshots": [ ... ],
  "vision_insights": [
    {
      "profile": "desktop",
      "description": "...",
      "extracted": [ ... ],
      "design": { ... }
    },
    {
      "profile": "mobile",
      "description": "...",
      "responsive_note": "..."
    }
  ]
}
```

If vision skipped: `vision_insights: []`.

---

## Integration with SYNTHESIZE (R1)

`synthesizer_user.j2` includes per page:

```
URL: ...
DOM excerpt: ...
Vision (desktop): description + extracted JSON
Vision (mobile): ...
```

R1 merges DOM facts + vision facts; **dedupe** by key; vision wins on conflict for **visual** fields (colors, layout); DOM wins on **verbatim quotes** for text evidence.

Contract S-H3 (doc 13): quotes in `facts[]` still prefer DOM substring; vision-only facts → `confidence: medium` max unless cross-validated.

---

## Design audit flow (end-to-end)

```
Task: "Audit design: colors, typography, mobile vs desktop"
  → intent design_audit
  → screenshots: desktop + tablet + mobile (doc 22)
  → vision: analyze × 3 profiles
  → R1: ExtractionResult with design_tokens + responsive_notes + screenshot_paths
```

---

## Performance budget

| Metric | Target |
|--------|--------|
| Single VLM call (1 PNG, 7B) | **5–15 s** warm |
| 3 profiles × 10 pages (worst) | **batch only if needed** — default: vision on **key pages** only (homepage + pages with extract_now flag) |
| Key pages only | orchestrator marks `priority_snapshot: true` → vision runs on those + homepage |

**Optimization:** full vision on all steps only with `--vision always`; else key pages + empty-DOM fallback.

---

## Prompts

```
data/prompts/
├── vision_system.txt
└── vision_user.j2    # task, url, profile, dom_excerpt optional
```

See [16-prompts-library.md](16-prompts-library.md).

---

## Module layout

```
backend/app/vision/
├── loader.py       # PNG read, path resolve
├── analyzer.py     # orchestrates analyze()
├── ollama_vision.py
└── schemas.py      # VisionInsight pydantic
```

---

## API & CLI

POST /runs:

```json
{
  "vision_enabled": "auto",
  "vision_profiles": "all"
}
```

CLI: `--vision`, `--no-vision`, `--vision-profiles desktop,mobile`.

---

## Phase mapping

| Item | Phase |
|------|-------|
| Screenshot capture | 1 (doc 22) |
| VisionLoader + VisionAnalyzer + Ollama VLM | **2** |
| Key-page-only optimization | 2 |
| R1 merge vision_insights | 2 |
| VLM in hot navigation loop | ❌ not planned |

---

## Testing

| Test | Type |
|------|------|
| Loader reads fixture PNG | unit |
| Analyzer mock Ollama → valid VisionInsight | unit |
| auto: design_audit triggers vision | unit |
| auto: rich DOM info task skips vision | unit |
| Synthesis fixture includes vision_insights in R1 prompt | integration |

Fixture: `tests/fixtures/screenshots/pricing_desktop.png` + mock JSON response.

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | v0.1: vision pipeline — loader, analyzer, VisionInsight, R1 merge |
| 2026-07-05 | **v0.2:** key pages heuristic (R0–R3, caps); failure modes; VisionInsight.status |
| 2026-07-05 | **v0.3 (review):** тег `qwen2-vl:7b` → `qwen2.5vl:7b`; fallback-лестница gemma3/minicpm-v/llama3.2-vision (llava → legacy); R2 ⇒ SPA fallback capture (docs 03/22) — закрыт разрыв «пустой DOM без скриншота» |
