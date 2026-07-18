# 05 — Extraction Schema

> Local Web Agent · Design doc · **v0.4** · 2026-07-05

## Назначение

Единый формат **выходных данных** crawl run: что агент нашёл, откуда, насколько уверен. Схема используется в R1 synthesis pass, CLI output и REST API.

## Top-level: ExtractionResult

```json
{
  "schema_version": 1,
  "run_id": "uuid",
  "task": "Find enterprise pricing",
  "start_url": "https://example.com",
  "status": "completed",
  "summary": "Enterprise pricing is custom; contact sales@example.com",
  "facts": [],
  "not_found": [],
  "pages_visited": 4,
  "duration_seconds": 127,
  "generated_at": "2026-07-05T12:05:00Z"
}
```

### status enum

| Value | Meaning |
|-------|---------|
| `completed` | Task answered with at least one high-confidence fact |
| `partial` | Some info found; task not fully satisfied |
| `not_found` | No relevant facts; explicit not_found entries |
| `blocked` | captcha / login / robots |
| `failed` | Technical failure |
| `canceled` | User cancel (FR-3.8); partial trace сохранён, synthesis пропущен |

## Fact

```json
{
  "key": "enterprise_pricing",
  "label": "Enterprise plan price",
  "value": "Custom pricing — contact sales",
  "confidence": "high",
  "evidence": [
    {
      "url": "https://example.com/pricing",
      "quote": "Enterprise: Contact us for a custom quote",
      "selector_hint": "h2:Plans + section enterprise",
      "screenshot_path": "screenshots/002_pricing.png"
    }
  ]
}
```

### confidence rules

| Level | Criteria |
|-------|----------|
| `high` | Verbatim DOM quote supports value **OR** DOM + vision cross-validated same value |
| `medium` | Vision-only visible fact; inferred from context; multiple weak signals |
| `low` | Ambiguous; degraded vision; include but flag in report |

**Hard rule (contract):** no `high` without DOM quote **unless** cross-validated (doc 13 S-H6). Vision-only → **medium** max.

### evidence.source

| source | quote required | screenshot_path |
|--------|----------------|-----------------|
| `dom` (default) | yes for high | optional |
| `vision` | no; use `vision_insight_ref` | recommended |
| `both` | DOM quote + vision ref | yes |

## not_found

When task asked for X but agent couldn't find it:

```json
{
  "key": "eu_office_address",
  "label": "EU office address",
  "reason": "No office locations page; only US address in footer",
  "pages_checked": ["https://example.com/contact", "https://example.com/about"]
}
```

Prefer explicit `not_found` over silent omission — reduces hallucination.

## Free-form vs structured tasks

### Free-form (MVP default)

User task is natural language. R1 decides which `facts[]` keys to emit based on task. Keys are snake_case slugs derived from content.

### Structured (P1)

Optional `--schema contacts.json` — user provides desired fields:

```json
{
  "fields": [
    {"key": "sales_email", "description": "Email for sales inquiries"},
    {"key": "enterprise_price", "description": "Enterprise tier pricing"}
  ]
}
```

R1 maps snapshots → required keys; missing → `not_found`.

## Regex assist (P1)

Pre-LLM extractors run on `main_text`:

| Pattern | Emits |
|---------|-------|
| Email regex | candidate facts `email_*` |
| Phone regex | candidate facts `phone_*` |
| Price patterns `$X/mo` | candidate facts `price_*` |

Candidates passed to R1 as hints — **R1 validates** and attaches evidence; raw regex alone never produces `high` confidence.

## page_types & design (Phase 2)

`design_tokens` populated from **`vision_insights[].design`** (doc 23) when vision enabled; fallback DOM heuristics only if vision skipped.

```json
{
  "page_types": [
    {"url": "...", "type": "pricing", "confidence": "high", "screenshot_paths": {"desktop": "...", "mobile": "..."}}
  ],
  "url_patterns": [" /blog/{slug}", "/products/{id}" ],
  "design_tokens": {
    "primary_colors": ["#1a1a2e"],
    "fonts": ["Inter, sans-serif"],
    "notes": "Fixed header, card grid on homepage",
    "reference_screenshots": {
      "desktop": ["screenshots/001_home_desktop.png"],
      "mobile": ["screenshots/001_home_mobile.png"]
    }
  }
}
```

## article (Phase 3 — UC-2, doc 24)

Optional block when crawl finds target article page:

```json
{
  "article": {
    "url": "https://competitor.com/blog/football-betting-guide",
    "title": "Complete Guide to Football Betting",
    "word_count": 2840,
    "headings": ["Introduction", "Odds formats", "Leagues", "FAQ"],
    "main_text_excerpt": "... up to 12000 chars for compare pass ...",
    "published_date": "2024-03-15",
    "page_type_confidence": "high"
  },
  "article_candidates_considered": [
    {"url": "https://competitor.com/blog/betting-tips-2023", "rejected_reason": "shorter, no FAQ/tables"}
  ]
}
```

`article` — **лучшая** из ≤ `max_article_candidates: 3` найденных статей (R1 выбирает в synthesis; doc 21 § article candidates); отклонённые — в `article_candidates_considered[]` для прозрачности. Used as input to `compare_results` rubric `content_completeness`.

---

## ComparisonResult (Phase 3 — doc 24)

Output of **Compare Synthesizer** across N crawl runs:

```json
{
  "schema_version": 1,
  "session_id": "uuid",
  "comparison_task": "Which competitor has the most complete football betting article?",
  "rubric": "content_completeness",
  "status": "completed",
  "excluded": [
    {"start_url": "https://z.com", "reason": "blocked: captcha"}
  ],
  "winner": {
    "run_id": "...",
    "start_url": "https://x.com",
    "label": "x.com",
    "reason": "Longest article with FAQ, odds tables, and league examples"
  },
  "rankings": [
    {"run_id": "...", "url": "https://x.com", "score": 92, "summary": "..."},
    {"run_id": "...", "url": "https://y.com", "score": 61, "summary": "..."}
  ],
  "dimensions": [
    {"name": "depth_sections", "scores": {"x.com": 9, "y.com": 5}},
    {"name": "data_examples", "scores": {"x.com": 10, "y.com": 4}}
  ],
  "narrative": "Site x.com wins because ...",
  "generated_at": "2026-07-05T..."
}
```

For `comparative_design` rubric `design_diff`: `winner` optional; focus on `dimensions` (colors, layout, mobile) + `narrative` diff story.

`excluded[]` — сайты, не дошедшие до compare (blocked/failed/timeout): compare идёт по ≥2 выжившим (M-H4, doc 24 § Partial failure); в отчёте и chat reply исключение называется явно.

Stored in `research_sessions.comparison_result_json` and `artifacts/{session_id}/comparison_report.md`.

---

## Comparison report template (doc 24)

```markdown
# Comparison Report

**Task:** {comparison_task} · **Sites:** {N} · **Rubric:** {rubric}

## Conclusion
{narrative}

## Winner
{winner.label}: {winner.reason}

## Rankings
| Site | Score | Summary |
|------|-------|---------|
| x.com | 92 | ... |

## Design differences
<!-- design_diff rubric: table per dimension -->

## Per-site details
<!-- links to individual crawl reports -->
```

---

## Markdown report template (single-site)

**Оптимальный UX:** три блока — Findings (факты), Design (если vision), Appendix (vision/diagnostics).

```markdown
# Crawl Report: {task}

**URL:** {start_url} · **Status:** {status} · **Pages:** {pages_visited} · **Vision:** {vision_pages_analyzed}/{vision_calls_total} calls

## Summary
{summary}

## Findings

### {label} ({confidence}) · source: {dom|vision|both}
{value}

> "{quote}" — [{url}]({url})  
> _Vision (desktop): {vision_description_snippet}_ — optional if source=vision|both

## Design analysis
<!-- omitted if no design_tokens and no vision_insights -->

**Colors:** {primary_colors joined}  
**Layout:** {layout notes from design_tokens}  
**Responsive:** {responsive_note from mobile vision}

| Viewport | Screenshot |
|----------|------------|
| Desktop | ![desktop]({path}) |
| Mobile | ![mobile]({path}) |

## Not found
- {label}: {reason}

## Appendix: vision diagnostics
<!-- only if vision_failures > 0 or vision_partial -->

| Step | URL | Profile | Status | Note |
|------|-----|---------|--------|------|
| 2 | /pricing | desktop | ok | — |
| 4 | /blog | mobile | skipped | cap exceeded |

_Screenshots are relative to `artifacts/{run_id}/`. Open report from that folder for images to render._
```

### Report generation rules

| Rule | Behavior |
|------|----------|
| Embed PNG | Relative paths only; same directory as `report.md` in artifacts |
| Vision snippet | Max 120 chars from `vision_insights[].description` |
| Hide empty Design | Skip section if `design_audit` intent false and no design fields |
| Appendix | Show when `vision_failures > 0` OR `vision_skipped_pages` non-empty |
| Blocked run | No Findings; Summary explains blocker; Appendix optional |

---

## Validation (Pydantic)

Backend validates R1 output against schema before saving. Malformed JSON:

1. Retry R1 once with error message
2. Fallback: wrap best-effort parse + `status: partial`

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial extraction schema |
| 2026-07-05 | evidence.screenshot_path; page_types / design_tokens; report embeds PNG |
| 2026-07-05 | design_tokens source: vision_insights (doc 23) |
| 2026-07-05 | **v0.2:** evidence.source; confidence vision rules; report UX (Findings/Design/Appendix) |
| 2026-07-05 | **v0.3:** article block; ComparisonResult; comparison report (doc 24) |
| 2026-07-05 | **v0.3.1 (review):** status `canceled` (FR-3.8) |
| 2026-07-05 | **v0.4 (review-2):** `schema_version` в ExtractionResult/ComparisonResult; `article_candidates_considered[]` (лучшая из ≤3, doc 21); `ComparisonResult.excluded[]` (partial failure, doc 24) |
