# 15 — API & CLI Spec

> Local Web Agent · Design doc · **v0.5** · 2026-07-05

## Base URL

```
http://localhost:8001
```

Uvicorn биндится **только на `127.0.0.1`** (NFR-2.5) — API не требует auth, поэтому не должен быть доступен из сети.

## Concurrency (D-12)

**Один активный crawl глобально.** Два параллельных run'а = 2 × (Chromium + 14B) → OOM на 32 GB. Правило уровня API, не только Layer 2:

| Событие | Поведение |
|---------|-----------|
| `POST /runs` при активном run | **409** `{"error": "run_in_progress", "active_run_id": "..."}` |
| `POST /sessions/{id}/messages` при активном | 409 аналогично (meta-agent сам сериализует внутри сессии) |
| Рестарт бэкенда | **Startup sweep** (doc 12): осиротевшие `running` → `failed`; lock производный от БД, не от памяти процесса |
| Phase 3+ (optional) | Внутренняя FIFO-очередь: 202 + `status: queued`, `queue_position` |

## REST API

### GET /health

```json
{
  "status": "ok",
  "ollama": "reachable",
  "ollama_version": "0.9.6",
  "playwright": "ready",
  "models": {
    "qwen2.5:14b-instruct": true,
    "deepseek-r1:14b": true,
    "qwen2.5vl:7b": false
  },
  "active_run_id": null
}
```

`models` — presence check через Ollama `/api/tags` (contract P-5); отсутствие vision-модели — warning, не failure. `ollama_version` — из `/api/version`; **< 0.9 → warning**: `think`-параметр для R1 недоступен (doc 16), fallback на strip_thinking.

### POST /runs

Start async crawl (background task).

**Request:**

```json
{
  "start_url": "https://example.com",
  "task": "Find enterprise pricing and sales contact",
  "max_pages": 10,
  "max_depth": 2,
  "same_domain_only": true,
  "rate_limit_ms": 1000,
  "respect_robots": true,
  "capture_screenshots": "auto",
  "screenshot_viewports": "all",
  "screenshot_full_page": false,
  "vision_enabled": "auto",
  "vision_profiles": "all"
}
```

**Response 202:**

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running"
}
```

### GET /runs/{run_id}

**Response:**

```json
{
  "run_id": "...",
  "status": "running",
  "pages_visited": 3,
  "max_pages": 10,
  "current_url": "https://example.com/about",
  "steps": [
    {
      "index": 0,
      "url": "https://example.com",
      "action": "navigate",
      "target_url": "https://example.com/pricing",
      "reasoning": "Pricing link in nav",
      "screenshot_paths": {
        "desktop": "screenshots/001_home_desktop.png",
        "tablet": "screenshots/001_home_tablet.png",
        "mobile": "screenshots/001_home_mobile.png"
      }
    }
  ]
}
```

When `status` is terminal, includes `result` (ExtractionResult).

### GET /runs/{run_id}/result

Returns `ExtractionResult` only. 404 if not finished.

### GET /runs/{run_id}/steps/{step_index}/screenshot

Query: `?profile=desktop` | `tablet` | `mobile` (default `desktop`).

Returns `image/png` for the step. 404 if screenshots disabled or profile not captured. See [22-page-screenshots.md](22-page-screenshots.md).

### GET /runs

List runs (paginated).

```json
{
  "runs": [
    {"run_id": "...", "task": "...", "status": "completed", "started_at": "..."}
  ],
  "total": 12
}
```

### POST /runs/{run_id}/cancel

Отмена активного run. **202** `{"run_id": "...", "status": "canceling"}`.

Оркестратор проверяет cancel-флаг на каждой границе state (перед OBSERVE/PLAN/ACT, между vision-вызовами). Уже собранные snapshots → **SYNTHESIZE пропускается**, run завершается `status: canceled` с сохранённым partial trace. 409 если run уже terminal.

### DELETE /runs/{run_id}

Delete run + artifacts. 204. 409 если run активен (сначала cancel).

---

## Research API (Phase 3 — doc 24)

### POST /sessions

```json
{ "title": "optional" }
```

**Response 201:** `{ "session_id": "..." }`

### POST /sessions/{session_id}/messages

```json
{
  "content": "Sites: a.com, b.com, c.com, d.com — describe design of each and differences"
}
```

**Response 202:** `{ "session_id": "...", "status": "running_tools" }`

Meta-agent parses URLs, runs sequential crawls, compare pass, appends assistant message.

### GET /sessions/{session_id}

```json
{
  "session_id": "...",
  "status": "completed",
  "messages": [ ... ],
  "run_ids": ["...", "..."],
  "comparison_result": { ... }
}
```

### GET /sessions/{session_id}/events

SSE: `tool_start`, `crawl_progress`, `compare_start`, `done`.

### POST /sessions/{session_id}/cancel

Останавливает tool-цикл сессии: текущий crawl доводится до cancel (см. `/runs/{id}/cancel`), очередь сайтов очищается, статус `failed` с пометкой `canceled_by_user`. 202.

### DELETE /sessions/{session_id}

204 — removes session artifacts + optional linked runs (configurable).

---

## CLI

Entry: `agent` (or `python -m cli.main`)

### agent crawl

```bash
agent crawl \
  --url https://example.com \
  --task "Find enterprise pricing" \
  --max-pages 10 \
  --max-depth 2 \
  --output result.json \
  --report report.md \
  --wait
```

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | required | Start URL |
| `--task` | required | Natural language task |
| `--max-pages` | 10 | Page budget |
| `--max-depth` | 2 | Path depth |
| `--allow-external` | false | Cross-domain links |
| `--no-robots` | false | Skip robots.txt (use with care) |
| `--output` | stdout | JSON file path |
| `--report` | none | Markdown report path |
| `--screenshots` | auto | `always` \| `never` \| `auto` (doc 22) |
| `--screenshot-viewports` | auto | `all` or `desktop,tablet,mobile` |
| `--screenshot-full-page` | false | Full scrollable page PNG |
| `--vision` | auto | `always` \| `never` \| `auto` (doc 23) |
| `--no-vision` | — | Force DOM-only synthesis |
| `--vision-profiles` | auto | `all` or `desktop,mobile` |
| `--wait` | true | Block until complete |
| `--api-url` | http://localhost:8001 | Backend URL |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | completed or partial with facts |
| 1 | not_found or blocked |
| 2 | technical failure |
| 3 | API unreachable |

### agent research (Phase 3)

```bash
agent research \
  --urls "https://a.com,https://b.com,https://c.com,https://d.com" \
  --task "Describe design of each site and how they differ" \
  --output comparison.json \
  --report comparison.md \
  --wait
```

| Flag | Default | Description |
|------|---------|-------------|
| `--urls` | required | Comma-separated start URLs (max 10) |
| `--task` | required | Natural language research task |
| `--output` | stdout | ComparisonResult JSON |
| `--report` | none | comparison_report.md path |
| `--max-pages` | per intent | Override per-site page budget |
| `--wait` | true | Block until session complete |

Equivalent to one chat message without UI (doc 24).

### agent sessions (Phase 3)

```bash
agent sessions list
agent sessions show <session_id>
agent sessions show <session_id> --messages
```

### agent runs list

```bash
agent runs list --limit 20
```

### agent runs show

```bash
agent runs show 550e8400-e29b-41d4-a716-446655440000
agent runs show 550e8400 --steps    # include step trace + screenshot paths
agent runs show 550e8400 --open-screenshots   # reveal artifacts in Finder (macOS)
```

### agent runs cancel

```bash
agent runs cancel 550e8400        # или без id — отменить активный
```

Ctrl+C в blocking-режиме (`--wait`) предлагает: `[a]bort run on server / [d]etach (run continues)`.

### agent runs delete

```bash
agent runs delete 550e8400
```

---

## CLI disclaimer (first run)

```
Local Web Agent — personal research tool.
You are responsible for complying with website Terms of Service.
robots.txt is respected by default.
```

---

## Progress events (Phase 2 optional SSE)

```
GET /runs/{run_id}/events   # Server-Sent Events

event: step
data: {"index": 2, "url": "...", "action": "navigate"}

event: done
data: {"status": "completed"}
```

MVP: CLI polls `GET /runs/{id}` every 2 s.

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial API & CLI spec |
| 2026-07-05 | capture_screenshots, GET step screenshot, CLI flags (doc 22) |
| 2026-07-05 | screenshot_viewports: desktop, tablet, mobile; ?profile= query |
| 2026-07-05 | vision_enabled, vision_profiles; CLI --vision flags (doc 23) |
| 2026-07-05 | **v0.3:** Research API /sessions; agent research CLI (doc 24) |
| 2026-07-05 | **v0.4 (review):** concurrency D-12 (409 при активном run); `POST /runs/{id}/cancel` + `agent runs cancel` + session cancel; /health c model presence + active_run_id; bind 127.0.0.1 (NFR-2.5) |
| 2026-07-05 | **v0.5 (review-2):** startup sweep в concurrency-таблице (lock из БД); /health + ollama_version (≥0.9 для think, doc 16) |
