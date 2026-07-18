# MEMORY — состояние проекта

> Снапшот для новых сессий Claude Code (обновлять при значимых вехах; история — в git).
> Обновлено: **2026-07-18** (поздняя ночь), Phase 3 ✅ DONE.

## Где мы

| Веха | Статус |
|------|--------|
| Design docs (22 шт.) | ✅ **все решения D-1..D-14 закрыты** (D-2/D-3 → qwen3:14b single-model) |
| Phase 0 benchmark | ✅ **DONE 2026-07-13** ([docs/19](docs/19-phase0-benchmark-results.md) v1.0) |
| Phase 1 minimal agent loop | ✅ **DONE 2026-07-18** |
| Phase 2 Full MVP | ✅ **DONE 2026-07-18** — 4/5 (80% гейт), vision E2E, PLAN p50 7.9 s ([doc 06](docs/06-mvp-phases.md) § Phase 2) |
| **Phase 3 Research Agent** | ✅ **DONE 2026-07-18** — UC-1/UC-2 exit-бенчмарк ([doc 06](docs/06-mvp-phases.md) § Phase 3); 115 тестов, cov 93% |
| **Phase 4 Chat UI** | 🔲 **NEXT** — React chat + SSE поверх /sessions (doc 24 § Chat UI, doc 17) |

## Phase 3 — что построено и бенчмарк

- `research/`: meta_agent (rules-planner: URL regex, research intent RU+EN, план по intent-таблице), runner (sequential D-7 + cooldown 30 s при N≥4, partial failure → `excluded[]`, M-H1..M-H4, session cancel/timeout 60 min), compare_synthesizer (rubrics из data/, wide ctx 24K при N>3, run_id мапит код по netloc-с-портом, выдуманные сайты отбрасываются), report (comparison_report.md).
- Storage: research_sessions в том же app.db (messages_json в строке; sweep running_tools/comparing → failed). API `/sessions` CRUD+messages+cancel; CLI `agent research --urls --task --output --report`.
- ExtractionResult + `article` (excerpt 12K **подставляет код из снапшота** — LLM возвращает только url+мету и короткую цитату), `article_candidates_considered`, `design_tokens`; синтез intent-aware (ARTICLE/DESIGN MODE в user-промпте).
- **UC-2 ✅** (3 блог-фикстуры): winner blog_alpha **95** > gamma 75 > beta 50 — спроектированный порядок; dimensions/narrative с цитатами; ~11 мин. **UC-1 ✅** (4 сайта, design_diff, vision always): report c 6 dimensions × 4 сайта; ~18.5 мин ≤ 20-мин бюджета doc 24; vision 0 сбоев; пик RAM Ollama 13 GB, OOM нет; winner=None — корректно для diff-рубрики.
- Бенчмарк-фиксы: `_host()` netloc с портом (фикстуры 127.0.0.1:* сливались), article-excerpt больше не перепечатывается LLM (резался max_tokens → пустой partial), невалидный article-блок отбрасывается не роняя синтез, word_count coercion+порог 50.

## Phase 2 — что построено (поверх Phase 1)

- **SQLite store** (`storage/sqlite_store.py`, doc 12 v0.5): WAL, run lock производный от БД, legacy-JSON автоимпорт (файлы → `data/runs/legacy_json/`), `DELETE /runs/{id}` + `runs delete`, result.json + report.md в artifacts.
- **Contract Enforcer** (`contracts/{loader,enforcer,context,rules/}`, doc 13 v0.7): YAML DSL в `data/contracts/` (crawl/synthesis/vision + crawl_forbidden.txt), unknown check → fail fast; порядок hard-проверок приоритетом кодов (G-H1 первым); G-H4/G-H6 — clamp-enforcement (`effective_rate_ms`, private exempt); recovery k=2 + link_scorer; **drift auto-tighten**: hard ≥3 → temp 0.2, I-H6 ≥2 → top-5, recovery <50% → fallback-only.
- **SynthesisValidator** (`extraction/synthesis_validator.py`): S-H3 fuzzy ≥0.85 (rapidfuzz, in-memory), провал цитаты → drop evidence / fact → not_found; S-H6 vision-only ≠ high; S-G2 max 20 facts.
- **Cancel FR-3.8**: cooperative event, проверки на границах state + между vision-вызовами; `POST /runs/{id}/cancel`, `runs cancel [id]`, Ctrl+C → abort/detach.
- **Sitemap P2.5** (`navigation/sitemap.py`): robots `Sitemap:` → fallback /sitemap.xml; index → 3 вложенных; cap 500/20; intent-фильтр (content_search по task-keywords минус стоп-слова; прочие по path_hints).
- **F1 полный** (`navigation/probes.py`): GET 12s/500KB/browser-UA/https→http; 403|пустой текст → escalate F2; links проб → queue bucket P1 (`f1:`-reason).
- **Early stop G-S1**: 3 посещённые страницы без новых кандидатов с сигнальными тегами → SYNTHESIZE (`metadata.early_stop`).
- **Cookie-dismiss D-11** (`browser/consent.py`): detect (fixed/z≥1000/25%+keywords) → CSS-hide → CMP-click reject-first (1/сайт, 2s); статус per-page в `metadata.consent`; **consent_selectors.yaml был битым YAML — починен**.
- **Vision batch** (`vision/`, `orchestrator/vision_batch.py`, doc 23): VisionLoader shield (V-H1/H2/H3), key-pages R0–R3 + caps 5/12, VISION_BATCH state (браузер закрыт до VLM), insights → снапшоты → текстом в R1-промпт; `--vision auto|always|never`.
- **Markdown report** (`reporting/markdown.py`, doc 05): Findings/Design/Not found/Appendix → `artifacts/{id}/report.md`.
- RunConfig новое: `use_sitemap`, `consent_handling`, `consent_click`, `vision_enabled`, `allow_private`.

## Открытые хвосты (не блокеры; Phase 4 может идти)

1. **p95 PLAN 11.6 s vs NFR-1.2 10 s** на real-страницах — тюнинг сниппетов/бюджета (doc 20).
2. **python.org contribute-кейс** — backlog: аннотация slug-проб интентом в candidate-списке, penalty версионных ссылок (doc 06 § Phase 2 таблица).
3. **Multi-viewport capture** (tablet/mobile из viewports.yaml) не подключён к _maybe_screenshot — desktop-only; в UC-1 dimension mobile_vs_desktop честно 0. Поднять при Phase 4 design-audit UX.
4. **SSE `/sessions/{id}/events`** отложен до Phase 4 (CLI поллит GET); doc 24 v0.4 п.4.
5. UC-бенчмарки гонялись на локальных фикстурах; real-site research-сессия (2-3 публичных сайта) — прогнать при случае для калибровки таймингов.

## Окружение

- **Модели установлены**: qwen2.5:14b-instruct, deepseek-r1:14b, qwen2.5vl:7b, qwen3:14b. **Дефолт кода: qwen3:14b (nav+synth)**. После работы — выгружать (`ollama ps` пуст).
- **Venv'ы**: `backend/.venv` (uv sync --extra dev; rapidfuzz установлен) и корневой `.venv` (spike).
- **Порты**: API 8001 · fixtures 8901–8904 · Ollama 11434.
- Гейты перед коммитом: `pytest` (115) · `ruff check app tests ../cli` · `check_module_size.py`.
- Fixture-порты сдвинулись (сайты сортируются по имени): blog_alpha 8901 · blog_beta 8902 · blog_gamma 8903 · geo_kontak 8904 · pricing 8905 · simple_contact 8906 · spa_price 8907.

## Gotchas

- `format: json` + R1 несовместимы (душит thinking) — synth без format, `think: true`; `strip_thinking()` — fallback.
- qwen3 в Ollama думает по умолчанию — для nav обязательно `think: false`.
- Ollama-демон между сессиями может умереть — проверять `/api/version`; `ollama pull` flaky (EOF) — ретраить.
- Тесты не должны трогать реальную `data/runs` — фикстуры используют `Settings(runs_dir_override=tmp_path)`; SqliteRunStore при создании **мигрирует** JSON-файлы из каталога.
- Slug-пробы в юнитах отключены autouse-фикстурой `_no_network_probes` (conftest) — иначе живой fixtures-сервер на 8901 менял поведение тестов (флак). RobotsPolicy.load для public-origin тестов мокать точечно.
- FakeOllama отдаёт ответы по очереди: vision batch на SPA-фикстурах съедает свой reply — считать порядок (nav → vision → synth).
- step_index в steps неуникален (OBSERVE и ACT одного шага) — SQLite PK (run_id, seq).
- Фикстурные сайты: каждый на своём порту = свой origin.
