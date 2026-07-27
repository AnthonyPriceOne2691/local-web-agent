# Active delivery status

- **slug:** mypy-strict
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** M
- **phase:** handoff
- **builder:** agent:claude-code
- **verifier:** human:anthony
- **human_ok_spec:** yes (by=human:anthony, at=2026-07-28)
  <!-- Основание: «это бесплатно? можно сейчас начать делать?» по конкретному
       пункту бэклога (mypy strict) — прямое задание объёма. -->
- **human_ok_plan:** n/a
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
- **ci-oracles:** tooling
- **worktree:** none (ветка fix/mypy-strict)
- **stack-selftest:** external (Prepare/)
- **hooks:** claude
- **blockers:** —
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Контекст поставки

Последний крупный пункт бэклога гейтов: mypy в базовом режиме. `--strict` даёт
**103 ошибки в 39 из 84 модулей**, но они однотипные — 81 это голые `dict`/`list`
в сигнатурах. Правки механические и не меняют поведение; регрессионная сетка —
191 тест.

## Отложенная поставка

`tier3-exit-smoke` (class S) — живой exit-прогон Tier 3, ждёт человека.
Артефакты — в git-истории `delivery/active/` на коммите `fed1a1a`.
