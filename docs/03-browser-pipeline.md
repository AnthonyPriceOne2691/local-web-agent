# 03 — Browser Pipeline

> Local Web Agent · Design doc · **v0.9** · 2026-08-03

## Назначение

Как браузер **открывает**, **ждёт** и **наблюдает** страницу — и что попадает в LLM. Аналог voice pipeline (STT → LLM → TTS), но цикл **observe → decide → act**.

## Pipeline overview

```
User task + start URL
        │
        ▼
┌───────────────┐     ┌────────────────┐     ┌──────────────┐
│ Fetch tier    │────▶│ Page Observer  │────▶│ PageSnapshot │
│ F2 Playwright │     │ extract DOM    │     │ (for LLM)    │
│ (MVP)         │     └────────────────┘     └──────┬───────┘
└───────────────┘                                   │
        ▲                                            ▼
        │                              ┌─────────────────────────┐
        └ validated action ────────────│ CandidateQueue + LLM    │
                                       │ (top-K only, doc 21)    │
                                       └─────────────────────────┘
```

> **Two-tier fetch (Phase 2):** F1 `httpx` probe (12s, 500 KB cap, https→http fallback) → F2 Playwright on 403/empty DOM. Ref: SEOLB contact scraper — [21-navigation-hints.md](21-navigation-hints.md).

## Playwright configuration (MVP)

### Navigation context (always desktop)

| Setting | Value | Why |
|---------|-------|-----|
| Browser | Chromium headless | Best JS support |
| **Navigation viewport** | **1440×900** (`desktop`, doc 22) | Stable nav, footer links, LLM snapshot |
| User-Agent | Desktop Chromium default | Consistent with viewport |
| Timeout navigation | 30 s | FR NFR-4.2 |
| Wait strategy | `commit` на бюджет навигации + `domcontentloaded` на **5 s** + 1 s settle | Документ обязателен, событие — нет: DOMContentLoaded держат чужие `defer`-скрипты |
| JavaScript | Enabled | Required for modern sites |
| Images / fonts | Load (default) | Lazy-loaded blocks |
| Cookies | Fresh context per run | No session persistence |
| Downloads | Block | Security |

> **Screenshots** могут сниматься в **desktop + tablet + mobile** на той же странице — см. [22-page-screenshots.md](22-page-screenshots.md). Навигация и DOM для LLM — **только desktop**.

### SPA / heavy JS sites

```
goto(url)
  → wait commit (бюджет навигации, 30 s)      # документ пришёл — иначе честное падение
  → wait domcontentloaded (бюджет 5 s, best-effort)
  → wait 1000ms (settle)
  → if main_text length < 200:
        wait networkidle (timeout 10s)
  → observe
  → if main_text STILL < 200:
        force desktop screenshot (даже при capture_screenshots=never)
        # «SPA fallback capture» — иначе vision-правилу R2 (doc 23) нечего анализировать
```

## Page Observer

### Extraction strategy (DOM-first)

| Field | Source | Limit |
|-------|--------|-------|
| `title` | `document.title` | 200 chars |
| `meta_description` | `<meta name="description">` | 300 chars |
| `headings` | `h1, h2, h3` innerText | max 20 items, 200 chars each |
| `main_text` | heuristic: `main`, `[role=main]`, `article`, else `body`; **content_search Phase 2: `trafilatura`** (см. ниже) | **8000 chars** (see doc 20) |
| `links` | `a[href]` visible text + resolved href | max **40** links per page |
| `breadcrumbs` | `[aria-label=breadcrumb]`, `.breadcrumb` | optional, 500 chars |
| `screenshot` | Playwright PNG after settle (if enabled) | see [22-page-screenshots.md](22-page-screenshots.md) |

### Link normalization

- Resolve relative URLs to absolute
- Drop: `mailto:`, `tel:`, `javascript:`, `#` only anchors
- Flag `same_domain` vs external (registrable domain match)
- Dedupe by normalized href

### URL normalization rules (canonical — visited set, dedupe, contract checks)

Одна функция `normalize_url()` (DRY, doc 18) для observer, visited set, CandidateQueue и enforcer:

| Rule | Example |
|------|---------|
| Lowercase scheme + host | `HTTPS://Example.COM` → `https://example.com` |
| Strip fragment | `/pricing#faq` → `/pricing` |
| Strip tracking params | `utm_*`, `gclid`, `fbclid`, `yclid`, `ref` (whitelist остальных query) |
| Trailing slash | Normalize to no-slash except root (`/about/` ≡ `/about`) |
| Default port | `:443`/`:80` dropped |
| Registrable domain (OQ-2) | `tldextract` (offline PSL snapshot); `www.x.com` ≡ `blog.x.com` ≡ `x.com` по умолчанию |

### Redirect policy (I-H9, doc 13)

После каждого `goto` — re-check финального URL:

| Redirect target | Action |
|-----------------|--------|
| Same registrable domain | OK; visited set учитывает **оба** URL (запрошенный + финальный) |
| Off-domain | Snapshot **не** сохраняется; URL → `redirect_offsite`; следующий кандидат |
| Private network / non-http(s) (I-H8) | То же + violation log |
| **Off-domain на step 0 (первая навигация)** | **Adopt:** `allowed_domains` переопределяются от landing URL + warning в лог/CLI («site.com → site.io») — иначе переезд домена мгновенно убивал бы run. I-H8 применяется всё равно |

### Main-text quality: trafilatura для content_search (Phase 2)

Fallback `else body` тянет меню/футеры → раздутый `word_count` и замусоренный `main_text_excerpt`, а на них строится сравнение полноты статей (UC-2). Для страниц `page_type: article`:

- **`trafilatura`** (офлайн, заточена под извлечение статейного текста + метаданных, включая `published_date`) — экстрактор article-текста;
- hand-rolled эвристика остаётся для быстрого OBSERVE в навигационном цикле;
- Phase 0 spike: сравнить `word_count` эвристики vs trafilatura на 2–3 реальных блогах — если дельта < 15%, trafilatura можно отложить.

### Blockers detection

| Signal | Status |
|--------|--------|
| URL contains `/login`, password field visible | `login_wall` |
| Cloudflare challenge text / cf-browser-verification | `captcha` |
| HTTP 4xx/5xx | `error` |
| Empty main_text + many scripts | `spa_loading` → retry once |

## PageSnapshot schema

```json
{
  "url": "https://example.com/pricing",
  "fetched_at": "2026-07-05T12:00:00Z",
  "status": "ok",
  "title": "Pricing",
  "meta_description": "...",
  "headings": [{"level": 1, "text": "Plans"}],
  "main_text": "...",
  "links": [
    {"href": "https://example.com/contact", "text": "Contact Sales", "same_domain": true}
  ],
  "screenshots": [
    {"profile": "desktop", "relative_path": "screenshots/001_pricing_desktop.png", "width": 1440, "height": 900, "full_page": false, "bytes": 198400}
  ],
  "viewport_navigation": "desktop",
  "char_count": 4521,
  "truncated": false
}
```

## Memory budget per page

| Component | RAM ~ |
|-----------|-------|
| Chromium tab | 100–300 MB |
| Snapshot text in Python | < 1 MB |
| LLM context (snapshot + history) | see doc 20 |

**Rule:** one tab per run in MVP; close page between navigations if memory spikes (measure Phase 0).

## Latency budget (single step)

| Stage | Target |
|-------|--------|
| Playwright goto + wait | 1–4 s |
| DOM extract | < 200 ms |
| Screenshot PNG (per viewport) | < 350 ms |
| 3 viewports (design audit) | < 1.2 s total |
| LLM navigation decision | 3–8 s |
| Contract check | < 10 ms |
| **Total per step** | **5–12 s** |

10 pages → **~1–2 min** browser + **~1–3 min** LLM → aligns with NFR-1.3 (< 5 min).

## robots.txt integration

```
Before first navigation to domain:
  1. Fetch https://{domain}/robots.txt (cache per run)
  2. Parse with urllib.robotparser or robotexclusionrulesparser
  3. Before each URL: if disallowed for our UA or * → skip + log
  4. Crawl-delay (if present): max(rate_limit_ms, crawl_delay) — cap 10 s
  5. Sitemap: directives → передать в CandidateQueue (doc 21, Phase 2)

Fetch outcomes:
  200 → parse; 4xx (incl. 404) → allow all (стандарт)
  5xx / timeout → retry 1× через 2 s → если снова fail: proceed + log
  (персональный tool с rate limit — блокироваться на весь run из-за flaky robots не стоит)
```

MVP User-agent string: `LocalWebAgent/0.1 (personal research tool; +https://localhost)`

> **Реализация (real-site прогон 2026-08-01):** robots.txt запрашивает **наш**
> httpx-клиент с этим самым UA, а `urllib.robotparser` используется только как
> парсер директив. Причина: `RobotFileParser.read()` ходит через `urllib` с
> дефолтным `Python-urllib/3.x`, реальные сайты отвечают на такой UA **403**, а
> stdlib трактует 401/403 как `disallow_all`. В результате `docs.astro.build`, у
> которого в robots.txt написано `Allow: /`, давал `robots_disallow` и ноль
> страниц — агент сообщал «сайт просил не ходить», хотя сайт просил обратное.
> Контракт выше («4xx → allow») теперь выполняется буквально, включая 401/403:
> правил нам не выдали — значит запрета нет. Настоящий `Disallow` уважается
> по-прежнему; на фикстурах (`127.0.0.1`) robots не запрашивается вовсе, поэтому
> дефект был невидим для юнитов.

> **UA policy (зафиксировать):** robots.txt проверяем для `LocalWebAgent` **и** `*` (строже из двух). Сами запросы: Playwright ходит с дефолтным Chromium UA (иначе ломаются SPA), F1 `httpx` — browser-like UA (SEOLB). Это стандартная практика, не «bypass»: мы не обходим блокировки, а выглядим как обычный браузер пользователя.

## Error handling

| Error | Action |
|-------|--------|
| Navigation timeout | Log; **retry once** after 2s (SEOLB: transient ≠ missing) |
| Navigation timeout (2×) | Skip to next CandidateQueue URL |
| SSL error | Stop run with message (no `--ignore-ssl` in MVP) |
| Browser crash | Restart browser once; else fail run |
| Observer exception | Snapshot with `status: error`; continue if possible |

## Vision analysis (D-6b)

Screenshot **capture** — Phase 1 ([doc 22](22-page-screenshots.md)).  
**Analysis** — Phase 2 ([doc 23](23-vision-analysis.md)):

```
artifacts/.../screenshots/*.png
  → VisionLoader.read_base64()
  → VisionAnalyzer (qwen2.5vl:7b) → VisionInsight JSON
  → PageSnapshot.vision_insights[]
  → R1 SYNTHESIZE (text only, no images)
```

Не в hot navigation loop — batch после crawl, до R1.

## Phase 2: HTTP probe tier (F1)

Before Playwright slug navigation:

```
httpx GET url
  → timeout 12s, max body 500 KB, browser-like UA, follow_redirects
  → if https fails → try http
  → if 403 / empty text / captcha header → escalate F2 Playwright
  → else parse links for CandidateQueue (doc 21)
```

Not in Phase 1 MVP (Playwright-only).

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial browser pipeline; DOM-first MVP |
| 2026-07-05 | **v0.2:** two-tier fetch plan (F1 httpx / F2 Playwright), retry policy; ref doc 21 |
| 2026-07-05 | **v0.3:** page screenshots in OBSERVE (doc 22); vision LLM split to Phase 3 |
| 2026-07-05 | **v0.4:** navigation viewport desktop 1440×900; screenshot profiles desktop/tablet/mobile |
| 2026-07-05 | **v0.5:** vision analysis → doc 23 (Phase 2); removed Phase 3 stub |
| 2026-07-05 | **v0.6 (review):** canonical URL normalization rules (tracking params, tldextract); redirect policy I-H9; robots Crawl-delay + Sitemap discovery + UA policy; SPA fallback capture (форс-скриншот при пустом DOM для vision R2); версия шапки синхронизирована с changelog |
| 2026-07-05 | **v0.7 (review-2):** landing-domain adopt на step 0 (переезд домена не убивает run); robots fetch 4xx/5xx семантика; trafilatura для article main-text (content_search, Phase 0 spike-решение) |
| 2026-08-01 | **v0.8 (real-site прогон):** § robots.txt integration — чтение robots нашим httpx-клиентом с UA `LocalWebAgent/0.1`; контракт «4xx → allow» выполняется буквально, включая 401/403 (stdlib трактовал их как `disallow_all` и давал ложный `robots_disallow` на сайте с `Allow: /`); stdlib остаётся парсером директив |
| 2026-08-03 | **v0.9 (испытание T-3a, doc 26):** § Wait strategy — бюджет навигации тратится на `commit` (документ), а DOMContentLoaded получает отдельный короткий бюджет **5 s** и больше не может уронить переход. Причина найдена замером: DOMContentLoaded ждёт и **отложенных** (`defer`) скриптов, поэтому один зависший сторонний хост держит событие до сетевого таймаута — `simonwillison.net` 31.0 s из-за `static.cloudflareinsights.com`, `martinfowler.com` 30.9 s из-за `cloud.umami.is`, при `commit` за 0.7 s у обоих. На старой стратегии это стоило **2 сайтов из 3** (0 страниц, run `failed`) и 46 % времени сессии. Недостижимый документ по-прежнему падает — на это есть отдельный тест |
