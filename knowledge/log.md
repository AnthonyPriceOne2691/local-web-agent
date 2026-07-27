# Knowledge Bundle Update Log

## 2026-07-28 (поставка mypy-strict)
* **Note (no canon change)**: код под `implementation:` четырёх concept'ов
  затронут типизацией (`mypy --strict`): аннотации сигнатур и параметризация
  дженериков. **Инварианты не менялись** — тиры действий, LLM-канон, запрет
  anti-bot bypass и runbook остаются как записаны. Гейт пропущен по
  `canon_drift_waiver` в STATUS (видимый waiver вместо env-переменной).

## 2026-07-27 (позже, поставка legacy-debt)
* **Note (no canon change)**: код под `implementation:` шести concept'ов изменён
  поставкой `legacy-debt` — добавлено логирование в `except`-ветки, исправлены
  аннотации типов и применён `ruff format`. **Инварианты не менялись**: тиры
  действий, механика attended-паузы, реестр действий, LLM-канон, запрет
  anti-bot bypass и runbook остались в силе как записаны.
  Затронутые concept'ы: [action tiers](/engineering/action-tiers.md),
  [attended mode](/engineering/attended-mode.md),
  [action registry](/engineering/action-registry.md),
  [LLM canon](/engineering/llm-canon.md),
  [no anti-bot bypass](/engineering/no-anti-bot-bypass.md),
  [local run](/ops/local-run.md).
  `okf_sync_gate` на этом мерже прошёл с `ALLOW_CANON_DRIFT=1` — осознанный
  дрейф «рефакторинг без смены инварианта» (канон OKF, § Waiver). Это запись
  того самого объяснения, которое waiver требует.
* **Structure**: у Layer 1 появились два новых модуля (`orchestrator/discovery.py`,
  `orchestrator/decide.py`) — вынесены из `loop.py` под лимит 500 LOC; описания
  инвариантов это не затронуло.

## 2026-07-27
* **Initialization**: создан OKF v0.2 bundle (`knowledge/`) при развёртывании
  канон-стека (AGENT_STACK §2.A). Upstream SPEC сверён в этот день:
  `**Version 0.2**` — совпадает с pinned в каноне, расхождений нет.
* **Creation**: seed-concept'ы — [overview](/product/overview.md),
  [action tiers](/engineering/action-tiers.md),
  [attended mode](/engineering/attended-mode.md),
  [LLM canon](/engineering/llm-canon.md),
  [action registry](/engineering/action-registry.md),
  [no anti-bot bypass](/engineering/no-anti-bot-bypass.md),
  [local run](/ops/local-run.md), [design docs](/references/design-docs.md).
* **Note**: канон дизайна остаётся в `docs/` (источник правды, версионируется);
  bundle держит выжимку инвариантов + карту реализации (`implementation:`).
