# Tasks

Разбивка плана (`plan.md` § Шаги) на проверяемые пункты. Каждый — отдельный коммит,
гейты зелёные после каждого.

## 1. Тесты инвариантов — ДО кода

- [x] T1.1 cancel на трёх границах: перед OBSERVE, перед PLAN, между vision-вызовами;
      статус `canceled`, синтез не запускается.
- [x] T1.2 early stop G-S1: три страницы без новых релевантных ссылок → SYNTHESIZE,
      `metadata.early_stop` заполнен.
- [x] T1.3 attended-пауза на `captcha` **и** на `login_wall`; после resume —
      `reobserve_in_place` (без повторного `goto`).
- [x] T1.4 unattended на блокере: `metadata.blocked_by`, прогон завершается, статус
      `blocked` в результате.
- [x] T1.5 handoff: после `handoff_done` агент не выбирает следующее действие —
      только фиксация исхода.
- [x] T1.6 анти-залипание: `click` / `fill` / `fill_form` по своим лимитам,
      `metadata.action_loop_guard`.
- [x] T1.7 `extract_now` guard: второй подряд → выход; `pages_left <= 0` → выход.
- [x] T1.8 исключение в середине прогона → `failed`, запись сохранена,
      `error_message` с именем типа (M-H4), браузер закрыт.
- [x] T1.9 `candidate_queue` покрытие с 74 % до ≥ 85 % — именно те ветки, которые
      буду двигать.
- [x] T1.10 все новые тесты зелёные **на текущем коде** (иначе они описывают не то,
      что есть).

## 2. Мелкие функции (по одной, заморозка снимается сразу)

- [x] T2.1 `vision/selection.py::select_vision_jobs` (11).
- [x] T2.2 `reporting/markdown.py::build_report` (11).
- [x] T2.3 `extraction/synthesis_validator.py::validate` (11).
- [x] T2.4 `orchestrator/decide.py::plan_validated` (12).

## 3. Кандидаты и Layer 2

- [x] T3.1 `navigation/candidate_queue.py::build_candidates` (18/16): источники
      (ссылки страницы, slug-пробы, sitemap, probe-links) — отдельными сборщиками,
      скоринг остаётся общим.
- [x] T3.2 `research/runner.py::run_message` (13) и `_run_llm_plan` (13): разделить
      «разобрать план» и «исполнить шаг»; tool-ноты и M-H* на месте.

## 4. `run()` — последним

- [x] T4.1 `RunState` (mutable dataclass) + `StepOutcome` (CONTINUE/PROCEED/STOP).
- [x] T4.2 `_prepare()`: валидация конфига, warmup, robots, rate, пробы, sitemap,
      профиль, старт браузера (видимость окна — по задаче-действию).
- [x] T4.3 `_observe_step()`: navigate+observe, блокеры, attended-развилка.
- [x] T4.4 `_plan_step()`: кандидаты, G-S1, `plan_validated`, запись шага.
- [x] T4.5 `_act_step()`: диспетч по действию, тиры, анти-залипание.
- [x] T4.6 `_finalize()`: vision, синтез, валидация результата, отчёт.
- [x] T4.7 `loop.py` ≤ 500 LOC сохранён (новые модули рядом, как `decide.py`).

## 5. Гейты и заморозки

- [x] T5.1 Снять все семь `per-file-ignores` сложности из `backend/pyproject.toml`.
- [x] T5.2 `ruff --isolated --select C901,PLR0912,PLR0915 backend/app` — пусто.
- [x] T5.3 Покрытие затронутых модулей не ниже исходного (loop 92 %, runner 89 %,
      markdown 97 %, selection 98 %, validator 97 %, decide 99 %).
- [x] T5.4 `lint-imports` зелёный: направление зависимостей не поехало.

## 6. Продуктовый прогон (eval-smoke, обязателен для класса M)

- [x] T6.1 ✅ UC-2: winner 8901, порядок 95 > 75 > 40 против записанного 95 > 75 > 50 —
      совпал (сессия `7b546c74527d`).
- [ ] T6.2 Tier 3 attended на `store_checkout` — **НЕ делался**: владелец выбрал
      минимальный объём прогона. Ветка `_interact_step` держится юнитами.
- [ ] T6.3 Real-site сессия — **НЕ делалась**: тот же выбор объёма.
- [x] T6.4 ✅ объём согласован до запуска; после прогона модель выгружена
      (`ollama ps` пуст), тестовый инстанс 8002 остановлен.

## 7. Закрытие

- [x] T7.1 `verify-report.md`: таблица «инвариант → тест», список всех отклонений от
      правила «только перестановка» (в идеале пустой).
- [x] T7.2 doc 02 / 03 / 25 — если поменялось имя шага, на которое ссылается док;
      версии и changelog.
- [ ] T7.3 PR + зелёный CI + мерж через `merge_guard` (по слову владельца).
