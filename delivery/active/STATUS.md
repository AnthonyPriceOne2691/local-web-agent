# Active delivery status

- **slug:** tier3-exit-smoke
- **stack:** delivery@1.11, cqg@1.7, okf@1.5
- **class:** S
- **phase:** tasks
  (подфазы clarify/analyze в STATUS не выносятся — см. §2.1)
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
- **worktree:** none (S)
- **hooks:** claude    <!-- stop-on-red + protect-main, .claude/settings.json -->
- **stack-selftest:** external (Prepare/)  <!-- AGENT_STACK §7.1 вариант B: каноны вне репо,
     CI их не видит; гоняется вручную при каждой правке канонов -->
- **blockers:** живой exit-смоук требует человека у клавиатуры (Tier 3 по построению:
  необратимую кнопку жмёт человек) — ждём окна у Антона
- **waivers:** —
- **circuit_breakers:** defaults from AGENT_DELIVERY_HARNESS.md §3.4

## Backlog гейтов (заведён при развёртывании стека, 2026-07-27)

Долг назван явно, чтобы не выглядел покрытым (подробности — `delivery/STACK-ACCEPTANCE.md`):

- [ ] **secrets-scanner** (`detect-secrets`/`gitleaks`) не подключён — механической
      проверки на секреты нет; сейчас держится на `.gitignore` и дисциплине.
- [ ] **`ruff-format`** не подключён: переформатирует 68 файлов — нужен отдельный
      style-коммит + `.git-blame-ignore-revs` + решение человека.
- [ ] **mypy → strict**: сейчас базовый режим + 12 модулей в
      `[[tool.mypy.overrides]]`; strict даёт 146 ошибок в 40 модулях.
- [ ] **Молчаливые `except`** (S110/S112/SIM105 в 5 модулях, 20 сайтов в
      `silent_except_baseline.txt`) — нужны осмысленные логи, а не
      `contextlib.suppress` ради зелени (CQG §1.5).
- [ ] **Diff-coverage** ни разу не гонялся на реальном диффе кода (порог 70%).

## Контекст поставки

Phase 7 Tier 3 handoff (`docs/25-action-framework.md` v1.0) — code-complete
(коммит `8a357a9`, 191 тест). Осталось единственное: **живой exit-прогон** по
референс-сценарию (doc 06 § Phase 6–7) на фикстуре `store_checkout`, где
финальную кнопку нажимает человек. Детали шагов — `tasks.md`.
