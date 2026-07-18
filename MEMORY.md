# MEMORY — состояние проекта

> Снапшот для новых сессий Claude Code (обновлять при значимых вехах; история — в git).
> Обновлено: **2026-07-18**, коммиты `48ffb02` (docs+Phase 0) → `d9e9f32` (Phase 1).

## Где мы

| Веха | Статус |
|------|--------|
| Design docs (22 шт., два review-прохода) | ✅ решения D-1..D-14 закрыты/зафиксированы в [docs/README.md](docs/README.md) |
| Phase 0 benchmark | ✅ **DONE 2026-07-13** — все exit-критерии ([docs/19](docs/19-phase0-benchmark-results.md) v1.0) |
| Phase 1 minimal agent loop | ✅ **DONE 2026-07-18** — backend+CLI+prompts, 30 тестов, cov 87%, E2E 3/3 |
| **Phase 2 Full MVP** | 🔲 **NEXT** |

## Ключевые результаты Phase 0 (для решений)

- **Hints-навигация бьёт чистый LLM**: GEO-слаг `/page/kontak` — hints ✅ 2 стр. vs llm-only ❌ (A/B #7).
- **Vision работает**: DOM-only честный not_found на CSS-цене; DOM+vision находит ($49). qwen2.5vl:7b: рубрика 5/5, JSON 100%, p95 14.3 s (D-6b/D-6c закрыты).
- **qwen3:14b single-model** (nav think:false + synth think:true): качество ≥ пары qwen2.5+r1, на 22–45% быстрее, ноль свопов → **рекомендация для D-2/D-3** (подтвердить на real-сайтах перед финализацией).
- Thermal: деградации нет (3 прогона, 1.006×). Real-сайты 2/3 (python.org ❌ — synth 203 s, тяжёлый контент).
- Слаг-пробы без HTTP-фильтра жгут бюджет на 404 → **F1-lite фильтр обязателен** (уже в проде Phase 1).

## Phase 1 — что построено

`backend/app/` (все слои за Protocols, DI через `app.state.orchestrator_factory`):
observer (snapshot/links/blockers, URL-канонизация+tldextract) · navigation (intent RU+EN, queue P0–P4 top-10, F1-lite probes) · contracts/guards (I-H1/H6/H8/H9, G-H1/H2/H3 hop-depth D-13, landing-adopt step 0) · llm (Ollama client: structured outputs, think, телеметрия; navigator/synthesizer c промптами из `data/prompts/`) · orchestrator/loop (state machine doc 04, robots+Crawl-delay, retry, SPA-fallback скриншот, replan→fallback recovery, чекпойнты) · storage (JSON store + startup sweep) · api (/health, POST /runs 409-lock D-12) + `cli/main.py`.

E2E 3/3 на фикстурах: телефон с цитатой · RU-задача (value по-русски — языковое правило работает) · email через несвязанный слаг. 0 контрактных нарушений.

## Открытые хвосты (не блокеры)

1. **PLAN p50 на real-сайтах 10–11 s** (цель 8 s) — мерилось при параллельной закачке; re-check чисто (gate doc 20 перед Phase 2 exit).
2. **qwen3 single-model на real-сайтах** — для финализации D-2/D-3.
3. **Synth 203 s на python.org** — тюнинг токен-бюджета (doc 20) для тяжёлых страниц.
4. tok/s ~11–12 у 14B — ниже ожиданий M5, проверить квантование/версию Ollama.

## Phase 2 scope (doc 06)

YAML contract-enforcer (`data/contracts/*.yaml`) · SQLite store (doc 12) · VISION_BATCH (loader/analyzer, doc 23) · sitemap tier P2.5 · cookie-dismiss D-11 (`consent_selectors.yaml` уже готов) · cancel FR-3.8 · markdown-отчёты (doc 05) · early stop · F1 HTTP tier полный · coverage-гейты 95/90/85.

## Окружение

- **Модели установлены**: qwen2.5:14b-instruct, deepseek-r1:14b, qwen2.5vl:7b, qwen3:14b (все ~9.3/9/6/9.3 GB). После работы — выгружать (`ollama ps` пуст).
- **Venv'ы**: `backend/.venv` (uv sync, прод+тесты) и корневой `.venv` (spike-скрипты). Playwright chromium в кэше.
- **Порты**: API 8001 · fixtures 8901–8904 · Ollama 11434.
- Прогоны Phase 0: `scripts/spike/results/*.jsonl` (gitignored), сводка — `summarize_results.py`.

## Gotchas

- `format: json` + R1 несовместимы (constrained decoding душит thinking) — R1/qwen3 synth без format, с `think: true`; `strip_thinking()` — fallback.
- qwen3 в Ollama **думает по умолчанию** — для nav обязательно `think: false`.
- `ollama pull` падает с «unexpected EOF» при flaky сети — ретраить; прогресс через `| tail -1` не виден (буферизация) — смотреть размер partial-блобов в `~/.ollama/models/blobs/`.
- Ollama-демон, запущенный из сессии (nohup), может умереть между сессиями — проверять `/api/version`.
- IDE-диагностика «Package not installed» в pyproject — у IDE выбран не тот интерпретатор; истина — `backend/.venv` (pytest зелёный).
- Фикстурные сайты: каждый на своём порту = свой origin (same-site по netloc для localhost).
