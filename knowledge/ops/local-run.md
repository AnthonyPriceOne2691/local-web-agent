---
type: Runbook
title: Локальный запуск и порты
description: Как поднять API, Chat UI и фикстуры, какие порты заняты и как выгрузить модели после прогона.
status: stable
tags: [ops, runbook]
generated:
  by: claude-code/fable-5
  at: 2026-07-27T00:00:00Z
implementation:
  - backend/app/main.py
  - scripts/spike/fixtures_server.py
---

# Purpose

Всё крутится на одной машине; деплоя нет. Этот runbook — чтобы не искать
команды и не занять чужой порт.

# Порты

| Порт | Что |
|---|---|
| 8001 | API (FastAPI) + Chat UI статика на `/` |
| 5173 | Vite dev-сервер (proxy на 8001) |
| 8901–8908 | фикстурные сайты (каждый — свой origin) |
| 11434 | Ollama |

Фикстуры сортируются по имени каталога: `blog_alpha` 8901 · `blog_beta` 8902 ·
`blog_gamma` 8903 · `geo_kontak` 8904 · `pricing` 8905 · `simple_contact` 8906 ·
`spa_price` 8907 · `store_checkout` 8908. Актуальную мапу печатает
`fixtures_server.py --print` — новый сайт сдвигает порты по алфавиту.

# Запуск

```bash
# backend (venv: backend/.venv, менеджер uv)
cd backend && uv sync --extra dev            # + --extra gdocs для Google Docs sink
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Chat UI (prod-статику отдаёт API на /)
cd frontend && npm install && npm run build

# фикстурные сайты для E2E
backend/.venv/bin/python scripts/spike/fixtures_server.py

# Ollama, если демон умер
nohup ollama serve &
```

# Canonical rules

- **API bind только `127.0.0.1`** (NFR-2.5) — не `0.0.0.0`, даже «на минутку».
- **Сторонняя аналитика посещаемых сайтов не загружается** (`block_trackers`, список
  хостов в `data/browser/tracker_hosts.yaml`, включён по умолчанию): обход не
  отмечается в чужой аналитике от имени этой машины, и заодно не платит её сетевыми
  таймаутами (живой замер: обход одного сайта 20.2 s → 5.7 s). Это **не** обход
  anti-bot — отпечаток не подделывается, блокируется только телеметрия. Блокировать
  по типу ресурса нельзя: на SPA без своих скриптов страницы нет вовсе, поэтому
  список именно хостовый, и хост сайта под обходом не блокируется никогда.
- **Прогоны ветки — на отдельном порту, рабочий 8001 не трогать.** Гоняя испытания,
  поднимай второй инстанс (`--port 8021`) с кодом ветки: рабочий сервер держит
  старый код, и прогон против него проверит не то, что изменено.
- Одновременно активен **один** crawl (глобальный лок, D-12); `waiting_user`
  тоже держит лок — браузер открыт и ждёт человека.
- **После прогонов выгружать модели**: `ollama stop <model>`, проверить
  `ollama ps` (должен быть пуст) — [LLM canon](/engineering/llm-canon.md).
- Тесты не должны трогать реальную `data/runs` — фикстуры используют
  `Settings(runs_dir_override=tmp_path)`.
- Гейты перед коммитом — `AGENTS.md` § Быстрые гейты; мерж — только через
  `scripts/merge_guard.sh`.

# Related

- Что запускать нельзя без человека: [action tiers](/engineering/action-tiers.md)
- Дизайн API/CLI: `docs/15-api-cli-spec.md`
