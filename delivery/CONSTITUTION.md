# Delivery constitution

**Version:** 1.0
**Ratified:** 2026-07-27
**Canon stack:** delivery@1.95 · cqg@2.40 · okf@1.18 · stack-map@1.52
<!-- версии из шапок канонов; каноны лежат ВНЕ репо (Prepare/, gitignored) —
     AGENT_STACK §7.1 вариант B, см. delivery/STACK-ACCEPTANCE.md -->
**CI:** deployed (github-actions) merge-gate: tooling   <!-- §10.4; серверная защита ветки — по тарифу -->

## Non-negotiables

- Done закрывается **зелёным CI-прогоном** (§10.4), не локальным «у меня прошло».
- `STRICT=0` / `git commit -n` — аварийная локальная мера, видимая в PR; в CI запрещены.
- Проектные инварианты, которые harness не отменяет (источник — `docs/`, [docs/README.md](../docs/README.md)):
  LLM только локально (Ollama), ноль телеметрии; единственный sanctioned outbound —
  экспорт в Google Docs по явному запросу; API bind только `127.0.0.1`;
  anti-bot bypass запрещён навсегда; необратимые действия на сайте жмёт человек
  (Tier 3 handoff, [docs/25](../docs/25-action-framework.md)).
- Design docs — источник правды: изменение дизайна = правка дока + changelog + bump версии.

## Process principles

1. Spec before broad implementation (class M/L).
2. Vertical slices; no oneshot of the whole plan.
3. Done = oracles (shape + behavior + product), never self-declaration alone.
4. Builder ≠ Verifier.
5. Agent mistake → strengthen harness (oracle / breaker / hook), not only prompts.
6. One `delivery/active` at a time.
7. Работа идёт в рамках фаз `docs/06-mvp-phases.md`; delivery-контур — процессная
   надстройка над ними, а не замена (фаза проекта ≠ фаза поставки).

## Coding-agent contract (thin ABC)

### Preconditions
- STATUS.md read; class S/M/L known; branch/worktree set.
- Before implement: artifacts per harness §2.2 (S: tasks; M/L: spec+plan+tasks + human_ok_spec).
- Перед инференсом на локальной модели — предупредить человека и дождаться «запускай»
  (32 GB RAM: 14B-модель ощутимо влияет на машину; после прогона выгружать).

### Invariants
- No secrets in git; no force-push to main; no done-on-red; no silent scope creep.
- Не коммитить `Gdocs-tabs editor/` (OAuth-креды) и `data/runs/**` (auth-cookie профили).

### Governance
- Human OK on spec (M/L). Human OK on plan (L / risky). HITL on prod deploy, data migrations, security-sensitive changes.
- HITL на живых прогонах с реальным сайтом и на любом Tier 2/3 действии агента (docs/25).

### Recovery
- On oracle red: fix ≤ retry budget, else escalate in STATUS.md.

## Pointers to sibling layers (fill if deployed)

- Code shape oracles: `CODE_QUALITY_GATES.md` (в `Prepare/`, вне репо) — [x] deployed
  (конфиги и скрипты — в репо: `.pre-commit-config.yaml`, `scripts/lint/`)
- Domain canon: `OKF_KNOWLEDGE_BUNDLE.md` / `knowledge/` — [x] deployed
- Agent hooks (§10): [x] deployed (claude — `.claude/settings.json`)
- CI oracles (§10.4, workflow per CQG §8): [x] deployed (`.github/workflows/quality.yml`)
- Skills catalog: `skills/README.md` — [x] absent (промптов-скиллов нет; LLM-промпты
  проекта живут в `data/prompts/` — это данные, не skills)
