# Active delivery status

- **slug:** next-up
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
- **phase:** specify
- **builder:** agent:claude-code
- **verifier:** human:anthony
- **human_ok_spec:** n/a
- **human_ok_plan:** n/a
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
- **ci-oracles:** tooling
  <!-- CI есть; гейт мержа в репо (merge_guard + pre-push). Серверная защита ветки
       платная для приватного репо, поэтому force-push в main и обход админом не
       закрыты — остаток в delivery/STACK-ACCEPTANCE.md § Остатки. -->
- **worktree:** none
- **hooks:** claude
- **stack-selftest:** external (Prepare/)
- **blockers:** приоритет не выбран — слот открыт по остатку, а не решён
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Предыдущие поставки

`legacy-debt` (M) · `ci-red` (S) · `mypy-strict` (M) · `tier3-exit-smoke` (S) ·
`nav-model-split` (S) · `synth-speed` (S) · `session-throughput` (S, закрыта
**частично**) · `ui-liquid-glass` (S) — все слиты через `merge_guard`; CI на main
зелёный. Артефакты в `delivery/archive/`.

## Backlog гейтов

- [x] **secrets-scanner** — `detect-secrets`, baseline пустой.
- [x] **`ruff-format`** — подключён, стилевой прогон в `afbd5f4`.
- [x] **Молчаливые `except`** — baseline 20 → 3 сайта (только `scripts/spike/**`).
- [x] **mypy-заглушки** сняты; **mypy → strict** ✅ (86 модулей).
- [x] **Diff-coverage** ✅ прогнан на реальном диффе кода (PR #7).
- [ ] **Сложность функций** (`C901`/`PLR09xx`, 10 модулей) — рефакторинг оркестратора.
- [x] **UI-рефактор** ✅ (поставка `ui-liquid-glass`): `App.tsx` → композиция,
      логика в `useSession` + `useSessionStream`.

## Хвосты из session-throughput (перенесены, не потеряны)

- `think:false` **без** схемы на `compare` — потолок ≈ 7 % сессии. Замер дешёвый:
  входы для A/B уже в БД, скрипт разложения написан.
- Cooldown 30 s при N ≥ 4 — нужен ли сейчас. Только с замером троттлинга, иначе
  «ускорение» обернётся деградацией на длинной сессии.
- `article.word_count` модель заполняет неверно (14 при статье на ~400 слов).

## Контекст поставки

Слот открыт без выбранного приоритета. Что лежит на столе, по весу:

1. **Real-site калибровка** — все числа проекта получены на локальных фикстурах, а
   реальная работа идёт по публичным сайтам. Живой прогон Tier 3 показал цену этого
   разрыва: девять дефектов, которых юниты не видели.
2. **Качество результата вместо скорости** — рубрики, язык narrative, полнота
   evidence. Скорость упёрлась в локальную генерацию 8–13 ток/с, и это свойство
   железа, а не кода.
3. **Хвосты из session-throughput**: `think:false` без схемы на `compare` (≈ 7 %
   сессии), нужен ли cooldown 30 s при N ≥ 4, неверный `article.word_count`.
4. **Сложность функций** (`C901`/`PLR09xx`, 10 модулей) — последний пункт долга гейтов.
