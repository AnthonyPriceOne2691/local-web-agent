# Tasks

Поставка `legacy-debt` (class M). Предыдущая поставка `tier3-exit-smoke` ждёт
человека (живой Tier 3 прогон) и лежит в main; её mini-spec — в git-истории
этого файла, вернуть после мержа.

## Slice 1 — ошибки не молчат (CQG §1.5)

- [ ] T1.1: `app/api/routes_runs.py`, `app/api/routes_sessions.py` (2 сайта)
- [ ] T1.2: `app/browser/playwright_session.py` (3 сайта)
- [ ] T1.3: `app/orchestrator/{loop,capture,interaction}.py` (8 сайтов)
- [ ] T1.4: `app/research/{runner,actions/gdocs_export}.py` (2 сайта)
- [ ] T1.5: `app/storage/sqlite_store.py`, `app/vision/analyzer.py` (2 сайта)
- [ ] T1.6: снять `S110/S112/SIM105` из `per-file-ignores`, переснять
      `silent_except_baseline.txt` вниз (останется только `scripts/spike/**`)

## Slice 2 — типы (mypy без заглушек)

- [ ] T2.1: 39 ошибок в 8 модулях (`loop.py`, `runner.py`, `llm_planner.py`,
      `compare_synthesizer.py`, `candidate_queue.py`, `path_hints.py`,
      `playwright_session.py`, `consent.py`, `analyzer.py`, `gdocs.py`)
- [ ] T2.2: удалить блок `[[tool.mypy.overrides]]`; `mypy app` зелёный

## Slice 3 — фронт и безопасность

- [ ] T3.1: ESLint `--fix` (import/order) + осмысленные правки остатка → 0 warnings
- [ ] T3.2: переснять `eslint_warnings_baseline.txt` вниз (17 → 0)
- [ ] T3.3: `detect-secrets` в `.pre-commit-config.yaml` + baseline + шаг в `quality.yml`

## Slice 4 — формат и закрытие

- [ ] T4.1: `ruff format` по проекту **отдельным коммитом** + `.git-blame-ignore-revs`
      + `git config blame.ignoreRevsFile`
- [ ] T4.2: подключить `ruff-format` хук в pre-commit (после того как база чистая)
- [ ] T4.3: 191 тест + smoke S1–S5 + `pre-commit run --all-files` зелёные
- [ ] T4.4: `verify-report.md` + `delivery_metrics.py --write`
- [ ] T4.5: `merge_guard.sh fix/legacy-debt main` → мерж → push
- [ ] T4.6: вернуть `tier3-exit-smoke` в `active/` (STATUS + tasks) — он не завершён
