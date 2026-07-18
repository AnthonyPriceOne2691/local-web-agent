# 17 — UI Screens (CLI + Future Web)

> Local Web Agent · Design doc · **v0.3.1** · 2026-07-05

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

## Phase 4: Research Chat UI

### Screens

```
[New Crawl]  [Runs]  [Settings]

New Crawl:
  - URL input
  - Task textarea
  - Advanced: max pages, depth, allow external
  - [Start] → live step feed

Run detail:
  - Status badge
  - Step timeline (url, action, reasoning)
  - Vision badge per step (ok / skipped / failed)
  - Screenshot thumbnails (desktop + mobile tabs)
  - Result card (facts + evidence expand; source dom/vision/both)
  - Design panel (colors swatches, layout notes)
  - Export JSON / Markdown
  - Cancel run (while running) — FR-3.8
  - Delete run

Settings:
  - Default limits
  - Ollama model names
  - Data directory
```

### Tech (if built)

- React + Vite + Tailwind (consistent with voice-interview-coach)
- Poll REST or SSE
- **No WebSocket required** — crawl is async job, not streaming chat

### Out of scope for Web UI

- Real-time browser view (too heavy)
- Editing prompts in UI (edit files in `data/prompts/`)

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | CLI flows MVP; Web UI draft Phase 3 |
| 2026-07-05 | **v0.2:** design audit flow; --vision progress; report/design CLI; Web UI vision badges |
| 2026-07-05 | **v0.3:** Flow 5 Research Chat primary UX; Phase 4 (doc 24) |
| 2026-07-05 | **v0.3.1 (review):** Cancel run в Run detail (FR-3.8) |
