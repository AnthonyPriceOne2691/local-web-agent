# 18 — Engineering Standards (SOLID, DRY, tests, module size)

> Local Web Agent · Design doc · **v0.4** · 2026-08-02

## Принцип

Код пишется **только после Phase 0**, но **с первого коммита** — по этим правилам.  
Паттерн **идентичен** [Voice Interview Coach doc 18](../../voice-interview-coach/docs/18-engineering-standards.md), адаптирован под browser agent.

**Связанные docs:** [02-architecture.md](02-architecture.md), [06-mvp-phases.md](06-mvp-phases.md), [01-requirements.md](01-requirements.md) (NFR-6).

---

## 1. Размер модулей — hard limit 500 LOC

| Метрика | Лимит |
|---------|-------|
| Один файл `.py` в `backend/app/`, `cli/` | **≤ 500 строк** |
| Spike scripts in `scripts/spike/` | исключение |

**Enforcement:** `scripts/check_module_size.py` — fail if exceeded.

### Целевая гранулярность

```
backend/app/
├── main.py                 # wiring < 150 LOC
├── api/
│   ├── routes_health.py
│   └── routes_runs.py
├── browser/
│   ├── session.py          # Playwright wrapper
│   └── launch.py
├── observer/
│   ├── snapshot.py
│   ├── links.py
│   └── blockers.py
├── orchestrator/
│   ├── loop.py
│   ├── states.py
│   └── link_scorer.py      # → navigation/link_scorer.py in Phase 1
├── navigation/             # intent, path_hints, candidate_queue, link_scorer
├── contracts/
│   ├── loader.py
│   └── enforcer.py
├── llm/
│   ├── ollama_client.py
│   ├── navigator.py
│   └── synthesizer.py
├── extraction/
│   └── validator.py
└── storage/
    ├── models.py
    └── run_repository.py
```

---

## 2. SOLID — project-specific rules

| Компонент | Единственная ответственность |
|-----------|------------------------------|
| `BrowserSession` | Playwright lifecycle, goto |
| `PageObserver` | DOM → PageSnapshot |
| `CrawlOrchestrator` | state machine, not HTTP |
| `ContractEnforcer` | validate actions, not browse |
| `OllamaClient` | HTTP to Ollama, not prompts |
| `RunRepository` | CRUD, not business rules |

**Interfaces (Protocol):**
- `BrowserSession`
- `PageObserver`
- `LlmClient`
- `RunStore`
- `ContractEnforcer`

**DI:** FastAPI `Depends` or `AppContainer` in `main.py`.

---

## 3. DRY

### Дублировать нельзя
- URL normalization
- PageSnapshot truncation
- Contract YAML loading
- Ollama request boilerplate
- `strip_thinking()` for R1

### Где не гонять DRY
- Navigator vs synthesizer prompts — **отдельные файлы**
- Unit tests — explicit fixtures over mega-helpers

---

## 4. Тесты — coverage gates

| Область | Минимум | Phase |
|---------|---------|-------|
| `contracts/` | **95%** | 2+ |
| `navigation/` (intent, candidate_queue, link_scorer) | **90%** | 1+ |
| `orchestrator/` | **90%** | 2+ |
| `observer/` | **85%** | 1+ |
| `llm/` | **85%** | 1+ |
| `extraction/` | **90%** | 2+ |
| `storage/` | **90%** | 2+ |
| `api/` | **80%** | 1+ |

**Backend `app/` overall:** ≥ **85%** end of Phase 2.

### Обязательные test cases

| Module | Cases |
|--------|-------|
| Contract enforcer | external URL reject; unseen URL reject; max pages; **private-IP reject (I-H8)**; **off-domain redirect discard (I-H9)** |
| Orchestrator | visited dedup; **hop-depth limit (не path-сегменты: `/blog/2024/03/x` в 1 клик = depth 1)**; fallback scorer; **extract_now loop guard**; **cancel flag mid-run**; **startup sweep: running → failed** |
| Navigation | intent from task (**RU + EN keywords**); slug queue P0<P2; `/page/kontak` not truncated by budget; **sitemap URLs → queue (P2.5)**; **content_search: 3 article candidates, не первая** |
| Observer | truncation; link extraction; blocker detection; **screenshot write**; **URL normalization (utm strip, trailing slash)** |
| Action parser | valid JSON; invalid → recovery |
| Extraction validator | high without quote → fail |
| API | POST /runs, GET status; **409 при активном run (D-12)**; **POST cancel** |

### Mocks

| Service | Mock in tests |
|---------|---------------|
| Playwright | ✅ Fake BrowserSession with HTML fixtures |
| Ollama | ✅ fixture JSON responses |
| SQLite | in-memory |

**E2E with real Playwright + Ollama:** `scripts/e2e_local.sh` — not in CI.

### Fixture sites

```
tests/fixtures/sites/
├── simple_contact/
│   ├── index.html
│   └── contact.html
├── pricing/
│   └── index.html
├── geo_kontak/
│   ├── index.html          # links to /page/kontak
│   └── page/kontak.html
├── redirect_offsite/       # ссылка 302 → чужой домен (I-H9, doc 13)
│   └── index.html
├── private_ip_link/        # <a href="http://192.168.1.1/admin"> (I-H8)
│   └── index.html
├── cookie_banner/          # overlay-баннер поверх контента (D-11, doc 22)
│   └── index.html
├── paginated_blog/         # статья на page 2 + sitemap.xml (doc 21 P2.5, UC-2)
│   ├── index.html
│   ├── page2.html
│   ├── sitemap.xml
│   └── betting-guide.html
└── sitemap_only/           # страница недостижима по ссылкам, есть в sitemap
    ├── index.html
    ├── sitemap.xml
    └── hidden-page.html
```

Serve via `pytest-httpserver` or static file handler — no flaky network.

---

## 5. Code quality tools

| Tool | Scope |
|------|-------|
| ruff (lint + format) | `backend/`, `cli/`, `scripts/` — **весь Python репозитория**, кроме `scripts/spike/` |
| mypy strict | `backend/app/` **и** `scripts/` (кроме `scripts/spike/`) |
| pytest + pytest-cov | backend |
| playwright | optional e2e script only |

**Конфиг ruff — в двух файлах, но правила в одном.** `backend/pyproject.toml` держит
набор правил, ignore-список и пороги сложности; корневой `ruff.toml` его `extend`-ит
и добавляет только то, что специфично для корня (`scripts/spike` в `extend-exclude`,
per-file-ignores для `cli/` и гейт-скриптов).

**Гонять lint и format только из корня репозитория** — так же, как это делает
pre-commit. Запуск из `backend/` применяет к `cli/` и `scripts/` backend-конфиг и
даёт ложный красный на формате.

История, ради которой это записано (поставка `lint-contour`, 2026-08-01): конфига в
корне не было, ruff берёт ближайший вверх по дереву, поэтому `cli/` и `scripts/`
линтовались **дефолтным** набором ruff (E4/E7/E9/F). Канонные правила там не работали
никогда, а хук был зелёным — «гейт есть, проверки нет».

**Гейт-скрипты — код с поведением, а не клей.** Они решают, пройдёт ли поставка,
поэтому держатся на тех же правилах: `mypy --strict`, канонные пороги сложности и
характеризационные тесты (`backend/tests/test_delivery_check_gate.py`,
`test_gate_scripts.py`) — гейт вызывается процессом, проверяются exit code и текст
сообщений. Новый гейт пишется набором проверок-функций, каждая возвращает
`(errors, warnings)`; одна `main()` на сто строк — то, из чего поставка
`scripts-canon` (2026-08-02) их и разбирала.

---

## 6. Definition of Done (each phase)

- [ ] No files > 500 LOC
- [ ] New code with tests same PR
- [ ] Coverage ≥ phase threshold
- [ ] Dependencies via Protocols / DI
- [ ] `ruff` / `mypy` clean

---

## 7. Anti-patterns

| Anti-pattern | Why |
|--------------|-----|
| Playwright calls in route handler | layer violation |
| LLM prompts inline in orchestrator | no versioning |
| Skip tests «needs real browser» | mock BrowserSession |
| One 900-line `crawl.py` | SRP + LOC |
| Trust LLM URLs without enforcer | security + hallucination |

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial; adapted from voice-interview-coach doc 18 |
| 2026-07-05 | `navigation/` module + GEO fixture; coverage Phase 1 |
| 2026-07-05 | **v0.2 (review):** fixtures redirect_offsite / private_ip_link / cookie_banner / paginated_blog / sitemap_only; test cases I-H8/I-H9, cancel, 409, sitemap, URL normalization |
| 2026-07-05 | **v0.2.1 (review-2):** test cases hop depth, RU keywords, article candidates, startup sweep |
| 2026-08-01 | **v0.3:** контур ruff зафиксирован — `backend/` + `cli/` + `scripts/` (кроме `scripts/spike/`), корневой `ruff.toml` через `extend`, lint/format гонять из корня |
| 2026-08-02 | **v0.4:** `mypy --strict` распространён на `scripts/`; гейт-скрипты разобраны по сложности и покрыты характеризационными тестами; правило «новый гейт = проверки-функции» |
