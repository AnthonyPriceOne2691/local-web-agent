# 21 — Navigation Hints (deterministic site access)

> Local Web Agent · Design doc · **v0.7** · 2026-07-18
> **Референс (боевой опыт):** Linkbuilding CRM — [CONTACT_SCRAPER_FALLBACK_DESIGN.md](../../../Shared%20Works/internal/seo/hide-linkbuilding-application-crm/Linkbuilding%20Automatization%20P/docs/CONTACT_SCRAPER_FALLBACK_DESIGN.md) (SEOLB-499, прогон 991 GEO-донора, 2026-07-03/04)

## Назначение

**Navigation Intelligence Layer** — детерминированные эвристики «как попасть на нужный раздел сайта», дополняющие LLM и ABC-контракты.

| Слой | Отвечает на |
|------|-------------|
| **Navigation hints** (этот doc) | *Куда логично идти?* — словари путей, порядок кандидатов |
| **LLM PLAN** | *Какой из top-K кандидатов лучше для task?* |
| **Contract Enforcer** (doc 13) | *Можно ли выполнить действие?* |

Промпт и LLM **не должны угадывать** `/page/kontak` или `/hubungi-kami` — это знает словарь. LLM выбирает among **scored candidates**, не invent URL.

## Что доказано в Linkbuilding (не про email)

На 991 GEO-доноре скрейп **удвоил** успех нахождения контактных страниц. Прирост дала **навигация**, не regex:

| # | Приём | Суть |
|---|--------|------|
| 1 | **Главная первой** | Footer/меню/шапка уже в HTML — не deep crawl сразу |
| 2 | **Ссылки с главной** | Contact-ссылки на homepage приоритетнее slug-guess |
| 3 | **Локализованные slug'и** | `/kontak`, `/page/kontak`, `/hubungi-kami`, `/redaksi`, `/اتصل`, `/ติดต่อ` |
| 4 | **Legal-страницы** | `/terms`, `/privacy`, `/syarat-ketentuan` — operator contact (для contact-задач) |
| 5 | **page_budget + порядок** | Локализованные пути **до** лимита; `pages[:10]` — баг |
| 6 | **Early stop** | После 1–2 релевантных страниц — хватит |
| 7 | **HTTP → Playwright** | Браузер только при 403 / пустом DOM / JS |
| 8 | **Retry** | Транзиентный timeout ≠ «страницы нет» |

**Не переносим:** email regex, Cloudflare decode, OCR, Hunter verify, mass batch.

---

## Архитектура: hybrid navigation

```
Task
  → classify task_intent (contact | pricing | about | careers | docs | generic)
  → NavigationHints.load(path_hints.yaml)
  → INIT: normalize to site root if task is site-wide
  → OBSERVE homepage
  → build CandidateQueue:
       (1) links from page matching intent keywords
       (2) slug probes from path_hints[intent]
       (3) optional legal slugs if intent=contact
  → score + dedupe + respect page_budget ORDER
  → PLAN: LLM picks among top-K candidates only
  → VALIDATE → ACT
  → early stop if sufficient evidence
```

**Инвариант:** LLM `navigate.url` ∈ **CandidateQueue** ∪ `{current_url}` — совместимо с contract I-H6.

---

## Task intent classification

MVP: keyword matching on user `task` (no extra LLM call). **Matching: casefold + substring; словарь двуязычный EN+RU** (стемы: «ваканс», «стоимост») — задачи пользователя формулируются по-русски (UC-1/UC-2), EN-only ключи роняли всё в `generic`. Ключи — в `path_hints.yaml § intent_keywords`, не в коде.

| Intent | Task keywords (examples) | Primary hints |
|--------|--------------------------|---------------|
| `contact` | contact, email, phone, sales, support, reach | contact + legal slugs |
| `pricing` | pricing, price, plan, enterprise, cost | pricing, commercial |
| `about` | about, team, company, who we are | about, impressum |
| `careers` | jobs, careers, hiring, work with us | careers |
| `docs` | documentation, api, developer, docs | docs, developer |
| `site_map` | map site, page types, all sections, structure | broad crawl + sitemap |
| `design_audit` | design, layout, colors, fonts, ui, look | homepage + key pages; **screenshots auto** (doc 22) |
| **`content_search`** | article, blog, guide, найди текст, ставки, betting | blog/docs slugs; **max_pages 12** (doc 24 UC-2) |
| `generic` | (default) | about + contact (light) |

Implementation: `backend/app/navigation/intent.py` — pure function, unit-tested.

---

## Task intents matrix (defaults)

**Оптимальный принцип:** intent задаёт **navigation hints + capture/vision defaults**. Переопределяется CLI/API flags.

| Intent | Keywords (sample) | `capture_screenshots` | `screenshot_viewports` | `vision_enabled` | Key pages only | `max_vision_pages` |
|--------|-------------------|----------------------|------------------------|------------------|----------------|-------------------|
| `contact` | contact, email, phone, sales | `never` | — | `never` | yes (homepage + priority) | 3 |
| `pricing` | pricing, price, plan, cost | `auto` | desktop | `auto` | yes | 3 |
| `about` | about, team, company | `never` | — | `never` | yes | 2 |
| `careers` | jobs, careers, hiring | `never` | — | `never` | yes | 2 |
| `docs` | documentation, api, developer | `never` | — | `never` | yes | 2 |
| `site_map` | map site, page types, structure | `auto` | desktop | `never` | no (all visited desktop) | 10 |
| **`design_audit`** | design, layout, colors, fonts, ui | **`always`** | **all** | **`always`** | no (all visited) | ∞ (cap calls) |
| **`content_search`** | article, blog, guide, betting, ставки | `never` | — | `never` | yes | 0 |
| `generic` | (default) | `never` | — | `auto` | yes | 3 |

### `auto` resolution order

```
1. Explicit CLI/API flags win (--vision, --screenshots, --screenshot-viewports)
2. Else task_intent row from matrix above
3. Else generic row
4. vision_enabled auto still applies R2 empty-DOM rule (doc 23) on any intent
```

### Examples

| User task | Detected intent | Screenshots | Vision |
|-----------|-----------------|-------------|--------|
| «Find sales email» | contact | off | off |
| «Get enterprise pricing» | pricing | desktop on priority pages | homepage + pricing if priority |
| «Map all main sections» | site_map | desktop every page | off |
| «Audit colors and mobile layout» | design_audit | all viewports all pages | all profiles all pages |
| «Find football betting article» | content_search | off | off (DOM text for compare) |
| «Find HQ city» | generic | off | off unless DOM empty |

---

## Research intents (Layer 2 — doc 24)

Meta-agent level; maps to per-site crawl plans:

| Research intent | User pattern | Per-site sub-intent | Compare rubric |
|-----------------|--------------|---------------------|------------------|
| `comparative_design` | N URLs + design / отличия | `design_audit` | `design_diff` |
| `comparative_content` | N URLs + find article + compare | `content_search` | `content_completeness` |
| `multi_site_research` | N URLs + generic task | from keywords | `generic_merge` |
| `single_site` | 1 URL | direct Layer 1 | — |

Resolved defaults stored in `crawl_runs.config_json.resolved_defaults` and session config for reproducibility.

---

## Candidate queue (ordering)

**Критично (урок SEOLB §9):** порядок кандидатов фиксирован **до** `page_budget`. Никогда не обрезать head списка наивным slice после сортировки по алфавиту.

```
Priority (lower = earlier):
  P0  Unvisited links ON current snapshot where link.text OR href matches intent keywords
  P1  Unvisited links ON homepage snapshot (cached) — same match
  P2  Slug probes: path_hints[intent] × origin — only if not in visited
  P2.5 Sitemap URLs matching intent (Phase 2, см. ниже)
  P3  Slug probes: path_hints.contact_legal — ONLY if intent=contact
  P4  Remaining same-domain links from snapshot (scored lower)
```

**Slug probe:** `GET` or Playwright `goto(origin + slug)` — только если URL не в visited и robots allow.

**Hop depth:** slug probes и sitemap-кандидаты считаются **depth 1** (прямой переход из очереди) — max_depth ограничивает переходы, не форму URL (doc 04 policy #2).

**Budget clarification:** очередь кандидатов может быть длиннее бюджета — в бюджет `max_pages` (default **10**) входят только фактические визиты. Урок SEOLB (`page_budget: 14`, баг `pages[:10]`): нельзя наивно слайсить *очередь* — локализованные slug'и P2 должны получить шанс до исчерпания бюджета визитов. Отдельного параметра `page_budget` нет — это тот же `max_pages`.

---

## Sitemap tier (Phase 2 — P2.5)

Дешёвый детерминированный источник URL, особенно для `content_search` (UC-2) и `site_map`:

```
INIT (после robots.txt):
  1. sitemap URLs из robots.txt `Sitemap:` директив
  2. fallback: {origin}/sitemap.xml, /sitemap_index.xml
  3. httpx GET (F1 tier), parse <loc>; sitemap index → до 3 вложенных sitemap
  4. cap: 500 <loc> URLs; same registrable domain only
  5. filter по intent:
       content_search → <loc> содержит task keywords или /blog|/article|/news|/guides
       остальные intents → match против path_hints[intent] slugs
  6. top-N (по keyword score) → CandidateQueue P2.5
```

| Param | Default |
|-------|---------|
| `use_sitemap` | `auto` (on для content_search, site_map; off для остальных) |
| `sitemap_max_urls` | 500 parsed / **20** в queue |
| `sitemap_timeout_ms` | 8000 |

**Зачем:** для «найди статью про X» блог-статья часто недостижима с homepage за depth 2 (пагинация, infinite scroll — MVP не скроллит). Sitemap решает это одним запросом. RSS (`/feed`, `/rss.xml`) — опциональный доп. источник для content_search, backlog Phase 5.

**Contract:** sitemap URLs входят в CandidateQueue ⊂ I-H6 (doc 13); robots + same-domain проверки применяются как обычно.

---

## Link scoring (extends doc 04)

```
score(link, intent) =
  +15  if link on homepage AND (text or href matches intent keywords)
  +12  if href path matches path_hints slug for intent
  +10  if link.text matches task keywords verbatim
  +8   if intent=contact AND href matches legal slug (path_hints.contact_legal)
  +5   if href path matches generic intent keywords
  +3   if shorter path depth
  -8   if href matches crawl_forbidden.txt AND intent ≠ contact
  -10  if href ∈ (login, signup, cart, checkout) unless task asks
  -5   if similar path prefix already visited
```

LLM PLAN получает **top 10** scored candidates (href + text + score + reason), не все 40 links.

---

## Homepage-first normalization

| Condition | Start URL |
|-----------|-----------|
| Task site-wide («find pricing on this site») | `{scheme}://{host}/` |
| Task mentions specific section + user gave deep URL | user `start_url` |
| `start_url` is deep link but intent generic | fetch root first, then user path if budget allows |

Config: `normalize_to_root: auto | always | never` (default `auto`).

---

## Two-tier fetch (Phase 2)

| Tier | When | How |
|------|------|-----|
| **F1 HTTP** | Default first pass on slug probe | `httpx`, UA browser-like, timeout 12s, body cap 500 KB, follow redirects, https→http fallback |
| **F2 Playwright** | HTTP 403 / empty main_text / captcha signal | Existing browser pipeline (doc 03) |

MVP Phase 1: Playwright only. Phase 2: HTTP for slug probe batch before browser.

Flag: `use_http_probe: true` (Phase 2), `escalate_to_browser: true`.

---

## Early stop

| Signal | Action |
|--------|--------|
| LLM `extract_now` + `confidence: high` | Mark page priority → optional one more confirm page → SYNTHESIZE |
| ≥ **2** pages with intent keyword in title/h1 | Orchestrator may force `stop` (config `early_stop_min_pages: 2`) |
| `pages_visited >= page_budget` | Hard stop (orchestrator) |
| Candidate queue exhausted | SYNTHESIZE partial |

### content_search: article candidates (не первая попавшаяся)

Вопрос UC-2 — «у кого **самая полная** статья», а не «у кого есть хоть какая-то». Early stop на первой статье систематически искажал бы ответ: у конкурента может быть 10 статей по теме.

| Rule | Behavior |
|------|----------|
| Найдена страница `page_type: article` | **Не** останавливаться; пометить `priority_snapshot`, продолжать по кандидатам |
| Собрано `max_article_candidates` (default **3**) | stop → SYNTHESIZE |
| Queue exhausted / budget | stop с тем, что есть |
| Sitemap tier (P2.5) | Главный поставщик кандидатов: keyword-match по `<loc>` даёт список статей сразу |
| SYNTHESIZE | R1 выбирает **лучшую** из кандидатов; она уходит в `article`-блок (doc 05); остальные — в `article_candidates_considered[]` (url + причина отклонения) |

---

## Retry on transient failure

| Failure | Action |
|---------|--------|
| Navigation timeout (1×) | Retry same URL once after 2s |
| HTTP 5xx | Skip to next candidate |
| Empty snapshot, status ok | Retry with networkidle (doc 03) |

SEOLB: retry loop дал ~+21 донор на перепроверке.

---

## Data file: `data/navigation/path_hints.yaml`

Канонический словарь slug'ов — см. файл в repo. Категории:

- `contact` — локализованные contact paths (SEA, MENA, EU, EN)
- `contact_legal` — terms/privacy/disclaimer (boost только для intent=contact)
- `about`, `pricing`, `careers`, `docs`, `commercial`
- `blog` — blog/article/news paths для `content_search` (UC-2)

Расширение: PR добавляет slug'и; не хардкодить в Python.

---

## Module layout

```
backend/app/navigation/
├── intent.py           # task → intent enum
├── path_hints.py       # load YAML, slug probes for origin
├── candidate_queue.py  # P0–P4 ordering, page_budget safe
├── link_scorer.py      # score(link, intent, context)
└── early_stop.py       # stop heuristics
```

---

## Integration points

| Consumer | Uses |
|----------|------|
| `orchestrator/loop.py` | CandidateQueue, early stop |
| `orchestrator/plan.py` | top-K to LLM prompt |
| `contracts/enforcer.py` | allowed URLs = queue ∪ visited links |
| `browser/http_probe.py` | F1 tier (Phase 2) |

---

## Phase mapping

| Item | Phase |
|------|-------|
| `path_hints.yaml` + intent + link_scorer | **1** |
| CandidateQueue + homepage-first | **1** |
| LLM top-K only (not raw 40 links) | **1** |
| early_stop | **2** |
| HTTP probe tier (F1) | **2** |
| Playwright escalate (F2) | **2** |
| **Sitemap tier (P2.5)** | **2** |
| RSS feed source (content_search) | 5+ backlog |
| Site-search probe (`/?s=`, `/search?q=`) — требует contract-исключения для сконструированных query-URL | 5+ backlog |
| GEO slug expansion from SEOLB runs | ongoing |

---

## Phase 0 benchmark extension

Добавить 2 fixture-сайта с локализованными путями ( `/kontak`, `/page/kontak` ) и сравнить:

| Mode | Metric |
|------|--------|
| LLM-only navigation | pages to answer, success |
| **Hints + LLM top-K** | pages to answer, success |

Gate: hints mode ≤ same pages, ≥ same success on localized fixtures.

---

## Requirements mapping

| Requirement | Navigation hints |
|-------------|------------------|
| FR-1.1 max pages | Candidate queue respects budget order |
| FR-4.5 link scoring | Extended scorer (this doc) |
| FR-2.6 multi-page aggregation | Early stop + priority snapshots |
| I-H6 no fabricated URLs | Queue-bound LLM candidates |

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | v0.1: Navigation Intelligence Layer from SEOLB contact scraper design |
| 2026-07-05 | v0.2: intents site_map, design_audit; screenshots auto for design (doc 22) |
| 2026-07-05 | **v0.3:** full intents matrix — capture/vision defaults; resolution order |
| 2026-07-05 | **v0.4:** content_search intent; research intents Layer 2 (doc 24) |
| 2026-07-05 | **v0.5 (review):** Sitemap tier P2.5 (robots `Sitemap:` → CandidateQueue) — закрывает пагинацию/infinite-scroll для UC-2; page_budget = max_pages (уточнение); RSS и site-search probe в backlog; `blog:` slugs добавлены в path_hints.yaml |
| 2026-07-05 | **v0.6 (review-2):** RU+EN intent keywords (casefold+substring, стемы) — EN-only роняло русские задачи в generic; hop depth для slug/sitemap кандидатов (D-13); content_search — до 3 article candidates вместо первой попавшейся |
| 2026-07-18 | **v0.7 (Phase 2 exit-бенчмарк):** docs-класс расширен на contributor-страницы — keywords `develop`/`contribut` (стемы: developer/development/contribute/contributing) + RU `разработ`/`вклад`, slugs `/dev`, `/contribute`, `/contributing` (кейс python.org: «contribute to CPython development» падал в generic). Sitemap P2.5 и полный F1 tier реализованы; стоп-слова task-keywords для sitemap-фильтра (about/find/article… не сигнал в `<loc>`) |
