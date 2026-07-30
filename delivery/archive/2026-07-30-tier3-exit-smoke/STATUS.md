# Active delivery status

- **slug:** tier3-exit-smoke
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
- **phase:** handoff
- **builder:** agent:claude-code
- **verifier:** human:anthony     <!-- живой прогон Tier 3 может принять только человек -->
- **human_ok_spec:** n/a          <!-- class S: mini-spec в tasks.md (§2.2) -->
- **human_ok_plan:** n/a
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
- **ci-oracles:** tooling
  <!-- CI есть (.github/workflows/quality.yml); гейт мержа в репо (scripts/merge_guard.sh
       + pre-push + needs:). Серверная защита ветки — платная для приватного репо
       (Pro+), поэтому НЕ закрыты: force-push в main и обход админом. Остаток
       зафиксирован в delivery/STACK-ACCEPTANCE.md § Остатки. -->
- **worktree:** none (ветка fix/tier3-live-fixes)
- **hooks:** claude    <!-- stop-on-red + protect-main, .claude/settings.json -->
- **stack-selftest:** external (Prepare/)  <!-- AGENT_STACK §7.1 вариант B: каноны вне репо,
     CI их не видит; гоняется вручную при каждой правке канонов -->
- **blockers:** —
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Предыдущие поставки

`legacy-debt` (M) · `ci-red` (S) · `mypy-strict` (M) — завершены и слиты через
`merge_guard`; артефакты в `delivery/archive/`. CI на main зелёный
(`gates` + `delivery`), `main-guard` отрабатывает `skipped`.

## Backlog гейтов (обновлён 2026-07-28)

Долг назван явно, чтобы не выглядел покрытым (подробности — `delivery/STACK-ACCEPTANCE.md`):

- [x] **secrets-scanner** — `detect-secrets` подключён (poстaвкa legacy-debt),
      baseline пустой.
- [x] **`ruff-format`** — подключён; стилевой прогон вынесен в `afbd5f4` и
      внесён в `.git-blame-ignore-revs`.
- [x] **Молчаливые `except`** — 17 мест в `app/` получили логи с контекстом;
      baseline 20 → 3 сайта (только `scripts/spike/**`).
- [x] **mypy-заглушки** — `[[tool.mypy.overrides]]` удалён, 84 модуля чисто.
- [x] **mypy → strict** ✅ (поставка `mypy-strict`): 103 ошибки закрыты,
      `strict = true`, ноль `[[overrides]]`, один `type: ignore` с причиной.
- [ ] **Сложность функций** (`C901`/`PLR09xx`, 10 модулей) — рефакторинг
      оркестратора; при выносе `decide.py` заморозка переехала вместе с кодом.
- [ ] **Diff-coverage** ни разу не гонялся на реальном диффе кода (порог 70%).
- [ ] **UI**: `App.tsx` 165 строк / `ComparisonView.tsx` 106 — вынос контроллера
      в хук; порог для `*.tsx` пока откалиброван (200/20 с обоснованием).

## Контекст поставки

**Phase 7 ✅ закрыта живым прогоном 2026-07-30** (doc 25 v1.1, doc 06 v0.12):
агент заполнил форму, выбрал «Оплатить заказ», встал в handoff-паузу; человек
нажал сам; агент зафиксировал `order_number = WX9-1337`. Прогон вскрыл девять
дефектов, которых юниты не видели (см. `verify-report.md`) — все исправлены и
закрыты тестами (200).

Остаток по скорости: заполнение формы теперь один вызов модели (~5 s на
`qwen3:14b`); владелец попросил лёгкую nav-модель, прогретую к открытию
браузера. Прогрев реализован (`OllamaClient.warmup` до `browser.start`),
`qwen3:8b` качается для замера — следующая поставка.
