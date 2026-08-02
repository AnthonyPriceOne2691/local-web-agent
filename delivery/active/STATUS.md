# Active delivery status

- **slug:** scripts-canon
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
- **phase:** verify
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
- **blockers:** —  <!-- приоритет задан владельцем: остаток долга гейтов -->
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Предыдущие поставки

`legacy-debt` (M) · `ci-red` (S) · `mypy-strict` (M) · `tier3-exit-smoke` (S) ·
`nav-model-split` (S) · `synth-speed` (S) · `session-throughput` (S, закрыта
**частично**) · `ui-liquid-glass` (S) · `real-site-calibration` (S) ·
`protect-main-segments` (S) · `lint-contour` (S) — все слиты через `merge_guard`;
CI на main зелёный. Артефакты в `delivery/archive/`.

## Backlog гейтов

- [x] **secrets-scanner** — `detect-secrets`, baseline пустой.
- [x] **`ruff-format`** — подключён; стилевые прогоны `afbd5f4` и `1c0ce0c`.
- [x] **Молчаливые `except`** — baseline 20 → 3 сайта (только `scripts/spike/**`).
- [x] **mypy-заглушки** сняты; **mypy → strict** ✅ (89 модулей).
- [x] **Diff-coverage** ✅ прогнан на реальном диффе кода (PR #7).
- [x] **UI-рефактор** ✅ (поставка `ui-liquid-glass`).
- [x] **`scripts/` и `cli/` в контуре ruff** ✅ (поставка `lint-contour`): корневой
      `ruff.toml` через `extend`, тест контура с негативным контролем, doc 18 v0.3.
- [x] **mypy на `scripts/`** ✅ (поставка `scripts-canon`): `--strict` зелёный,
      подключён хуком `mypy-scripts`.
- [x] **Сложность гейт-скриптов** ✅ разобрана целиком (было 47/25/17/15) — заморозок
      для `scripts/` больше нет; тесты писались ДО разбора.
- [ ] **Сложность backend** — 7 модулей: `loop.run` (30 ветвлений, 160 statements),
      `candidate_queue`, `decide`, `runner`, `markdown`, `selection`,
      `synthesis_validator`. Отдельная поставка **класса M**: рефакторинг ядра
      оркестратора влияет на поведение агента, нужны спека, план и подпись владельца
      (§2.2/§3.3) плюс продуктовый прогон в проверке.

## Хвосты из session-throughput (перенесены, не потеряны)

- `think:false` **без** схемы на `compare` — на фикстурах потолок ≈ 7 % сессии, но
  **36 % на реальных сайтах** (замер `real-site-calibration`), из них 81 % выхода —
  мысли. Входы для A/B уже в БД, скрипт разложения написан.
- Cooldown 30 s при N ≥ 4 — на реальном прогоне 0.7 % сессии, выигрыш заведомо мал;
  менять только с замером троттлинга.
- `article.word_count` модель заполняет неверно (14 при статье на ~400 слов).

## Хвосты из real-site-calibration

- `I-H6` на реальных доках: top-10 кандидатов против сотен ссылок в сайдбаре —
  лечится в doc 21 (аннотация кандидатов интентом, penalty версионных ссылок).
- Обход — **46 %** реальной сессии (против 20 % на фикстурах). Оптимизировать имеет
  смысл его и `compare`, а не синтез одного сайта.
- Cancel во время attended-паузы не прерывает мгновенно (gate ждёт resume/timeout).

## Контекст поставки

Владелец (02.08): закрыть остаток долга гейтов. Закрыта та его часть, что не меняет
поведение агента: типы и сложность гейт-скриптов. Сложность backend вынесена в
отдельную поставку класса M — см. бэклог выше и `verify-report.md` § Ограничения.

Что лежит на столе дальше, по весу:

0. **Сложность backend (класс M)** — ждёт спеки/плана и подписи владельца.
1. **Качество результата вместо скорости** — рубрики, полнота evidence, язык
   narrative в compare-промпте (re-compare отвечает по-английски на русский вопрос).
   Скорость упёрлась в локальную генерацию 8–13 ток/с — это свойство железа.
2. **`compare` без схемы** — единственная измеримая цель по скорости на реальных
   сайтах (36 % сессии, 81 % выхода — мысли); входы для A/B уже в БД.
3. **Открытый вопрос канона по robots** — владелец считает, что при работе «как будто
   заходит он сам» robots можно игнорировать. Дефолт не менялся; для осознанного
   исключения на прогон есть `respect_robots: false`. Смена дефолта — отдельное
   решение с правкой doc 01/03 и `CLAUDE.md`.
