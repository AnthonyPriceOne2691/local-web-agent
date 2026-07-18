# MEMORY — состояние проекта

> Снапшот для новых сессий Claude Code (обновлять при значимых вехах; история — в git).
> Обновлено: **2026-07-18** (ночь), Phase 2 ✅ DONE (exit-бенчмарк прогнан).

## Где мы

| Веха | Статус |
|------|--------|
| Design docs (22 шт.) | ✅ **все решения D-1..D-14 закрыты** (D-2/D-3 → qwen3:14b single-model по бенчмарку) |
| Phase 0 benchmark | ✅ **DONE 2026-07-13** ([docs/19](docs/19-phase0-benchmark-results.md) v1.0) |
| Phase 1 minimal agent loop | ✅ **DONE 2026-07-18** — backend+CLI+prompts, E2E 3/3 |
| **Phase 2 Full MVP** | ✅ **DONE 2026-07-18** — exit-бенчмарк 4/5 (гейт 80%), 7/8 с бонусами; vision E2E ✅; PLAN p50 7.9 s ≤ 8 s; 96 тестов, cov 93% ([doc 06](docs/06-mvp-phases.md) § Phase 2 — таблица результатов) |
| **Phase 3 Research Agent** | 🔲 **NEXT** — ComparisonResult, compare synthesizer, meta-agent, sessions (doc 06/24) |

## Phase 2 exit-бенчмарк (2026-07-18, qwen3:14b single-model + qwen2.5vl:7b)

- Фикстуры 5/5: phone ✅ · Pro price ✅ · RU-задача ✅ · GEO-слаг `/page/kontak` ✅ · **vision #8 ✅ ($49 из CSS ::after — DOM не видит, VLM находит, merged `source: vision, medium`)**.
- Real: playwright.dev ✅ (python API docs, high) · ollama.com ✅ (`/search`, S-H3c URL-факт) · python.org ❌ known-fail (intent docs срабатывает, `/dev`-проба в очереди, но LLM уходит в docs.python.org листать версии; честный not_found; backlog: аннотация проб интентом, penalty версионных ссылок).
- PLAN p50 **7.9 s** (28 вызовов; gate ≤8 doc 20 взят чисто); p95 11.6 s — выше NFR-1.2 (10 s) только на real-страницах → хвост тюнинга doc 20. Synth max 95.9 s (python.org) vs 203 s в Phase 0.
- Бенчмарк поймал 3 прод-бага (все починены + юниты): S-H3b vision-цитаты резались DOM-проверкой → reclass через `token_set_ratio`; S-H3c URL-факты убивались без цитаты → визит = self-evidence (cap medium); флак юнитов при живом fixtures-сервере → autouse-мок проб в conftest.

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

## Открытые хвосты (не блокеры; Phase 3 может идти)

1. **p95 PLAN 11.6 s vs NFR-1.2 10 s** на real-страницах — тюнинг сниппетов/бюджета (doc 20).
2. **python.org contribute-кейс** — backlog: аннотация slug-проб интентом в candidate-списке, penalty версионных ссылок (doc 06 § Phase 2 таблица).
3. doc 14 (model split) ещё описывает пару qwen2.5+r1 как канон — выровнять с doc 16 v0.5 (single-model) при ближайшей правке.
4. `--vision always` профили-таблица doc 21/23 реализована частично: viewports.yaml multi-viewport capture (tablet/mobile) не подключён к _maybe_screenshot (сейчас desktop-only + SPA fallback) — уточнить в Phase 3 design-audit работах.

## Окружение

- **Модели установлены**: qwen2.5:14b-instruct, deepseek-r1:14b, qwen2.5vl:7b, qwen3:14b. **Дефолт кода: qwen3:14b (nav+synth)**. После работы — выгружать (`ollama ps` пуст).
- **Venv'ы**: `backend/.venv` (uv sync --extra dev; rapidfuzz установлен) и корневой `.venv` (spike).
- **Порты**: API 8001 · fixtures 8901–8904 · Ollama 11434.
- Гейты перед коммитом: `pytest` (96) · `ruff check app tests ../cli` · `check_module_size.py`.

## Gotchas

- `format: json` + R1 несовместимы (душит thinking) — synth без format, `think: true`; `strip_thinking()` — fallback.
- qwen3 в Ollama думает по умолчанию — для nav обязательно `think: false`.
- Ollama-демон между сессиями может умереть — проверять `/api/version`; `ollama pull` flaky (EOF) — ретраить.
- Тесты не должны трогать реальную `data/runs` — фикстуры используют `Settings(runs_dir_override=tmp_path)`; SqliteRunStore при создании **мигрирует** JSON-файлы из каталога.
- Slug-пробы в юнитах отключены autouse-фикстурой `_no_network_probes` (conftest) — иначе живой fixtures-сервер на 8901 менял поведение тестов (флак). RobotsPolicy.load для public-origin тестов мокать точечно.
- FakeOllama отдаёт ответы по очереди: vision batch на SPA-фикстурах съедает свой reply — считать порядок (nav → vision → synth).
- step_index в steps неуникален (OBSERVE и ACT одного шага) — SQLite PK (run_id, seq).
- Фикстурные сайты: каждый на своём порту = свой origin.
