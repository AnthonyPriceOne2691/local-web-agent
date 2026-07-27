# Active delivery status

- **slug:** ci-red
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
- **phase:** implement
- **builder:** agent:claude-code
- **verifier:** human:anthony
- **human_ok_spec:** n/a          <!-- class S: mini-spec в tasks.md (§2.2) -->
- **human_ok_plan:** n/a
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
- **ci-oracles:** weak
  <!-- ЧЕСТНОЕ значение на время этой поставки: CI существует, но красный с
       первого прогона (6/6) — неподделываемого прогона у нас не было ни разу.
       Вернём `tooling` только после зелёного прогона quality на main. -->
- **worktree:** none (ветка fix/ci-red)
- **stack-selftest:** external (Prepare/)
- **hooks:** claude
- **blockers:** —
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Контекст поставки

Развёрнутый контур врал о себе: в STATUS стояло `ci-oracles: tooling`, а все шесть
прогонов CI были красными — и две поставки закрыты как done при красном CI.
Причины и план — `tasks.md`. Пока поставка не закрыта, `ci-oracles: weak` — это
факт, а не пессимизм.

## Отложенная поставка

`tier3-exit-smoke` (class S) — живой exit-прогон Tier 3, ждёт человека у
клавиатуры. Артефакты — в git-истории `delivery/active/` на коммите `d460e92`.
