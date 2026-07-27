---
type: Design
title: Реестр действий Layer 2
description: Единственный источник правды для tools планнера; новое действие = модуль + промпт-файл, runner и планнер не меняются.
status: stable
tags: [actions, extensibility]
generated:
  by: claude-code/fable-5
  at: 2026-07-27T00:00:00Z
resource: docs/25-action-framework.md
implementation:
  - backend/app/research/actions/
  - data/prompts/tools/
---

# Purpose

Раньше список инструментов планнера был двумя захардкоженными кортежами
(`KNOWN_TOOLS` в runner, `PLANNER_TOOLS` в планнере) — и они **разошлись**.
Теперь один реестр: он же membership-проверка (A-H1), он же точка расширения.

# Canonical rules

- Действие описывается `ActionSpec`: `name`, `tier`, `reversible`, `cloud`,
  `structural`, хуки `enforce` / `execute` / `note`.
- **Новое действие = модуль в `backend/app/research/actions/` с
  `register(ActionSpec(...))` + описание в `data/prompts/tools/<name>.txt`.**
  Runner и планнер при этом не трогаются. Описания — в `data/`, не в коде.
- Блок «Available tools» meta-промпта собирается из реестра (`{TOOLS_BLOCK}`);
  зарегистрированное действие без txt-описания = ошибка конфигурации (fail fast).
- `structural` действия (`crawl_site`, `compare_results`) ведёт runner — у них
  нет `execute`: они управляют потоком сессии (очередь, cooldown, финал).
- Пер-action контракты живут в `enforce` (например «run_id только из этой
  сессии» — M-H3); кросс-плановые правила (лимит crawl'ов M-H2, «compare один и
  последним») остаются в планнере.
- **Гейт tier**: runner не исполняет действия tier ≥ 2 без подтверждения
  (A-H2/A-H3) — см. [action tiers](/engineering/action-tiers.md).

# Зарегистрированные действия

| Действие | Tier | Заметка |
|---|---|---|
| `crawl_site` | 1 | structural: обход одного сайта |
| `compare_results` | 0 | structural: терминальная стадия сравнения |
| `get_run_result` | 0 | детали run'а в ответ чата |
| `list_session_runs` | 0 | список runs сессии |
| `export_gdocs` | 0 | **cloud**: только по явному запросу (A-H4) |
| `export_file` | 0 | локальный markdown в artifacts сессии |

# Related

- Тиры и политика подтверждения: [action tiers](/engineering/action-tiers.md)
- Планнер и контракты M-*: `docs/24-research-chat-agent.md`
