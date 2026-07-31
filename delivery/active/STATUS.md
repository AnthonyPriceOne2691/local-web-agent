# Active delivery status

- **slug:** session-throughput
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
- **phase:** tasks
- **builder:** agent:claude-code
- **verifier:** human:anthony     <!-- влияет на длительность сессий: принимает владелец -->
- **human_ok_spec:** n/a          <!-- class S: mini-spec в tasks.md (§2.2) -->
- **human_ok_plan:** n/a
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
- **ci-oracles:** tooling
  <!-- CI есть (.github/workflows/quality.yml); гейт мержа в репо (scripts/merge_guard.sh
       + pre-push + needs:). Серверная защита ветки — платная для приватного репо
       (Pro+), поэтому НЕ закрыты: force-push в main и обход админом. Остаток
       зафиксирован в delivery/STACK-ACCEPTANCE.md § Остатки. -->
- **worktree:** none
- **hooks:** claude    <!-- stop-on-red + protect-main, .claude/settings.json -->
- **stack-selftest:** external (Prepare/)  <!-- AGENT_STACK §7.1 вариант B: каноны вне репо,
     CI их не видит; гоняется вручную при каждой правке канонов -->
- **blockers:** — (приоритет подтверждён владельцем 2026-07-31)
- **worktree-note:** ветка `feat/session-throughput`
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Предыдущие поставки

`legacy-debt` (M) · `ci-red` (S) · `mypy-strict` (M) · `tier3-exit-smoke` (S) ·
`nav-model-split` (S) · `synth-speed` (S) — завершены и слиты через `merge_guard`;
артефакты в `delivery/archive/`. CI на main зелёный (`gates` + `delivery`).

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
- [x] **Diff-coverage** ✅ отработал на реальном диффе кода (PR #7, прогон
      30631474202): `model_router.py` 100 %, все затронутые файлы ≥ 89.5 % при
      пороге 70 % (`config` 98.6 · `navigator` 93.9 · `ollama_client` 89.5 ·
      `decide` 98.7 · `loop` 92.7). До этого гейт видел только исключённые файлы.
- [ ] **UI**: `App.tsx` 165 строк / `ComparisonView.tsx` 106 — вынос контроллера
      в хук; порог для `*.tsx` пока откалиброван (200/20 с обоснованием).

## Контекст поставки

`synth-speed` закрыла синтез **одного сайта**: на извлекающих интентах −68 %
выходных токенов при идентичном ответе, на `content_search`/`design_audit` рычаг
оказался нестабильным (350 ↔ 1265 токенов) и там сохранён канон. То есть для
основного сценария владельца (несколько сайтов + поиск статей) синтез одного сайта
ускорить **не удалось** — и дожимать его без нового замера не стоит.

Остаток по длительности многосайтовой сессии, ни разу не измеренный:

1. **Финальный `compare`** — один вызов на сессию, вход 24K при N>3, ответ по
   природе длинный. Сознательно не тронут в `synth-speed`.
2. **Структура сессии** — последовательный обход (D-7) + cooldown 30 s при N≥4.
   Cooldown — термальное решение для fanless M5; трогать только с замером
   троттлинга, иначе «ускорение» превратится в деградацию на 10 сайтах.

Альтернативы, если приоритет другой: UI-рефактор (`App.tsx`/`ComparisonView`),
сложность функций (`C901` в оркестраторе), real-site калибровка.
