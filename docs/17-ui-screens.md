# 17 — UI Screens (CLI + Future Web)

> Local Web Agent · Design doc · **v0.4** · 2026-07-19

## MVP: CLI (Phase 1–3) → Chat UI (Phase 4, primary UX)

Web UI **не в Layer 1 MVP**. **Research Chat** — целевой интерфейс продукта с Phase 4 ([doc 24](24-research-chat-agent.md)). До этого: `agent crawl` и `agent research`.

---

## CLI flows

### Flow 1: Start crawl (blocking)

```
$ agent crawl --url https://acme.com --task "Find sales email"

Local Web Agent v0.1
Task: Find sales email
Start: https://acme.com
Limits: 10 pages, depth 2

[1/10] https://acme.com          → navigate → /contact
[2/10] https://acme.com/contact  → extract_now
[3/10] synthesizing...

Status: completed (3 pages, 42s)

Summary: Sales contact is sales@acme.com

Findings:
  • sales_email (high): sales@acme.com
    Evidence: "Email us at sales@acme.com" — /contact

Saved: data/runs/abc123/result.json
```

### Flow 2: Design audit (vision + multi-viewport)

```
$ agent crawl --url https://acme.com \
  --task "Audit design: colors, layout, mobile vs desktop" \
  --report report.md

[1/10] https://acme.com              → navigate → /pricing
[2/10] https://acme.com/pricing      → extract_now
[3/10] vision batch (4 calls: 2 pages × desktop+mobile+tablet on home)...
[4/10] synthesizing...

Status: completed (2 pages, 78s, vision 4/4 ok)

Summary: Blue primary (#2563eb); card grid desktop; hamburger mobile.

Design:
  • primary_colors: #2563eb, #ffffff
  • layout: three-column pricing cards, sticky header

Report: data/runs/def456/report.md  (open folder for images)
```

### Flow 3: Background crawl + poll

```
$ agent crawl --url ... --task "..." --no-wait
Run started: abc123
Poll: agent runs show abc123

$ agent runs show abc123 --watch   # Phase 2: refresh every 2s
```

### Flow 4: History

```
$ agent runs list

 ID       STATUS      PAGES  TASK                          STARTED
 abc123   completed   3      Find sales email              2h ago
 def456   blocked     1      Get pricing                   1d ago

$ agent runs show abc123 --steps
$ agent runs show abc123 --vision     # Phase 2: vision_insights summary per step
```

---

## CLI components (Rich)

| Component | Use |
|-----------|-----|
| `Progress` | Page counter [N/max] |
| `Spinner` | LLM planning / synthesis |
| `Table` | runs list |
| `Panel` | Summary + findings + design block |
| `Syntax` | JSON output optional |
| `Markdown` | `--report` file preview path in done message |

---

### Flow 5: Research Chat (Phase 4 — primary)

```
┌─────────────────────────────────────────────┐
│ You: a.com b.com c.com d.com                │
│      Compare design of each                 │
├─────────────────────────────────────────────┤
│ Agent: Design audit site 1/4 (a.com)…       │
│        ████████░░░░                           │
│ Agent: [table of differences]                 │
│        Open comparison_report.md              │
├─────────────────────────────────────────────┤
│ [ URLs or message…                  ] [Send] │
└─────────────────────────────────────────────┘
```

Side panel: linked runs, screenshot thumbs, per-site reports.

---

## Phase 4: Research Chat UI — реализовано (2026-07-19)

**Стек (факт):** React 19 + Vite 7 + TypeScript + Tailwind CSS v4 (`frontend/`). Prod: `npm run build` → `frontend/dist`, FastAPI монтирует на `/` (same-origin, CORS не нужен). Dev: `npm run dev` (5173) c proxy `/sessions|/runs|/health` → 8001.

### Layout (три колонки)

```
┌─ Sidebar ─────┬─ Chat ────────────────────────┬─ Side panel ──────────┐
│ + New chat    │ header: title·status·Cancel   │ tabs: Runs|Comparison │
│ session list  │ messages (user/assistant/⚙)   │ Runs: RunCard         │
│  (status,     │ CrawlProgress bar (SSE)       │  status·intent·pages  │
│   runs count, │ "Comparing…" spinner          │  steps timeline       │
│   delete ✕)   │ composer (Enter=send)         │  screenshot thumbs    │
│               │ welcome: UC-1/UC-2 примеры    │ Comparison: winner,   │
│               │                               │  rankings bars,       │
│               │                               │  dimensions table,    │
│               │                               │  narrative, excluded, │
│               │                               │  Export report.md     │
└───────────────┴───────────────────────────────┴───────────────────────┘
```

### Компоненты (`frontend/src/`)

| Файл | Ответственность |
|------|-----------------|
| `App.tsx` | state-holder: sessions/current/runs/progress; SSE attach/detach; send/cancel/delete |
| `api.ts` | REST-клиент + `subscribeSessionEvents` (EventSource, дедуп реплея по `message.index`) |
| `types.ts` | зеркала Pydantic-схем (SessionRecord, RunRecord, ComparisonResult, SSE events) |
| `components/Sidebar.tsx` | список сессий, New chat, delete |
| `components/Chat.tsx` | лента, ProgressCard, composer, welcome-примеры UC-1/UC-2 |
| `components/Message.tsx` | user/assistant баблы; tool-notes (M-S1) компактной строкой ⚙ |
| `components/SidePanel.tsx` | табы Runs / Comparison |
| `components/RunCard.tsx` | статус, steps timeline, скриншот-тумбы (`/runs/{id}/steps/{pos}/screenshot`) |
| `components/ComparisonView.tsx` | winner, rankings, dimensions-таблица, narrative, excluded, экспорт `report.md` |
| `components/StatusBadge.tsx` | цветовые статусы session/run |

### Поведение

- SSE `GET /sessions/{id}/events` (протокол — doc 15 v0.6); источник правды — `GET /sessions/{id}`: на `done` и tool-notes UI рефетчит сессию/runs.
- Cancel session (FR-3.8) из header; ошибки API (409 busy/run_in_progress) — красный баннер.
- **No WebSocket** — SSE poll pattern (exit doc 06). EventSource сам реконнектит; реплей дедупится.

### Out of scope for Web UI

- Real-time browser view (too heavy)
- Editing prompts / settings in UI (edit files in `data/prompts/`, env `LWA_*`)
- Отдельный «New Crawl» экран для Layer 1 — single-site задача решается тем же чатом (один URL → `single_site` intent)

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | CLI flows MVP; Web UI draft Phase 3 |
| 2026-07-05 | **v0.2:** design audit flow; --vision progress; report/design CLI; Web UI vision badges |
| 2026-07-05 | **v0.3:** Flow 5 Research Chat primary UX; Phase 4 (doc 24) |
| 2026-07-05 | **v0.3.1 (review):** Cancel run в Run detail (FR-3.8) |
| 2026-07-19 | **v0.4 (Phase 4 impl):** Chat UI реализован — React 19 + Vite 7 + TS + Tailwind v4 в `frontend/`; трёхколоночный layout (sidebar / chat+SSE progress / side panel Runs+Comparison со скриншотами и экспортом report.md); prod = статика из FastAPI, dev = Vite proxy; черновые экраны New Crawl/Settings заменены фактической структурой (single-site — через тот же чат) |
