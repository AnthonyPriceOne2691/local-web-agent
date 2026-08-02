# Verify report — orchestrator-complexity

**Date:** 2026-08-02
**Verifier:** human:anthony (спека и объём прогона), agent:claude-code (проверки)

## Что сделано

Семь функций, державшихся на `per-file-ignores`, разобраны. **Заморозок сложности в
проекте не осталось ни одной** — `ruff --isolated --select C901,PLR0912,PLR0915` по
`backend/app`, `cli` и `scripts` чист.

| Функция | Было | Стало |
|---|---|---|
| `loop.py::run` | **C901 30**, 30 ветвлений, **160 statements** | ≤ 10 |
| `candidate_queue::build_candidates` | 18 / 16 ветвлений | ≤ 10 |
| `runner::run_message` | 13 | ≤ 10 |
| `runner::_run_llm_plan` | 13 | ≤ 10 |
| `decide::plan_validated` | 12 | ≤ 10 |
| `synthesis_validator::validate` | 11 | ≤ 10 |
| `markdown::build_report` | 11 | ≤ 10 |
| `vision::select_vision_jobs` | 11 | ≤ 10 |

Новые модули (`loop.py` удержан ≤ 500 LOC): `run_state.py` (состояние прогона +
`StepOutcome`), `finalize.py` (результат и отчёт), `observe.py` (переход, ретрай,
redirect-guard, SPA-fallback, скриншот). Consent переехал в `capture.py`.

## Порядок работы: тесты до кода

Как и в `scripts-canon`: сначала тесты, прогнанные на **старом** коде, потом разбор.

| Инвариант `run()` | Тест |
|---|---|
| Отмена до OBSERVE — браузер никуда не идёт | `test_run_invariants::cancel_before_observe_stops_without_navigating` |
| Отмена между OBSERVE и PLAN — LLM не зовётся | `…::cancel_between_observe_and_plan_skips_llm` |
| Отмена перед синтезом — синтез пропускается | `test_orchestrator::cancel_before_synthesis_skips_llm` |
| Ранняя остановка G-S1 | `test_orchestrator_edges::early_stop_gs1_after_three_stale_pages` |
| Attended-пауза на captcha и на login_wall | `test_attended::attended_pause_resume_then_observe`, `…::attended_login_wall_pause_resume` |
| Без attended блокер завершает прогон | `test_attended::captcha_without_attended_still_blocks` |
| После handoff — только фиксация исхода | `test_tier3_handoff::after_handoff_agent_stops_acting` |
| Анти-залипание click / fill / fill_form | `test_run_invariants::repeated_click_stops_acting`, `test_tier3_handoff::repeated_fill_stops_acting`, `…::repeated_fill_form_stops_acting` |
| `extract_now` guard | `test_orchestrator_edges::extract_now_streak_breaks_loop` |
| Падение в середине → `failed` + имя типа + закрытый браузер | `test_run_invariants::crash_mid_run_fails_with_type_name_and_closes_browser` |
| Финализация: результат, длительность, `report.md` | `…::finalize_fills_result_and_writes_report` |
| Hard-нарушение конфига — отказ до браузера | `test_orchestrator_edges::config_hard_violation_fails_before_start` |
| Источники кандидатов P1–P4 и дедуп | `test_candidate_sources` (5 кейсов) |

Покрытие: `candidate_queue` 74 % → **100 %**, `loop.py` 92 % → **98 %**, общий
92 % → **93 %**. Тестов 302 (было 292).

## Отклонения от правила «только перестановка»

Правило поставки: дифф — перестановка и извлечение; изменение условия требует
отдельного объяснения.

**Отклонений нет.** Настоящих дефектов по дороге не нашлось, логика не менялась.
Сохранены и неочевидные тонкости, которые легко было потерять:

- проверка `handoff_done` осталась **только** у `click`/`fill` — у `fill_form` её не
  было и раньше (пачка полей до handoff не доходит по построению);
- браузер закрывается и на отменённом прогоне (`_finish_canceled` вызывает
  `_safe_close`, как делал прежний код);
- отмена проверяется на **обеих** границах состояний, а не один раз в начале цикла;
- `_early_stop` сбрасывает `just_visited` даже когда новых ссылок нет — иначе
  счётчик G-S1 считал бы одну страницу дважды.

## Находка из тестов (не дефект, но важно знать)

На **статичной** странице анти-залипание `click` недостижимо: раньше срабатывает
ранняя остановка G-S1 (три страницы подряд без новых релевантных ссылок). Поэтому
тестовая фикстура честно подгружает новую ссылку на каждый клик — как настоящая
кнопка «показать ещё». Это не обход проверки, а её условие.

## Продуктовый прогон (eval-smoke) ✅

Объём выбран владельцем: UC-2 на фикстурах. Сессия `7b546c74527d`, второй инстанс
API на 8002 с кодом ветки (рабочий 8001 не трогали).

| Критерий | Результат |
|---|---|
| Все сайты прочитаны | 3 из 3 `completed`, `excluded` пуст |
| Победитель и порядок | **8901 → 8903 → 8902**, 95 > 75 > 40 (записано 95 > 75 > 50) |
| Факты с цитатами | 2/2, 1/1, 2/2 — цитаты прошли сверку с DOM (S-H3) |
| Размерности + narrative | 5 размерностей, narrative называет разделы и объём |
| Стадии | OBSERVE, ACT, SYNTHESIZE присутствуют в каждом run'е |
| Модели выгружены | `ollama ps` пуст |

Разница в третьем счёте (40 против 50) — разброс локальной модели; критерием был
**порядок**, он совпал. Полные детали — `eval-smoke.md`.

## Гейты

`pytest` **302** · ruff · ruff format · `mypy --strict` (app 92 модуля + scripts) ·
module-size (`loop.py` 493) · pre-commit `--all-files` · `delivery_check` ·
`okf_sync_gate` · `lint-imports`.

## Честные ограничения

- **Прогон не покрывает attended/Tier 3**: ветки `_handle_blocker` и
  `_interact_step` на UC-2 не задействованы — их держат только юниты. Живого
  подтверждения этих веток в поставке нет (см. `eval-smoke.md` § Чего не проверяет).
- **Real-site прогон не делался** — по выбранному объёму. Значит, поведение на
  настоящих сайтах после разбора подтверждено только косвенно.
- `loop.py` — 493 LOC при лимите 500: запаса мало, следующий вынос понадобится
  скоро. Это цена того, что машина состояний осталась одним читаемым файлом.
