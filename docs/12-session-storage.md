# 12 — Session Storage (Crawl Runs)

> Local Web Agent · Design doc · **v0.5** · 2026-07-18

## Назначение

Персистентность **crawl runs** и **research sessions** (Phase 3). Аналог session storage в Voice Interview Coach.

## Storage layout

```
data/runs/
├── app.db                 # SQLite
└── artifacts/
    ├── {run_id}/          # per crawl (Layer 1)
    │   ├── result.json
    │   ├── report.md
    │   ├── screenshots/
    │   └── steps/
    └── {session_id}/      # Phase 3 — research session
        ├── comparison_report.md
        └── messages.json  # optional export
```

Phase 1: только `data/runs/{run_id}.json` (flat file). Phase 2: migrate to SQLite + artifacts.

## SQLite schema (Phase 2)

### crawl_runs

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| task | TEXT | user task |
| start_url | TEXT | |
| config_json | JSON | max_pages, depth, domains, resolved_defaults, prompt_versions |
| status | ENUM | running, completed, partial, not_found, blocked, failed, **canceled** |
| intent | TEXT | classified task intent (contact, pricing, …) — runtime-поле RunRecord |
| current_url | TEXT | последняя посещённая страница (CLI-поллинг) |
| result_json | JSON | ExtractionResult nullable until done |
| **metadata_json** | JSON | violation aggregates (doc 13), vision flags (doc 23), llm stats — **колонка добавлена: на неё ссылались docs 13/23, в схеме отсутствовала** |
| pages_visited | INT | |
| started_at | TIMESTAMP | |
| finished_at | TIMESTAMP | nullable |
| error_message | TEXT | nullable |
| session_id | UUID FK | nullable; set when run from Research Agent (doc 24) |

### research_sessions (Phase 3)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| title | TEXT | auto from first message |
| status | ENUM | active, running_tools, comparing, completed, failed |
| comparison_result_json | JSON | ComparisonResult nullable |
| config_json | JSON | max_sites, rubric override |
| created_at | TIMESTAMP | |
| finished_at | TIMESTAMP | nullable |

### session_messages (Phase 3)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| session_id | FK | |
| role | ENUM | user, assistant, system, tool |
| content | TEXT | |
| tool_calls_json | JSON | nullable |
| created_at | TIMESTAMP | |

### crawl_steps

| Column | Type | Notes |
|--------|------|-------|
| run_id | FK | PK = (run_id, **seq**) |
| seq | INT | позиция в step-логе; `step_index` может повторяться (OBSERVE и ACT одного шага) |
| step_index | INT | логический номер шага цикла |
| state | TEXT | OBSERVE, PLAN, ACT, ... |
| url | TEXT | current page |
| action / target_url / note | TEXT | executed action (плоские колонки вместо action_json) |
| screenshot_paths_json | JSON | `{profile: relative_path}` — мульти-профиль (doc 22/23), вместо одиночного screenshot_path |
| llm_reasoning | TEXT | from PLAN |
| contract_violations | JSON | [] if clean |
| duration_ms | INT | |
| llm_stats_json | JSON | nullable; `eval_count`, `eval_duration`, `prompt_eval_count` из ответа Ollama — бесплатная телеметрия для тюнинга (doc 20) |

Full PageSnapshot → `artifacts/{run_id}/steps/{index:03d}.json` (optional, configurable). After vision batch (Phase 2): same file includes **`vision_insights[]`** (doc 23).

## SQLite settings

- **WAL mode** (`PRAGMA journal_mode=WAL`) — CLI-поллинг читает во время записи шагов без блокировок
- `busy_timeout` 5 s

## Startup sweep (zombie runs)

Crash/рестарт бэкенда оставляет runs в `status: running` навечно — и глобальный run lock (D-12) был бы занят навсегда. Поэтому при старте приложения:

```
UPDATE crawl_runs
  SET status='failed', error_message='orphaned: backend restart'
  WHERE status='running';
UPDATE research_sessions
  SET status='failed'   -- + пометка canceled_by_restart в config_json
  WHERE status IN ('running_tools', 'comparing');
```

Run lock — **производный от БД** (нет строк `running` → свободен), не in-memory флаг. Собранные шаги/артефакты осиротевшего run сохраняются (`runs show` работает). Resume из checkpoint — backlog P2 (doc 06).

## Retention

| Policy | MVP |
|--------|-----|
| Max runs stored | No auto-delete |
| User delete | `agent runs delete <id>` |
| Snapshot artifacts | On by default; `--no-artifacts` flag to save DB only |

## API mapping

| Operation | Storage |
|-----------|---------|
| POST /runs | Insert crawl_runs, status=running |
| Each step | Insert crawl_steps + optional artifact file |
| Run complete | Update result_json, status, finished_at |
| GET /runs/{id} | Join run + steps summary |
| GET /runs/{id}/result | result_json only |
| GET /runs/{id}/steps/{index}/screenshot | PNG file (doc 22) |
| POST /sessions | Insert research_sessions (doc 24) |
| POST /sessions/{id}/messages | Message + meta-agent run |
| GET /sessions/{id} | Session + messages + runs + comparison |
| DELETE /sessions/{id} | Session + linked artifacts |

## Privacy

- All local; no encryption at rest in MVP
- Sensitive URLs/tasks — user responsibility
- Delete run removes DB row + artifact folder

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial crawl run storage design |
| 2026-07-05 | screenshots/ artifacts; crawl_steps.screenshot_path (doc 22) |
| 2026-07-05 | Step artifacts: vision_insights after vision batch (doc 23) |
| 2026-07-05 | **v0.2:** research_sessions, session_messages; crawl_runs.session_id (doc 24) |
| 2026-07-05 | **v0.3 (review):** crawl_runs.metadata_json (referenced by docs 13/23 but missing); status canceled; crawl_steps.llm_stats_json (Ollama eval telemetry); SQLite WAL |
| 2026-07-05 | **v0.4 (review-2):** startup sweep для zombie runs (running → failed при рестарте); run lock производный от БД |
| 2026-07-18 | **v0.5 (Phase 2 impl):** SqliteRunStore реализован. crawl_runs + intent, current_url (runtime-поля RunRecord); crawl_steps: PK (run_id, seq) — step_index неуникален (OBSERVE+ACT), action/target_url/note плоскими колонками, screenshot_paths_json (мульти-профиль) вместо screenshot_path; legacy JSON Phase 1 автоимпортируется в БД (файлы → `legacy_json/`); `DELETE /runs/{id}` + `agent runs delete` (retention); result.json пишется в artifacts при финальном статусе |
