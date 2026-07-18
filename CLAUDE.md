# Local Web Agent — инструкции для Claude Code

Локальный research-агент: Layer 1 — crawl worker одного сайта (Playwright + Ollama), Layer 2 — research chat по N сайтам со сравнением. Всё на MacBook Air M5 32 GB, **ноль облачных API** (privacy-first). Автор: Anton Aspidov (общение — по-русски).

**Первым делом в новой сессии:** прочитай [MEMORY.md](MEMORY.md) — там текущее состояние, открытые хвосты и gotchas.

## Процесс (обязателен)

- **Design docs — источник правды**: `docs/` (индекс и решения D-1..D-14 — [docs/README.md](docs/README.md)). Любое изменение дизайна = правка дока + запись в changelog в конце + bump версии в шапке (`v0.x`). Версии в шапке, индексе и changelog должны совпадать.
- **Код только в рамках фаз** [docs/06-mvp-phases.md](docs/06-mvp-phases.md). Phase 0 ✅, Phase 1 ✅, Phase 2 — next.
- **Стандарты** [docs/18-engineering-standards.md](docs/18-engineering-standards.md): файл ≤ 500 LOC (`scripts/check_module_size.py`), SOLID/Protocols + DI, DRY — промпты и словари в `data/`, не в коде; тесты с моками (Fake browser/LLM в `backend/tests/conftest.py`); coverage: contracts ≥95%, orchestrator/navigation ≥90%, app ≥85% (к концу Phase 2).
- **Перед завершением любой работы с кодом**: `ruff check`, `pytest`, `check_module_size.py` — всё зелёное.
- `scripts/spike/` — исключение из стандартов (Phase 0 артефакт, не трогать без нужды).

## Команды

```bash
# Backend (venv: backend/.venv, менеджер uv)
cd backend && uv sync --extra dev
.venv/bin/python -m pytest -q --cov=app          # тесты + coverage
.venv/bin/python -m ruff check app tests ../cli   # lint
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001  # API

# CLI (из корня репо)
backend/.venv/bin/python -m cli.main crawl --url URL --task "..."
backend/.venv/bin/python -m cli.main runs list

# Fixture-сайты для тестов/E2E (порты 8901+)
backend/.venv/bin/python scripts/spike/fixtures_server.py

# Гейт размера модулей
backend/.venv/bin/python scripts/check_module_size.py

# Phase 0 spike-бенчмарки (отдельный .venv в корне)
cd scripts/spike && ../../.venv/bin/python benchmark_crawl.py --tasks tasks.yaml --dry-run
```

## LLM / Ollama

- Канон параметров — [docs/16-prompts-library.md](docs/16-prompts-library.md): nav `qwen2.5:14b-instruct` (structured outputs — JSON Schema в `format`), synth `deepseek-r1:14b` (`think: true`, БЕЗ `format` — иначе душится thinking), vision `qwen2.5vl:7b` (Phase 2).
- **Рекомендация Phase 0** (doc 19): single-model `qwen3:14b` (nav `think:false` + synth `think:true`) — быстрее на 22–45%, ноль свопов. Включение: `LWA_NAV_MODEL=qwen3:14b LWA_SYNTH_MODEL=qwen3:14b`. Финализация D-2/D-3 — после повтора на real-сайтах.
- Дисциплина RAM (32 GB): никогда 2×14B одновременно; между pass'ами `keep_alive: 0`; после прогонов выгружать модели (`ollama ps` должен быть пуст). Если пользователь говорит «модель не поднимай» — только код/тесты/dry-run, без инференса.
- Ollama-демон может быть не запущен: `nohup ollama serve &`. `ollama pull` бывает flaky (EOF) — ретраить.

## Границы

- API bind только `127.0.0.1` (NFR-2.5); глобальный лок: 1 активный crawl (D-12, 409).
- robots.txt соблюдаем, anti-bot bypass запрещён, формы не сабмитим (контракты doc 13).
- Никаких облачных LLM и телеметрии.

## Git

- Приватный GitHub: https://github.com/AnthonyPriceOne2691/local-web-agent (identity настроен: Anton Aspidov + noreply). Коммиты — со ссылкой на фазу/доки; пушить после зелёных гейтов.
