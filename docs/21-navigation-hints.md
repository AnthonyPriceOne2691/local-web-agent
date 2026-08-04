# 21 — Navigation Hints (deterministic site access)

> Local Web Agent · Design doc · **v0.10** · 2026-08-04
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

## Link scoring (extends doc 04) — v0.8 после испытания T-3d

```
score(link, intent) =
  # СОДЕРЖАНИЕ (тема главнее формы)
  +20  if тема задачи есть в тексте ссылки ИЛИ в словах пути (`/stavki-na-futbol`)
  +8   if форма записи И тема совпала           (форма разрешает ничью между
  +4   if форма записи без темы                  тематическими, но не заменяет её)
  +6   if текст похож на заголовок (>=4 слов, >=25 симв.) и мы ищем статью
  -4   if текста нет вовсе И темы нет            (модель не может о ней судить)
  # ВХОД В РАЗДЕЛ (работает только пока раздел ещё не найден)
  +15  if на главной И (текст или href совпал с ключевиками интента)
  +12  if на главной И href совпал со слугом словаря
  +8   if intent=contact И href совпал с юридическим слугом
  +3   if малая глубина пути И это НЕ поиск статьи
  # ЖАНР (только при поиске статьи — content_search)
  +10  if обучающий жанр И тема совпала   (wiki/school/academy/guide/гайд/обучен…)
  +4   if обучающий жанр без темы          (жанр усиливает тему, но не заменяет)
  -10  if промо И сама задача про промо НЕ спрашивает (bonus/фрибет/розыгрыш…)
  # ШТРАФЫ (признак ищется в ПУТИ, не во всём URL)
  -8   if путь юридический И intent != contact
  -10  if путь in (login, signup, cart, checkout)
```

**Форма записи** (`entry`): дата в пути, числовой id, длинный слуг из 3+ слов, `.html`.
Признаки структурные — они описывают форму URL записи, одинаковую у блогов, новостных
лент и вики, а не подогнаны под конкретные сайты.

### Почему веса именно такие (замер T-3d, doc 26)

Три реальных портала со статьями про ставки: агент прошёл раздел -> раздел -> раздел, не
открыл ни одной статьи и заявил, что статей нет. Две причины, обе измерены:

1. **`slug` и `shallow` достаются страницам-спискам**, а ссылка на статью получала 0:
   её заголовок не совпадал с задачей буквально, а путь — ни с одним слугом. Поэтому
   слуг и малая глубина теперь работают только пока раздел не найден: внутри раздела они
   уводили в соседний раздел (news -> бонусы -> букмекеры).
2. **Первая попытка починки дала форме больше веса, чем теме** (`entry` +12 против
   `task-kw` +10) — и агента потянуло в турниры, теги и видео: они тоже «длинный слуг из
   трёх слов». В top-10 стояли шесть ссылок с пустым текстом, о которых модель не может
   сказать ничего. Отсюда правило: **тема главная, форма только разрешает ничью**, а
   нечитаемая ссылка получает штраф.

Тема ищется **с начала слова и по префиксу >=4 символов** (`matching`): «ставки» обязано
ловить «ставках». И ищется не только в тексте ссылки, но и **в словах пути** — на живом
прогоне половина кандидатов имела пустой текст.

### Тема ищется и в транслитерированном пути (T-3g)

Правка T-3d учила искать тему **в словах пути** — но у русских сайтов путь записан
латиницей, а задача приходит по-русски, и на таких путях признак темы не срабатывал
**вообще**. Замер: `sports.ru/betting/stavochnaya-wiki` (эталонная вики про ставки) стояла
**#134 из 731** со счётом 11 — текст ссылки пуст, путь латинский, поэтому ссылка получала
только `homepage+intent` и штраф `blind`. Десятое место того же корня стоило 37.

Слова задачи транслитерируются одной схемой (`app/navigation/matching.py`) и сопоставляются
с путём. Схемы у сайтов разные (`ц` → c/ts, `х` → h/kh), но спасает то, что тема ищется
**префиксом от 4 символов**: первые четыре символа у схем совпадают (`ставки` → stav…,
`футбол` → futb…, `школа` → shko…). Таблица — алфавит, а не политика, поэтому живёт в коде.

**Цена, названная прямо:** префикс правую границу слова не проверяет, поэтому «ставки»
совпадает и со «Ставрополем». Это **уже** было так для кириллицы (половина словаря —
стемы), транслитерация нового класса ошибки не вносит. Ужесточение до полного слова
сломало бы `stavochnaya`, то есть ровно тот случай, ради которого правка сделана.

Обратная сторона: служебные слова задачи после транслитерации начали ловить чужие пути —
`статью` → `stat` совпадало с `/stat/football`, и страница статистики становилась «по теме».
Поэтому слова задачи фильтруются словарём `task_stopwords`; он **уже существовал** в
sitemap-фильтре внутри кода и переехал в `data/navigation/path_hints.yaml` — один словарь
на двух потребителей.

### Обучающий жанр против промо (T-3g)

Задача «как делать ставки на футбол» просит **обучающий** материал, а формула не отличала
его ни от новости, ни от бонусной акции. У промо есть и тема («ставки»), и форма записи, и
длинный заголовок — поэтому на корне букмекерского обзорника промо занимало **девять мест
из десяти** и вытесняло раздел «Школа беттинга» (#20 из 285).

Два словаря в `data/navigation/path_hints.yaml`: `learn_markers` (`wiki`, `school`,
`academy`, `guide`, `гайд`, `обучен`, `инструкц`, `знаний`…) и `promo_markers` (`bonus`,
`фрибет`, `розыгрыш`, `акци`, `cashback`…). Оба работают только при `content_search`.

**Штраф промо выключается, если промо и есть запрос** («найди бонусы букмекеров») — иначе
правка ломала бы законный сценарий; на это есть тест.

**Вес жанра двойной — 10 при теме, 4 без.** Первая версия давала +10 безусловно, и замер
сразу показал цену: `championat.com/guide/lifestyle` (жанр есть, темы нет, текст пуст)
поднялся на #9 корня и вытеснил статью про ставки из top-10. Это **та же ошибка «форма выше
темы», что в T-3d**, повторённая на другом признаке. Правило общее для всей формулы: признак
формы или жанра **усиливает** тему, но не заменяет её.

Итог замера на 8 снятых страницах (критерий объявлялся до правки):

| Сайт | хаб к статьям | до | после |
|---|---|---|---|
| `legalbet.ru` | `/shkola-bettinga` | #20 (43) | **#1** (53) |
| `www.sports.ru` | `/betting/stavochnaya-wiki` | #134 (11) | **#4** (45) |
| `www.championat.com` | `/bets/article-…` | #10 (31) | #10 (31) |

Доля тематических ссылок в top-10 не упала ни на одной странице, на двух корнях выросла
(3/10 → 4/10 и 5/10 → 6/10). **Чего правка не лечит:** на самой странице-хабе
`legalbet.ru/shkola-bettinga/` эталонная статья про футбол стоит #26 — её вытесняют
соседние «Как делать ставки в БК X», которые тому же жанру и теме удовлетворяют. Жанр
раздела правку получил, выбор **внутри** раздела — нет.

### Штрафы смотрят путь, а не весь URL (T-3e)

Найдено офлайн-оракулом на корне `legalbet.ru`: штраф `legal-avoid` (−8) стоял у **каждой**
ссылки сайта, потому что подстрока `/legal` совпадает внутри `//legalbet.ru`. Тот же класс
ошибки, что `ui` внутри `g-ui-de` (T-3a): признак сравнивался с целым URL вместо пути.
Так же ловились `//cartier` на `/cart` и `//logincorp` на `/login`.

На порядок очереди этих трёх сайтов правка **не влияет** — штраф был одинаков для всех
ссылок хоста, поэтому ранжирование внутри страницы не менялось (замер: top-10 не сдвинулся
ни на одной из 8 страниц). Она важна там, где счёт сравнивается **между источниками**:
ссылки закэшированной homepage попадают в P1 только с положительным счётом, и запись,
у которой осталась одна форма (+8), обнулялась штрафом и выпадала.

Запрос сознательно не смотрим: штраф про то, что страница **является** корзиной или
входом, а не про параметр `?next=/login` у обычной ссылки.

### Отбор — по счёту, а не по позиции в DOM

LLM PLAN получает **top 10** scored candidates (href + text + score + reason).

Сколько ссылок доходит до оценки — предохранитель по памяти (`LINKS_CAP`), **не** отбор.
Замер T-3d показал, почему позиционный лимит неверен в принципе: ссылки берутся в порядке
DOM, а позиция содержимого у каждого сайта своя. У `sports.ru/betting/stavochnaya-wiki`
420 ссылок; при лимите 40 в вход попадали только шапка и меню (50 из 52 тематических
отброшены), при лимите 300 — всё равно мимо, потому что ссылки на статьи лежат на
позициях #345-#351. **Любое фиксированное N режет контент на каком-нибудь сайте.**

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
| 2026-08-04 | **v0.8 (испытание T-3d, doc 26):** § Link scoring переписан — **тема главнее формы**. Причина измерена: на трёх реальных порталах агент ходил раздел -> раздел -> раздел и не открыл ни одной статьи, потому что `slug`/`shallow` достаются спискам, а ссылка на статью получала 0. Слуг и малая глубина теперь работают только пока раздел не найден; введены `entry` (форма URL записи), `headline` (заголовок против навигационной подписи) и штраф за ссылку без читаемого текста; тема ищется префиксом >=4 символов и **в словах пути** тоже. Отдельно записано, что первая попытка починки дала форме больше веса, чем теме, и агента потянуло в турниры/теги/видео. § Отбор — по счёту, а не по позиции в DOM: позиционный лимит неверен в принципе (у `sports.ru` статьи на позициях #345-#351, любое фиксированное N режет контент) |
| 2026-08-04 | **v0.10 (починка первого хопа, doc 26 § T-3g):** две новых секции. **§ Тема ищется и в транслитерированном пути** — у русских сайтов путь латиницей, задача по-русски, и признак темы не срабатывал вовсе (`sports.ru/betting/stavochnaya-wiki` стояла #134 из 731 со счётом 11); слова задачи транслитерируются, служебные отсекаются словарём `task_stopwords`, который переехал из кода `sitemap.py` в data и стал общим на двух потребителей. Цена названа: префикс не проверяет правую границу, поэтому «ставки» ловит и «Ставрополь» — так уже было для кириллицы. **§ Обучающий жанр против промо** — словари `learn_markers`/`promo_markers` в data; штраф промо выключается, когда промо и есть запрос; вес жанра двойной (10 при теме, 4 без), потому что безусловный +10 поднял `/guide/lifestyle` на #9 корня — та же ошибка «форма выше темы», что в T-3d. Замер по объявленному заранее критерию: хаб к статьям в top-10 на всех трёх корнях (#20 → #1, #134 → #4, #10 → #10), доля тематических не упала нигде |
| 2026-08-04 | **v0.9 (офлайн-замер цепочки, doc 26 § T-3e):** § Штрафы смотрят путь, а не весь URL — `/legal` совпадало внутри `//legalbet.ru` и снимало 8 очков у **каждой** ссылки сайта-обзорника (так же `//cartier` на `/cart`, `//logincorp` на `/login`). Названо, чего правка НЕ лечит: порядок очереди на этих сайтах не сдвинулся ни на одной из 8 страниц, потому что штраф был одинаков для всех ссылок хоста; она важна там, где счёт сравнивается между источниками (P1 берёт ссылки homepage только с положительным счётом) |
