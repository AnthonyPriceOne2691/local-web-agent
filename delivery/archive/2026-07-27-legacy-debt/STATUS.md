# Active delivery status

- **slug:** legacy-debt
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** M
- **phase:** handoff
- **builder:** agent:claude-code
- **verifier:** human:anthony
- **human_ok_spec:** yes (by=human:anthony, at=2026-07-27)
  <!-- Основание: «я всё одобряю и давай поправь все ошибки легаси которые
       показала раскатка контура» — прямое задание объёма после отчёта, где
       каждый пункт долга был перечислен. -->
- **human_ok_plan:** n/a
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
- **ci-oracles:** tooling
  <!-- CI есть; гейт мержа в репо (merge_guard.sh + pre-push + needs:).
       Серверная защита ветки платная для приватного репо → force-push и обход
       админом не закрыты (delivery/STACK-ACCEPTANCE.md § Остатки). -->
- **worktree:** none (ветка fix/legacy-debt)
  <!-- Отступление от дефолта §5.1 с причиной: worktree потребовал бы дублировать
       тулчейн (venv ~1.5 GB + node_modules). Изоляция — ветка; слитое состояние
       всё равно проверяется merge_guard.sh перед мержем. -->
- **stack-selftest:** external (Prepare/)
- **hooks:** claude
- **blockers:** —
- **waivers:** waiver: max_files_touched=100 max_loc_diff=3000 reason=71 of 94 files are the isolated formatting commit afbd5f4 (blame-ignored); splitting a whole-project format is not possible by=human:anthony at=2026-07-27
  <!-- Основание: владелец одобрил объём работ («я всё одобряю и давай поправь
       все ошибки легаси») после отчёта, где ruff-format на 68 файлов был назван
       отдельным пунктом. Смысловые правки — 23 файла. -->
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Контекст поставки

Чистка легаси-долга, вскрытого развёртыванием канон-стека (`spec.md`). Долг был
заморожен в тающих списках (`per-file-ignores`, `[[tool.mypy.overrides]]`,
baseline'ы) — эта поставка снимает заморозки, а не расширяет их.

## Отложено (не в этой поставке — с причиной)

- Сложность функций (C901/PLR0912/PLR0915 в 10 модулях) — рефакторинг
  оркестратора, отдельная поставка со своим риском регрессии.
- mypy `strict` (146 ошибок в 40 модулях) — следующий шаг после этой чистки.
- `scripts/spike/**` — Phase 0 артефакт, вне стандартов по CLAUDE.md.

## Предыдущая поставка (вернуть после мержа)

`tier3-exit-smoke` (class S) — живой exit-прогон Tier 3 на фикстуре 8908;
блокер: нужен человек у клавиатуры (необратимую кнопку жмёт он). Артефакты — в
git-истории `delivery/active/` на коммите `1563e80`.
