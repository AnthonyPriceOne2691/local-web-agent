# Active delivery status

- **slug:** ui-liquid-glass
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
  <!-- Класс S, хотя файлов много: изменение живёт целиком в одном слое
       (`frontend/src`), бэкенд и контракты не тронуты, деплоя нет, откат =
       revert одного коммита. Если по ходу потребуется правка API или схем —
       поставка переклассифицируется в M со спекой, а не «дотянется» тихо. -->
- **phase:** verify
- **builder:** agent:claude-code
- **verifier:** human:anthony     <!-- визуал и формулировки принимает владелец: это вкус, не гейт -->
- **human_ok_spec:** n/a          <!-- class S: mini-spec в tasks.md (§2.2) -->
- **human_ok_plan:** n/a
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
  <!-- Фронт закрыт не юнитами, а гейтами сборки (tsc), eslint-ратчетом и
       визуальной проверкой скриншотами. Названо честно: автотестов UI нет. -->
- **ci-oracles:** tooling
  <!-- CI есть (.github/workflows/quality.yml); гейт мержа в репо (scripts/merge_guard.sh
       + pre-push + needs:). Серверная защита ветки — платная для приватного репо
       (Pro+), поэтому НЕ закрыты: force-push в main и обход админом. Остаток
       зафиксирован в delivery/STACK-ACCEPTANCE.md § Остатки. -->
- **worktree:** none (ветка `feat/ui-liquid-glass`)
- **hooks:** claude    <!-- stop-on-red + protect-main, .claude/settings.json -->
- **stack-selftest:** external (Prepare/)  <!-- AGENT_STACK §7.1 вариант B: каноны вне репо,
     CI их не видит; гоняется вручную при каждой правке канонов -->
- **blockers:** —
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Предыдущие поставки

`legacy-debt` (M) · `ci-red` (S) · `mypy-strict` (M) · `tier3-exit-smoke` (S) ·
`nav-model-split` (S) · `synth-speed` (S) · `session-throughput` (S, закрыта
**частично** — итог и перенесённые хвосты в
`delivery/archive/2026-08-01-session-throughput/tasks.md`). Все слиты через
`merge_guard`; CI на main зелёный.

## Backlog гейтов

- [x] **secrets-scanner** — `detect-secrets`, baseline пустой.
- [x] **`ruff-format`** — подключён, стилевой прогон в `afbd5f4`.
- [x] **Молчаливые `except`** — baseline 20 → 3 сайта (только `scripts/spike/**`).
- [x] **mypy-заглушки** сняты; **mypy → strict** ✅ (86 модулей).
- [x] **Diff-coverage** ✅ прогнан на реальном диффе кода (PR #7).
- [ ] **Сложность функций** (`C901`/`PLR09xx`, 10 модулей) — рефакторинг оркестратора.
- [ ] **UI-рефактор** (`App.tsx` → хук-контроллер, `ComparisonView`) — закрывается
      этой поставкой.

## Хвосты из session-throughput (перенесены, не потеряны)

- `think:false` **без** схемы на `compare` — потолок ≈ 7 % сессии. Замер дешёвый:
  входы для A/B уже в БД, скрипт разложения написан.
- Cooldown 30 s при N ≥ 4 — нужен ли сейчас. Только с замером троттлинга, иначе
  «ускорение» обернётся деградацией на длинной сессии.
- `article.word_count` модель заполняет неверно (14 при статье на ~400 слов).

## Контекст поставки

Владелец: «взгляни на UI как опытный UI/UX, переделай визуал под жидкое стекло, а
все текстовые поля с технической информацией перепиши по-человечески; язык — только
английский».

Исходное состояние честно: интерфейс работает, но выглядит как дефолтный Tailwind
(плоские slate/blue плашки, тёмный сайдбар рядом со светлыми панелями), тексты
двуязычные (RU в паузах, тумблере, примерах), а наружу торчит внутренняя лексика
проекта — `runs`, `intent`, `running_tools`, `extract_now`, `Dimensions`, `rubric`,
`loading <id>…`. Человеку, который не писал этот бэкенд, половина подписей непрозрачна.
