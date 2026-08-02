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
**частично**) · `ui-liquid-glass` (S) · `real-site-calibration` (S) ·
`protect-main-segments` (S) · `lint-contour` (S) · `scripts-canon` (S) ·
`orchestrator-complexity` (M) — все слиты через `merge_guard`; CI на main зелёный.
Артефакты в `delivery/archive/`.

## Долг гейтов закрыт целиком

- [x] secrets-scanner · `ruff-format` · молчаливые `except` · diff-coverage ·
      UI-рефактор.
- [x] **mypy strict** — `backend/app` (92 модуля) **и** `scripts/`.
- [x] **Контур ruff** — весь Python репозитория, кроме `scripts/spike/`
      (поставка `lint-contour`; тест контура с негативным контролем).
- [x] **Сложность функций** — разобраны все: 4 гейт-скрипта (`scripts-canon`) и
      7 функций ядра (`orchestrator-complexity`, включая `loop.run` — 30 ветвлений
      и 160 statements). **Заморозок сложности в проекте не осталось ни одной.**

**Правило на будущее:** заморозку сложности не возвращать — сначала разбирается
функция. Новый гейт-скрипт пишется набором проверок-функций, каждая возвращает
`(errors, warnings)`; новая стадия оркестратора — методом со `StepOutcome`.

## Хвосты (перенесены, не потеряны)

- `think:false` **без** схемы на `compare` — **36 %** реальной сессии, 81 % выхода —
  мысли. Входы для A/B уже в БД, скрипт разложения написан.
- Язык narrative: re-compare отвечает по-английски на русский вопрос.
- `I-H6` на реальных доках: top-10 кандидатов против сотен ссылок в сайдбаре (doc 21).
- `article.word_count` модель заполняет неверно (14 при статье на ~400 слов).
- Cooldown 30 s при N ≥ 4 — на реальном прогоне 0.7 % сессии; только с замером.
- Cancel во время attended-паузы не прерывает мгновенно.
- **`loop.py` — 493 LOC при лимите 500**: запаса мало, следующий вынос понадобится
  скоро (цена того, что машина состояний осталась одним читаемым файлом).
- **Attended/Tier 3 не проверялись живым прогоном** в поставке
  `orchestrator-complexity` (выбран минимальный объём eval-smoke) — ветки
  `_handle_blocker` и `_interact_step` держатся юнитами.

## Контекст поставки

Слот открыт без выбранного приоритета. Что лежит на столе, по весу:

1. **Качество результата** — рубрики, полнота evidence, язык narrative в
   compare-промпте. Скорость упёрлась в локальную генерацию 8–13 ток/с (железо).
2. **`compare` без схемы** — единственная измеримая цель по скорости на реальных
   сайтах (36 % сессии, 81 % выхода — мысли); входы для A/B уже в БД.
3. **Живой attended-прогон** после рефакторинга ядра — закрыть пробел eval-smoke.
4. **Открытый вопрос канона по robots** — владелец считает, что при работе «как будто
   заходит он сам» robots можно игнорировать. Дефолт не менялся; для осознанного
   исключения на прогон есть `respect_robots: false`. Смена дефолта — отдельное
   решение с правкой doc 01/03 и `CLAUDE.md`.
