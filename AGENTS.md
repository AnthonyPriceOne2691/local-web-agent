# AGENTS.md — local-web-agent

Проектные инструкции (архитектура, команды, границы) — в [CLAUDE.md](CLAUDE.md);
дизайн-решения — в [docs/](docs/README.md). Ниже — процессный контур.

## Canon stack / Agent Delivery Harness

- **Start here:** `AGENT_STACK.md` (order: Delivery → CQG → OKF).
  ⚠ Каноны лежат **вне репозитория**, в `Prepare/` (gitignored) — вариант B
  AGENT_STACK §7.1; следствия и компенсация: `delivery/STACK-ACCEPTANCE.md`.
- Process canon: `AGENT_DELIVERY_HARNESS.md`.
- Active delivery: `delivery/active/STATUS.md` — read before coding.
- **Order:** follow delivery phases. Do not oneshot large work.
- **Done:** only when verify oracles pass; never declare done on red.
- Prefer git worktree for class M/L (Delivery §5.1).
- Smoke/evals: `delivery/evals/smoke/` + `active/eval-smoke.md` (Delivery §6).
- Metrics on handoff: Delivery §9 / A.10 (`scripts/delivery_metrics.py --write`).
- Hooks if deployed: Delivery §10 — `.claude/settings.json` (stop-on-red, protect-main).
- Skills/prompts: `skills/README.md` (Delivery §11); no inline prompts (CQG).
  В этом проекте skills-каталога нет; LLM-промпты живут в `data/prompts/` как данные.
- Do **not** duplicate code-quality rules here — use `CODE_QUALITY_GATES.md` if present.
- Do **not** invent domain canon — use `knowledge/` / OKF if present.
- Deploy order for missing layers: Delivery → CQG → OKF (see `AGENT_STACK.md`).

## OKF knowledge bundle

- **Stack map first:** `AGENT_STACK.md` (Delivery → CQG → OKF).
- Bundle root: `knowledge/` (Open Knowledge Format v0.2).
- **Before answering canonical questions** (тиры действий, что жмёт человек,
  модели и флаги, что запрещено навсегда, порты): читай `knowledge/index.md` и
  ходи по ссылкам. Не выдумывай по памяти.
- **When changing invariants** in code: обнови связанный concept в том же
  изменении; освежи parent `index.md` и `log.md`. Это прибито:
  `scripts/okf_sync_gate.py` падает, если тронут путь из `implementation:`
  concept'а, а сам concept — нет.
- Дизайн-решения с историей версий живут в `docs/` (источник правды);
  `knowledge/` — выжимка инвариантов, дубля быть не должно
  (`knowledge/references/design-docs.md`).
- Bootstrap / формат: `OKF_KNOWLEDGE_BUNDLE.md` (в `Prepare/`, вне репо).
- Upstream spec (сверять при deploy/migrate):
  https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

## Быстрые гейты (перед объявлением done)

```bash
python scripts/delivery_check.py --diff-base origin/main   # фазы + circuit breakers
pre-commit run --all-files                                 # форма кода (CQG)
bash scripts/lint/check_baseline_ratchet.sh                # снимки только вниз
bash scripts/lint/check_gate_coverage.sh                   # все гейты подключены
python scripts/okf_validate.py knowledge/                  # формат канона домена
python scripts/okf_sync_gate.py --base origin/main         # code ↔ canon
bash delivery/evals/smoke/run.sh                           # product oracles
```

Мерж — только через `bash scripts/merge_guard.sh <branch>` (CQG §8.5): гейты
гоняются на **слитом** состоянии. Серверной защиты ветки нет (тариф), поэтому
force-push и обход админом остаются незакрытыми — см. STACK-ACCEPTANCE § Остатки.
