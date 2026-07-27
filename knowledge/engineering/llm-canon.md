---
type: Policy
title: LLM-канон — модели, флаги, дисциплина RAM
description: qwen3:14b как единая nav+synth модель с разными think-флагами, vision qwen2.5vl:7b, никогда две 14B одновременно.
status: stable
tags: [llm, ollama, performance]
generated:
  by: claude-code/fable-5
  at: 2026-07-27T00:00:00Z
resource: docs/16-prompts-library.md
implementation:
  - backend/app/llm/
  - data/prompts/
---

# Purpose

Выбор моделей и флагов закрыт бенчмарком (решения D-2/D-3, Phase 2), а не
вкусом. Ошибка в флаге тихо ломает качество: `format: json` душит thinking,
а qwen3 без `think: false` думает там, где нужен быстрый ответ.

# Canonical rules

| Пасс | Модель | Флаги |
|---|---|---|
| Навигация (DECIDE) | `qwen3:14b` | `think: false`, structured output |
| Синтез (SYNTHESIZE) | `qwen3:14b` | `think: true`, **без** `format` |
| Vision | `qwen2.5vl:7b` | батчем, браузер закрыт до вызова |

- **`format: json` + thinking несовместимы** — душит рассуждение; синтез идёт без
  `format`, а `strip_thinking()` подчищает ответ.
- **qwen3 думает по умолчанию** — для навигации `think: false` обязателен.
- **Никогда две 14B одновременно** (32 GB): между пассами `keep_alive: 0`,
  после прогонов модели выгружаются (`ollama ps` должен быть пуст).
- Fallback-пара при проблемах с qwen3:
  `LWA_NAV_MODEL=qwen2.5:14b-instruct LWA_SYNTH_MODEL=deepseek-r1:14b`.
- **Промпты живут в `data/prompts/`**, не в коде (CQG-гейт `inline-prompt`
  держит это механически). Словари и рубрики — тоже `data/`.
- Ollama-демон между сессиями может умереть — проверять `/api/version`;
  `ollama pull` бывает flaky (EOF), ретраить.

# Процессное правило

Перед запуском инференса на локальной модели агент **предупреждает человека**
(что и зачем запускает) и ждёт подтверждения; после прогона выгружает модели.
Причина — не безопасность, а ресурс машины: 14B ощутимо влияет на M5 Air.

# Related

- Локальный запуск и порты: [local run](/ops/local-run.md)
- Полный канон промптов и бенчмарки: `docs/16-prompts-library.md`,
  `docs/19-phase0-benchmark-results.md`
