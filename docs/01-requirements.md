# 01 — Requirements

> Local Web Agent · Design doc · **v0.5.1** · 2026-07-20

## Функциональные требования

### FR-0 Core agent loop

| ID | Требование | MVP | Priority |
|----|------------|-----|----------|
| FR-0.1 | Пользователь задаёт **natural language task** + **start URL** | ✅ | P0 |
| FR-0.2 | Агент открывает страницу в headless browser | ✅ | P0 |
| FR-0.3 | Агент **наблюдает** страницу: title, headings, main text, links | ✅ | P0 |
| FR-0.4 | Агент **решает** следующее действие: navigate / extract / stop | ✅ | P0 |
| FR-0.5 | Агент переходит по **внутренним ссылкам** того же домена (same-origin policy configurable) | ✅ | P0 |
| FR-0.6 | Агент возвращает **structured result** + **evidence** (URL, snippet) | ✅ | P0 |
| FR-0.7 | Полный **audit trail** каждого шага (observe → decide → act) | ✅ | P0 |
| FR-0.8 | **Page screenshots** — Playwright PNG; profiles **desktop / tablet / mobile** (doc 22) | ✅ | P0 |
| FR-0.9 | **Vision analysis:** загрузить PNG → local VLM → `vision_insights` (doc 23) | ✅ | P0 (Phase 2) |
| FR-0.10 | Vision insights merged в SYNTHESIZE вместе с DOM | ✅ | P0 (Phase 2) |

### FR-1 Navigation & scope

| ID | Требование | MVP | Priority |
|----|------------|-----|----------|
| FR-1.1 | **Max pages** per run (default 10, configurable) | ✅ | P0 |
| FR-1.2 | **Max depth** from start URL (default 2) — **hop depth**: навигационные переходы, не сегменты URL-пути (doc 04 policy #2) | ✅ | P0 |
| FR-1.3 | **Same-domain only** by default; cross-domain — opt-in flag | ✅ | P0 |
| FR-1.4 | Respect **robots.txt** (fetch + parse; disallow → skip; **Crawl-delay honored, cap 10 s**) | ✅ | P0 |
| FR-1.5 | **Rate limit**: min delay between page loads (default 1 s) | ✅ | P0 |
| FR-1.6 | Skip non-HTML: PDF, images, zip (log + optional extract URL only) | ✅ | P1 |
| FR-1.7 | Handle JS-rendered pages (Playwright wait for network idle / selector) | ✅ | P0 |
| FR-1.8 | Login / auth walls — detect and stop with clear message | ✅ | P1 |
| FR-1.9 | CAPTCHA / Cloudflare — detect and stop (no bypass) | ✅ | P0 |
| FR-1.10 | **Homepage-first** + slug path hints для навигации (ref SEOLB) | ✅ | P0 |
| FR-1.11 | LLM выбирает только among **top-K scored candidates**, не произвольный URL | ✅ | P0 |
| FR-1.12 | **Sitemap.xml** как источник кандидатов (robots `Sitemap:` → CandidateQueue P2.5, doc 21) | ✅ Phase 2 | P1 |
| FR-1.13 | **Private network / non-http(s) blocked** (SSRF guard, I-H8 doc 13) | ✅ | P0 |
| FR-1.14 | **Off-domain redirect** обнаружен и отброшен (I-H9 doc 13); исключение — первая навигация: allowed_domains деривятся от landing URL (переезд домена) | ✅ | P0 |

### FR-2 Extraction

> См. [05-extraction-schema.md](05-extraction-schema.md)

| ID | Требование | MVP | Priority |
|----|------------|-----|----------|
| FR-2.1 | Free-form task → agent fills **ExtractionResult** schema | ✅ | P0 |
| FR-2.2 | Each fact includes **source_url** + **evidence_text** | ✅ | P0 |
| FR-2.3 | **Confidence** score per field (high / medium / low) | ✅ | P0 |
| FR-2.4 | «Not found» — явный статус, не галлюцинация | ✅ | P0 |
| FR-2.5 | Predefined extractors: emails, phones, addresses (regex assist) | partial | P1 |
| FR-2.6 | Multi-page aggregation (merge facts from several URLs) | ✅ | P0 |
| FR-2.7 | Export: JSON, Markdown report | ✅ | P0 |
| FR-2.8 | Export: CSV | ❌ | P2 |

### FR-3 Interface

| ID | Требование | MVP | Priority |
|----|------------|-----|----------|
| FR-3.1 | **CLI**: `crawl`, `runs list`, `runs show <id>` | ✅ | P0 |
| FR-3.2 | **REST API**: start run, poll status, get result | ✅ | P0 |
| FR-3.3 | Live progress in CLI (step N/M, current URL) | ✅ | P0 |
| FR-3.4 | Web UI (React) | ❌ | P2 |
| FR-3.5 | `--screenshots` / `--no-screenshots`; просмотр в `runs show` | ✅ | P1 |
| FR-3.6 | `--screenshot-viewports` desktop/tablet/mobile (doc 22) | ✅ | P1 |
| FR-3.7 | `--vision` / `--no-vision`; vision в design_audit по умолчанию (doc 23) | ✅ | P1 |
| FR-3.8 | **Cancel run/session**: `POST /runs/{id}/cancel`, `agent runs cancel` — partial trace сохраняется | ✅ | P1 |

### FR-6 Research Chat Agent (Layer 2)

> См. [24-research-chat-agent.md](24-research-chat-agent.md)

| ID | Требование | MVP | Priority |
|----|------------|-----|----------|
| FR-6.1 | **Chat** или CLI: N URLs + natural language task | ✅ | P0 (Phase 4 / 3 CLI) |
| FR-6.2 | Meta-agent **tool calls** only: crawl_site, compare_results, get_run | ✅ | P0 (Phase 3) |
| FR-6.3 | **Sequential** multi-site crawl queue (no parallel on M5) | ✅ | P0 (Phase 3) |
| FR-6.4 | **Compare synthesis** → ComparisonResult + narrative | ✅ | P0 (Phase 3) |
| FR-6.5 | UC-1: comparative design across sites | ✅ | P0 (Phase 3) |
| FR-6.6 | UC-2: find article + rank by completeness | ✅ | P0 (Phase 3) |
| FR-6.7 | Research Session persistence (messages, runs, comparison) | ✅ | P1 (Phase 3) |
| FR-6.8 | SSE/progress events during tool execution | partial | P1 (Phase 4) |

### FR-4 Behavioral contracts (ABC — arXiv:2602.22302)

> См. [13-behavioral-contracts.md](13-behavioral-contracts.md) · источник: `/Users/anthony/Documents/2602.22302v1.pdf`

| ID | Требование | MVP | Priority |
|----|------------|-----|----------|
| FR-4.1 | **Contract Enforcer** проверяет каждое действие агента **перед execution** | ✅ | P0 |
| FR-4.2 | Hard: never submit forms / POST / login — **граница Tier 1/Tier 2** (doc 25): submit/login **не автономно**; автономный Tier 1 `click` по не-submit элементу разрешён (FR-7.3) | ✅ | P0 |
| FR-4.3 | Hard: stay within allowed domain(s) | ✅ | P0 |
| FR-4.4 | Hard: max pages / max depth enforced by orchestrator, not LLM | ✅ | P0 |
| FR-4.5 | Soft: prefer shorter paths to answer (link scoring heuristic) | partial | P1 |
| FR-4.6 | Violation logging in run metadata | ✅ | P1 |
| FR-4.7 | `*.contract.yaml` in `data/contracts/` (ContractSpec-lite, paper §5) | ✅ | P1 |
| FR-4.8 | `data/navigation/path_hints.yaml` — slug dictionaries ([doc 21](21-navigation-hints.md)) | ✅ | P0 |
| FR-4.9 | Legal pages (`/privacy`, `/terms`) — **boost** when intent=contact, soft avoid otherwise | ✅ | P1 |

### FR-5 Storage & history

> См. [12-session-storage.md](12-session-storage.md)

| ID | Требование | MVP | Priority |
|----|------------|-----|----------|
| FR-5.1 | Persist each **crawl run** with full step log | ✅ | P0 |
| FR-5.2 | Optional page snapshot (truncated DOM text, not full HTML) | ✅ | P0 |
| FR-5.3 | List / inspect past runs | ✅ | P1 |
| FR-5.4 | Delete run | ✅ | P1 |
| FR-5.5 | Full HTML archive | ❌ | P2 |

### FR-7 Action Framework (агент действует на сайте) — Phase 6

> См. [25-action-framework.md](25-action-framework.md). Ось **автономность × обратимость**: автономно на обратимом, подтверждение на необратимом.

| ID | Требование | MVP | Priority |
|----|------------|-----|----------|
| FR-7.1 | **Реестр действий** (Action registry): агент выполняет только зарегистрированные типизированные действия (A-H1) | 🛠 | P1 (Phase 6) |
| FR-7.2 | **Tier 0 sink** — доставка результата наружу (файл, Google Docs); действие «наружу» требует явного user-consent (A-H4) | 🛠 | P1 (Phase 6) |
| FR-7.3 | **Tier 1 safe interaction** — автономный `click` по **не-submit / не-login** элементу (раскрыть, пагинация) по индексу ∈ `snapshot.interactive_elements` | 🛠 | P1 (Phase 6) |
| FR-7.4 | **Tier 2 consequential** — login: attended-пауза (человек логинится сам, паролей не храним) ✅; submit форм — под подтверждением (след. срез) | 🛠 | P2 (Phase 6) |
| FR-7.5 | **Tier 3 destructive** — купить/удалить/отправить: агент **не** выполняет, только готовит (A-H3) | 🔲 | P2 |
| FR-7.6 | **Element referencing** — `PageSnapshot.interactive_elements` с устойчивой нумерацией (спайк A-1) | ✅ | P1 (Phase 6) |

## Нефункциональные требования

### NFR-1 Performance & latency

| ID | Требование | Target |
|----|------------|--------|
| NFR-1.1 | Single page load + observe | **< 5 s** (typical site) |
| NFR-1.2 | LLM decision step (navigation) | **< 8 s p50 / < 10 s p95** warm (согласовано с doc 19/20) |
| NFR-1.3 | Full run (10 pages, simple task) | **< 5 min** wall time |
| NFR-1.4 | First run (cold browser + model load) | **< 30 s** overhead acceptable |

> Latency некритична как в voice loop; важнее **correctness + traceability**.

### NFR-2 Privacy & storage

| ID | Требование |
|----|------------|
| NFR-2.1 | LLM inference **только локально** (Ollama) |
| NFR-2.2 | Нет телеметрии / analytics в MVP |
| NFR-2.3 | Crawl data хранится локально в `data/runs/` |
| NFR-2.4 | Явное удаление runs; no cloud sync |
| NFR-2.5 | REST API bind **только 127.0.0.1** (no auth → не светить в LAN) |

### NFR-3 Platform

| ID | Требование |
|----|------------|
| NFR-3.1 | macOS Apple Silicon (M5), 32 GB RAM |
| NFR-3.2 | Playwright Chromium bundled |
| NFR-3.3 | Ollama models укладываются в 512 GB SSD |
| NFR-3.4 | Работа без VPN / без зарубежных API в MVP |

### NFR-4 Reliability

| ID | Требование |
|----|------------|
| NFR-4.1 | Run не теряется при crash — checkpoint после каждого step |
| NFR-4.2 | Timeout per page (default 30 s) → skip + log |
| NFR-4.3 | Graceful stop on OOM: reduce context / abort run |
| NFR-4.4 | **Global concurrency = 1 активный crawl** (D-12): второй `POST /runs` → 409; иначе 2×(Chromium+14B) = OOM |

### NFR-5 Legal & ethics

| ID | Требование |
|----|------------|
| NFR-5.1 | robots.txt respected by default |
| NFR-5.2 | User responsible for ToS compliance — disclaimer in CLI |
| NFR-5.3 | No credential stuffing, no CAPTCHA bypass |
| NFR-5.4 | PII extraction — user-initiated only; no bulk personal data harvesting mode |

### NFR-6 Code quality & tests

> Детали: [18-engineering-standards.md](18-engineering-standards.md)

| ID | Требование | Target |
|----|------------|--------|
| NFR-6.1 | Размер модуля: один исходный файл | **≤ 500 LOC** |
| NFR-6.2 | SOLID: слои, DI, интерфейсы Browser/LLM/Store | обязательно |
| NFR-6.3 | DRY: prompts/contracts в `data/`, не в коде | обязательно |
| NFR-6.4 | Unit + integration tests; LLM/Browser — mocks | обязательно |
| NFR-6.5 | Backend coverage `app/` | ≥ 85% к концу Phase 2 |
| NFR-6.6 | Contract enforcer + orchestrator | ≥ 90–95% coverage |

## Out of scope (MVP)

- Multi-tenant / auth
- Distributed crawling / queue workers
- CAPTCHA solving
- Login automation — **пересмотрено (Phase 6):** Tier 2 (submit/login под attended-подтверждением, doc 25), **не автономно**
- Cloud LLM fallback
- Mobile app
- Real-time collaborative UI
- Automatic scheduled crawls (cron) — post-MVP

## Open questions

| # | Вопрос | Статус |
|---|--------|--------|
| OQ-1 | Web UI в Phase 2 или Phase 3? | ✅ **Phase 4 Chat UI**; Phase 3 = `agent research` CLI (doc 24) |
| OQ-2 | Same registrable domain vs strict same-origin? | ✅ **Closed: same registrable domain** via `tldextract` + offline PSL snapshot (doc 03 § URL normalization); `www`/`blog` субдомены included by default |
| OQ-3 | Store full HTML or truncated text only? | ✅ Truncated text MVP; HTML P2 |
| OQ-4 | Cookie-banner dismissal для design audit (D-11)? | ✅ **Closed:** detect → CSS-hide (default, без согласия) → CMP-click reject-first fallback; Phase 1 honest capture (doc 22) |
| D-6b | Vision VLM **`qwen2.5vl:7b`** + loader/analyzer | ✅ **design closed** ([doc 23](23-vision-analysis.md)); benchmark Phase 2 |
| **D-7** | Multi-site execution | ✅ **sequential queue only** ([doc 24](24-research-chat-agent.md)) |
| **D-8** | Two-layer architecture | ✅ Layer 2 Research Chat + Layer 1 Crawl Worker ([doc 24](24-research-chat-agent.md)) |
| **D-9** | Primary product UX | ✅ Research Chat UI Phase 4 ([doc 24](24-research-chat-agent.md)) |

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial requirements |
| 2026-07-05 | FR-4: ссылка на ABC arXiv:2602.22302; ContractSpec-lite в FR-4.7 |
| 2026-07-05 | FR-1.10–1.11, FR-4.8–4.9: navigation hints (doc 21, SEOLB ref) |
| 2026-07-05 | FR-0.8: page screenshots (doc 22) |
| 2026-07-05 | Multi-viewport screenshots: desktop 1440×900, tablet, mobile |
| 2026-07-05 | FR-0.9–0.10, FR-3.7: vision analysis batch (doc 23); D-6b closed |
| 2026-07-05 | **v0.2:** FR-6 Research Chat; D-7/D-8/D-9 closed (doc 24); OQ-1 closed |
| 2026-07-05 | **v0.3 (review):** FR-1.12 sitemap; FR-1.13 SSRF guard; FR-1.14 redirect re-check; FR-3.8 cancel; FR-1.4 + Crawl-delay; NFR-2.5 bind localhost; NFR-4.4 concurrency=1 (D-12); NFR-1.2 p50/p95 согласован; OQ-2 закрыт (tldextract); OQ-4 cookie banners (D-11) |
| 2026-07-05 | **v0.4 (review-2):** FR-1.2 max_depth = hop depth (D-13); FR-1.14 landing-domain исключение для первой навигации |
| 2026-07-20 | **v0.5 (Phase 6):** FR-7 Action Framework (агент действует на сайте, doc 25) — Tier 0 sink / Tier 1 автономный click / Tier 2 submit-login под подтверждением / Tier 3 не автономно; FR-7.6 element referencing (спайк A-1). FR-4.2 уточнён как граница Tier 1/Tier 2. Login automation вынесен из out-of-scope в Tier 2 (attended) |
| 2026-07-20 | **v0.5.1 (Tier 2 login):** FR-7.4 — attended-логин реализован (login_wall → пауза, человек логинится в видимом браузере; агент паролей не хранит). Credentials-хранилище не нужно (unattended вне scope) |
