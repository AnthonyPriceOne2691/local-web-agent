# MEMORY — состояние проекта

> Снапшот для новых сессий Claude Code (обновлять при значимых вехах; история — в git).
> Обновлено: **2026-07-18** (вечер), Phase 2 code complete.

## Где мы

| Веха | Статус |
|------|--------|
| Design docs (22 шт., два review-прохода) | ✅ решения D-1..D-14 закрыты/зафиксированы в [docs/README.md](docs/README.md) |
| Phase 0 benchmark | ✅ **DONE 2026-07-13** — все exit-критерии ([docs/19](docs/19-phase0-benchmark-results.md) v1.0) |
| Phase 1 minimal agent loop | ✅ **DONE 2026-07-18** — backend+CLI+prompts, E2E 3/3 |
| **Phase 2 Full MVP** | 🟡 **CODE COMPLETE 2026-07-18** — 93 теста, cov 94%; до закрытия — ручные прогоны (ниже) |
| Phase 3 Research Agent | 🔲 next после закрытия Phase 2 |

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

## Хвосты до закрытия Phase 2 (ручные, нужны реальные LLM)

1. **5-task benchmark ≥80%** (suite Phase 0) на Phase 2-коде — exit-критерий #2 doc 06.
2. **E2E на fixture-сервере** (3 сценария Phase 1 + vision/sitemap кейсы) с реальными моделями.
3. **PLAN p50 ≤8s re-check** чисто, без параллельной закачки (gate doc 20).
4. qwen3 single-model на real-сайтах — финализация D-2/D-3 (из Phase 0).
5. Synth 203s на python.org — тюнинг токен-бюджета (doc 20).

## Окружение

- **Модели установлены**: qwen2.5:14b-instruct, deepseek-r1:14b, qwen2.5vl:7b, qwen3:14b. После работы — выгружать (`ollama ps` пуст).
- **Venv'ы**: `backend/.venv` (uv sync --extra dev; rapidfuzz теперь установлен) и корневой `.venv` (spike).
- **Порты**: API 8001 · fixtures 8901–8904 · Ollama 11434.
- Гейты перед коммитом: `pytest` (93) · `ruff check app tests ../cli` · `check_module_size.py`.

## Gotchas

- `format: json` + R1 несовместимы (душит thinking) — synth без format, `think: true`; `strip_thinking()` — fallback.
- qwen3 в Ollama думает по умолчанию — для nav обязательно `think: false`.
- Ollama-демон между сессиями может умереть — проверять `/api/version`; `ollama pull` flaky (EOF) — ретраить.
- Тесты не должны трогать реальную `data/runs` — фикстуры используют `Settings(runs_dir_override=tmp_path)`; SqliteRunStore при создании **мигрирует** JSON-файлы из каталога.
- Оркестратор-юниты с публичным origin обязаны мокать `probe_slugs_f1`/`filter_alive`/`RobotsPolicy.load` — иначе реальная сеть.
- FakeOllama отдаёт ответы по очереди: vision batch на SPA-фикстурах съедает свой reply — считать порядок (nav → vision → synth).
- step_index в steps неуникален (OBSERVE и ACT одного шага) — SQLite PK (run_id, seq).
- Фикстурные сайты: каждый на своём порту = свой origin.
