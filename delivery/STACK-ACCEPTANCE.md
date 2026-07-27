# Stack acceptance

**Date:** 2026-07-27
**Stack:** delivery@1.11 · cqg@1.7 · okf@1.5 (карта — stack-map@1.7)
**Где лежат каноны:** **вне репо** — `Prepare/` (добавлена в `.gitignore` по просьбе
владельца). Это вариант **B** из AGENT_STACK §7.1 со всеми его следствиями — см. «Остатки».

## Что развёрнуто

| Слой | Состояние | Примечание |
|---|---|---|
| ① delivery/ | deployed | дерево + CONSTITUTION + `delivery_check.py` + `delivery_metrics.py` + hook в `AGENTS.md`; active-поставка `tier3-exit-smoke` (class S) |
| ② гейты | deployed | 15 pre-commit хуков зелёные + 2 pre-push; baseline'ы сняты; адаптации — в карте ролей ниже |
| ③ knowledge/ | deployed | 14 файлов, 8 concept'ов, 6 с `implementation:`; upstream SPEC сверён 2026-07-27 (`Version 0.2` = pinned) |
| ④ CI + гейт мержа | **tooling** | `quality.yml` + `main-guard.yml` + `canon-freshness.yml`; `merge_guard.sh` + pre-push. Серверной защиты ветки нет (тариф) |

## Карта ролей гейтов

Инвариант — **роль**, а не имя файла (CQG «Применимость»).

| Роль | Канонический скрипт | В этом проекте | Статус |
|---|---|---|---|
| Доступ к настройкам только типизированно | `check_grep_gate.sh --rule config-access` | как есть | адаптирован: `TOOLING_RE` исключает сам harness (`scripts/lint/`, `okf_*`, `delivery_*`, `merge_guard`) — эти скрипты по контракту CQG §6 настраиваются через env, правило к ним неприменимо |
| DI вместо importlib-магии | `check_grep_gate.sh --rule di-indirection` | как есть | как есть (0 нарушений) |
| Сервис не знает про web | `check_grep_gate.sh --rule service-no-web` | как есть | как есть (0 нарушений); усилен `.importlinter`-контрактом `no-web-in-core` |
| Нет модулей-помоек | `check_grep_gate.sh --rule no-grab-bag-module` | как есть | как есть (0 нарушений) |
| Ошибки не молчат | `check_ast_gate.py --rule silent-except` | адаптирован | `SKIP_PARTS` += `/.venv/`, `/site-packages/`, `/node_modules/`: venv лежит внутри дерева, `rglob` затянул 168 чужих записей на первом прогоне. Baseline: 11 файлов / 20 сайтов |
| Длинные промпты — в файлы | `check_ast_gate.py --rule inline-prompt` | как есть | baseline 0 — промпты и так в `data/prompts/` |
| Длина файлов под контролем | `check_file_length.sh` | как есть | 134 файла; baseline 1 (`scripts/spike/benchmark_crawl.py` 663 — Phase 0 артефакт). Рядом живёт проектный `scripts/check_module_size.py` (doc 18, ≤500 LOC для `backend/app`) — в smoke S2 |
| Копипаст не растёт | `check_jscpd_gate.sh` | адаптирован | `-i` += `**/.venv/**,**/node_modules/**,**/dist/**` (та же причина); jscpd поставлен в `frontend/node_modules`; baseline 9 clone-пар |
| Warnings линтера не растут | `check_eslint_warnings.sh` | как есть | ESLint+Prettier поставлены в этой поставке (их не было); baseline 17 warnings, 0 errors |
| Направление зависимостей | `import-linter` | как есть | `.importlinter` написан по **фактическим** импортам (3 контракта: layers `api→research→orchestrator→…→schemas`, `schemas-leaf`, `no-web-in-core`) — 3 kept |
| Покрытие изменённого кода | `check_diff_coverage.sh` | как есть | не в pre-commit (ручной DoD, §3.5) — исключение объявлено в `not_wired_reason()`; в CI отдельным шагом |
| Снимки только вниз | `check_baseline_ratchet.sh` | как есть | pre-push + CI (нужен диff против remote-ref) |
| **Все гейты подключены** | `check_gate_coverage.sh` | как есть | 12 гейтов, подключено 11, осознанно нет 1 |
| Формат knowledge-bundle | `okf_validate.py` | как есть | 14 файлов, 0 ошибок |
| Канон ↔ код | `okf_sync_gate.py` | как есть | 6 concept'ов с `implementation:` |
| Фазы поставки + breakers | `delivery_check.py` | как есть | 0 ошибок, 0 предупреждений |
| Мерж только через гейты | `merge_guard.sh` | адаптирован | симлинкует `backend/.venv` и `frontend/node_modules` из основного клона в проверочный worktree: тулчейн gitignored, без этого гейты падали по окружению, а не по качеству кода. Проверено на живой ветке: 5/5 гейтов зелёные на слитом состоянии |

**Не подключено сознательно (названо вслух, а не обойдено молча):**

- **`ruff-format`** — переформатировал бы **68 файлов (~2.2k строк)** прямо в
  bootstrap-поставке. Это отдельный style-коммит с `.git-blame-ignore-revs` и
  waiver'ом circuit breaker'а — решение владельца, не побочный эффект
  развёртывания. `ruff` (lint, канонный select) подключён и зелёный.
- **secrets-scanner** (`detect-secrets`/`gitleaks`) — не поставлен в этой
  поставке; секретов в репо нет (OAuth-креды лежат в gitignored
  `Gdocs-tabs editor/`, auth-cookie — в gitignored `data/runs/profiles/`),
  но механической проверки нет. Пункт backlog в `delivery/active/STATUS.md`.

## Полнота, не только зелёность

- [x] `check_gate_coverage.sh` — OK (12 гейтов, 11 подключено, 1 осознанное исключение)
- [x] `pre-commit run --all-files` — зелено (15 хуков)
- [x] `stack_selftest.py Prepare/` — OK (41 блок, 0 провалов; версии канонов совпадают с таблицей §1)
- [x] Каждый гейт показал непустой набор файлов: grep 90 · AST 97 · file-length 134 · ESLint 13 · jscpd 9 clone-пар · import-linter 82 файла/202 зависимости · okf_validate 14

Первый прогон был красным дважды — и оба раза по делу, а не «настроим потом»:
① AST/jscpd тянули `.venv` (LINT_PY_SRC=`.`, venv внутри дерева) → адаптированы
исключения; ② `config-access` ругался на сами гейт-скрипты → сужена область.
Ни `STRICT=0`, ни удаления гейтов, ни baseline вверх не применялось.

## Остатки (не закрыто — и почему)

| Инвариант | Почему не закрыт | Компенсация |
|---|---|---|
| Force-push в `main` / обход админом | серверная защита ветки платная (приватный репо → GitHub Pro+) | правило «мерж только через `scripts/merge_guard.sh`»; pre-push хуки; `main-guard.yml` открывает issue на красное в main; hook `protect-main` (Delivery A.11) в `.claude/settings.json` |
| `stack_selftest` в CI | каноны вне репо (`Prepare/` в `.gitignore`) → CI их физически не видит | `scripts/stack_selftest.py` лежит в репо и гоняется **вручную с путём** `Prepare/` при каждой правке канонов. STATUS: `stack-selftest: external (Prepare/)` |
| Circuit breakers на работе прямо в `main` | `delivery_check --diff-base origin/main` считает `merge-base..HEAD`; при коммитах напрямую в main дифф пуст → breaker вырождается | работа класса M/L — в feature-ветке/worktree (Delivery §5.1), тогда breaker считает реально; для этой bootstrap-поставки лимит объёма не применялся осознанно |
| `needs:` у downstream-джобы | деплоя нет вовсе (локальный продукт, ничего не публикуется) | n/a по причине, а не забыто: как только появится publish/deploy-джоба — обязана получить `needs: [gates, delivery]` |
| Diff-coverage порог 70% | скрипт подключён в CI, но на этой поставке не гонялся (дифф — конфиги и каноны, не прод-код) | первый реальный прогон — на следующей кодовой поставке |
| mypy `strict` | strict дал 146 ошибок в 40 из 82 модулей — заморозка половины базы в overrides сделала бы гейт декоративным | базовый mypy зелёный + тающий список `[[tool.mypy.overrides]]` из 12 легаси-модулей; ужесточение — пункт backlog |

## Разбор: где эта процедура подвела

Записывать КАЖДЫЙ случай, когда приёмка показала зелено, а дыра была.
Формат: симптом → корневая причина → что добавлено в harness → как проверено.

### 2026-07-27 — baseline из чужого кода выглядел бы как «гейт работает»

- **Симптом:** `--generate` для `silent-except` дал 180 файлов / 385 сайтов при
  82 модулях в проекте. Если бы никто не посмотрел в снимок, гейт остался бы
  зелёным навсегда: 168 записей — это `site-packages`, они не меняются.
- **Причина (механизм):** `check_ast_gate.py` перечисляет файлы через
  `Path.rglob`, а не `git ls-files` (как grep-гейты), и `SKIP_PARTS` не содержал
  venv. При `LINT_PY_SRC=.` (единственный способ покрыть и `backend/app`, и
  `cli/` одним корнем) внутрь области попал `backend/.venv`.
- **Усиление:** `SKIP_PARTS` += `/.venv/`, `/site-packages/`, `/node_modules/`;
  та же правка для jscpd (`-i`). В приёмку добавлен пункт «каждый гейт показал
  непустой **и осмысленный** набор файлов» — не только непустой.
- **Проверено воспроизведением:** снимок удалён и пересобран — 11 файлов /
  20 сайтов, все из `backend/app`; число согласуется с независимым источником
  (ruff `S110`/`SIM105` указывает на те же 5 модулей).

### 2026-07-27 — «гейт мержа развёрнут» ≠ «гейт мержа работает»

- **Симптом:** `merge_guard.sh` лежал на месте, `chmod +x` сделан, в чеклисте
  выглядел закрытым. Первый реальный прогон на живой ветке: 4 из 5 гейтов
  FAIL — `backend/.venv/bin/python: No such file or directory`.
- **Причина:** гейт проверяет слитое состояние в **свежем worktree**, а тулчейн
  (`backend/.venv`, `frontend/node_modules`) gitignored и там отсутствует. Хуки
  зовут интерпретатор по фиксированному пути. То есть скрипт был бы «красным
  всегда» — и первый же мерж прошёл бы мимо него как «ну он вечно падает».
- **Усиление:** в `merge_guard.sh` добавлен симлинк тулчейна из основного клона;
  в приёмку добавлено правило: **каждый гейт-скрипт обязан быть прогнан хотя бы
  раз на реальном входе**, а не только положен в репозиторий. Наличие файла —
  не доказательство работоспособности (тот же класс ошибки, что «зелёный гейт,
  который ничего не сканирует»).
- **Проверено воспроизведением:** заведена пробная ветка с коммитом, прогон
  `DRY_RUN=1 merge_guard.sh` → сначала 4 FAIL (воспроизведение), после правки —
  5/5 OK; ветка удалена, в main перенесён только фикс скрипта.

### 2026-07-27 — гейт ругался на сам harness

- **Симптом:** `config-access` падал на `check_ast_gate.py`, `okf_validate.py`,
  `okf_sync_gate.py` — «нарушение вне baseline».
- **Причина:** правило «настройка только через типизированный `config.X`»
  адресовано прод-коду, а гейт-скрипты по контракту CQG §6 читают `os.environ`
  (`LINT_PY_SRC`, `STRICT`, `BASE`, `OKF_BUNDLE`). При `LINT_PY_SRC=.` они попали
  в область правила.
- **Усиление:** в `check_grep_gate.sh` добавлен `TOOLING_RE` — harness исключён
  из области **всех** grep-правил, с причиной в комментарии. Занесение в
  baseline было бы хуже: снимок, который никогда не растает, врёт про долг.
- **Проверено:** прод-код по-прежнему сканируется (90 файлов), правило ловит
  реальное нарушение — `backend/app/contracts/rules/budget.py` остался в baseline
  с 2 записями, а не исчез вместе с исключением.
