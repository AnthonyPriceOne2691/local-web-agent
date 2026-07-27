---
type: Reference
title: Design docs (`docs/`) — источник правды дизайна
description: Где лежат версионированные дизайн-решения проекта и почему bundle их не дублирует.
status: stable
tags: [process, docs]
generated:
  by: claude-code/fable-5
  at: 2026-07-27T00:00:00Z
resource: docs/README.md
implementation: []   # указатель на внешний канон, поведение кода не описывает
---

# Purpose

У проекта **уже есть** зрелый канон дизайна — `docs/` (25 версионированных
доков с changelog'ами). Bundle его не заменяет и не копирует: дубль канона
означает, что один из двух врёт.

# Canonical rules

- **`docs/` — источник правды дизайна.** Любое изменение дизайна = правка дока +
  запись в changelog + bump версии в шапке; версии в шапке, индексе и changelog
  должны совпадать.
- **`knowledge/` — канон инвариантов для агента**: выжимка того, о чём легко
  соврать по памяти, с картой реализации (`implementation:`) и гейтом
  синхронизации `okf_sync_gate.py`.
- Разошлись — правится **тот слой, где неправда**, и пишется в `log.md` почему;
  молчаливый drift запрещён.
- Работа ведётся в рамках фаз `docs/06-mvp-phases.md`; процессные фазы поставки
  (`specify … handoff`) живут отдельно, в `delivery/`.

# Навигация по docs/

| Тема | Док |
|---|---|
| Индекс и решения D-1..D-14 | `docs/README.md` |
| Требования (FR/NFR) | `docs/01-requirements.md` |
| Фазы продукта | `docs/06-mvp-phases.md` |
| Поведенческие контракты (I-H*, S-*, G-*) | `docs/13-behavioral-contracts.md` |
| API / CLI / SSE | `docs/15-api-cli-spec.md` |
| Промпты и модели | `docs/16-prompts-library.md` |
| Инженерные стандарты (≤500 LOC, SOLID, тесты) | `docs/18-engineering-standards.md` |
| Research chat agent + attended | `docs/24-research-chat-agent.md` |
| Action Framework (тиры 0-3) | `docs/25-action-framework.md` |

# Related

- Инварианты действий: [action tiers](/engineering/action-tiers.md)
- Состояние проекта и хвосты: `MEMORY.md` (в корне, gitignored — локальный снапшот)
