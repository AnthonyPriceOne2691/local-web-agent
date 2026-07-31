# Active delivery status

- **slug:** nav-model-split
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
- **phase:** verify
- **builder:** agent:claude-code
- **verifier:** human:anthony     <!-- решение «модель X на класс решений Y» принимает владелец -->
- **human_ok_spec:** n/a          <!-- class S: mini-spec в tasks.md (§2.2) -->
- **human_ok_plan:** n/a
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
- **ci-oracles:** tooling
  <!-- CI есть (.github/workflows/quality.yml); гейт мержа в репо (scripts/merge_guard.sh
       + pre-push + needs:). Серверная защита ветки — платная для приватного репо
       (Pro+), поэтому НЕ закрыты: force-push в main и обход админом. Остаток
       зафиксирован в delivery/STACK-ACCEPTANCE.md § Остатки. -->
- **worktree:** none (ветка feat/nav-model-split)
- **hooks:** claude    <!-- stop-on-red + protect-main, .claude/settings.json -->
- **stack-selftest:** external (Prepare/)  <!-- AGENT_STACK §7.1 вариант B: каноны вне репо,
     CI их не видит; гоняется вручную при каждой правке канонов -->
- **blockers:** —
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Предыдущие поставки

`legacy-debt` (M) · `ci-red` (S) · `mypy-strict` (M) · `tier3-exit-smoke` (S) —
завершены и слиты через `merge_guard`; артефакты в `delivery/archive/`.
CI на main зелёный (`gates` + `delivery`), `main-guard` отрабатывает `skipped`.

## Backlog гейтов (обновлён 2026-07-28)

Долг назван явно, чтобы не выглядел покрытым (подробности — `delivery/STACK-ACCEPTANCE.md`):

- [x] **secrets-scanner** — `detect-secrets` подключён (поставка legacy-debt),
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

Владелец просил лёгкую nav-модель, прогретую к моменту открытия браузера. Замер
`qwen3:8b` против `qwen3:14b` сделан 2026-07-31 **на одном коде** (два инстанса
API, 8002/8003) и показал, что «просто заменить модель» — неверный ответ:
лёгкая быстрее вдвое на локальных по DOM решениях и стабильно хуже на выборе
ссылки по смыслу (3 прогона из 3 с `G-H2` и лишним хопом в 404).

Отсюда поставка: **не подмена модели, а маршрутизация решений** — лёгкая на
интеракцию, тяжёлая на анализ и синтез. Числа и приёмка — в `tasks.md`.
