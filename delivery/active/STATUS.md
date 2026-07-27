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
- **ci-oracles:** tooling
  <!-- По определению §10.4 `tooling` = CI есть + гейт мержа в репозитории
       (merge_guard + pre-push), серверного нет по тарифу. Это и есть наш случай.
       `weak` (что стояло здесь по ходу поставки) означает «CI нет вовсе» —
       трактовать им «CI красный» было ошибкой: красный прогон это stop-gate
       (§3.3), и следит за ним отдельный гейт scripts/lint/check_ci_status.sh.
       Подтверждено прогоном на PR #4: джоба gates зелёная целиком, включая
       шаги, которые до фикса ни разу не выполнялись. -->
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
