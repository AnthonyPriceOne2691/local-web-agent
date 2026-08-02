# Active delivery status

- **slug:** orchestrator-complexity
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** M
- **phase:** implement
- **builder:** agent:claude-code
- **verifier:** human:anthony
- **human_ok_spec:** yes  <!-- 02.08, владелец: «делай всю», включая run() -->
- **human_ok_plan:** n/a  <!-- требуется только для класса L (§3.3) -->
- **shape-oracles:** cqg-deployed
- **behavior-oracles:** tests-present
- **ci-oracles:** tooling
  <!-- CI есть; гейт мержа в репо (merge_guard + pre-push). Серверная защита ветки
       платная для приватного репо, поэтому force-push в main и обход админом не
       закрыты — остаток в delivery/STACK-ACCEPTANCE.md § Остатки. -->
- **worktree:** none (ветка `refactor/orchestrator-complexity`)
- **hooks:** claude
- **stack-selftest:** external (Prepare/)
- **blockers:** —
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4
  <!-- Ожидаемый объём близок к порогу (25 файлов / 800 LOC). Упрёмся — дробим на
       две поставки, waiver не выписываем: план §Оценка. -->

## Предыдущие поставки

`legacy-debt` (M) · `ci-red` (S) · `mypy-strict` (M) · `tier3-exit-smoke` (S) ·
`nav-model-split` (S) · `synth-speed` (S) · `session-throughput` (S, закрыта
**частично**) · `ui-liquid-glass` (S) · `real-site-calibration` (S) ·
`protect-main-segments` (S) · `lint-contour` (S) · `scripts-canon` (S) — все слиты
через `merge_guard`; CI на main зелёный. Артефакты в `delivery/archive/`.

## Backlog гейтов

- [x] **secrets-scanner** · **`ruff-format`** · **молчаливые `except`** ·
      **mypy strict** (app + scripts) · **diff-coverage** · **UI-рефактор** ·
      **контур ruff** (backend + cli + scripts) · **сложность гейт-скриптов**.
- [ ] **Сложность backend** — эта поставка: 7 функций, главная `loop.run`
      (30 ветвлений, 160 statements).

## Хвосты (перенесены, не потеряны)

- `think:false` **без** схемы на `compare` — **36 %** реальной сессии, 81 % выхода —
  мысли. Входы для A/B уже в БД.
- Cooldown 30 s при N ≥ 4 — на реальном прогоне 0.7 % сессии; только с замером.
- `article.word_count` модель заполняет неверно (14 при статье на ~400 слов).
- `I-H6` на реальных доках: top-10 кандидатов против сотен ссылок в сайдбаре (doc 21).
- Cancel во время attended-паузы не прерывает мгновенно.
- Язык narrative: re-compare отвечает по-английски на русский вопрос.

## Контекст поставки

Владелец (02.08) подписал спеку и выбрал полный объём — включая `run()`.

Суть: семь функций держатся на `per-file-ignores`, и главная из них — единственное
место, где сходятся все инварианты прогона (cancel на границах, G-S1, attended-паузы,
тиры действий, анти-залипание, синтез, отчёт). Девять дефектов живого прогона Tier 3
нашлись именно там.

Порядок работы (план §Шаги): тесты инвариантов **до** кода → мелкие функции →
`build_candidates` → `runner` → `run()` последним → снятие заморозок → продуктовый
прогон (UC-2 на фикстурах + Tier 3 attended + одна real-site сессия).

Правило диффа: только перестановка и извлечение. Найденный по дороге настоящий дефект
— отдельный коммит с тестом и упоминанием в verify-report, а не тихая правка внутри
рефакторинга.
