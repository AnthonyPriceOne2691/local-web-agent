# Knowledge Bundle Update Log

## 2026-08-01 (поставка ui-liquid-glass)
* **Canon change** — [action registry](/engineering/action-registry.md): `note`-хук
  объявлен текстом для человека, а не логом. Он виден в ленте чата, поэтому пишется
  человеческим английским без `run=<id>` и внутренних имён действий. Основание:
  реворк UI обнаружил, что заметки реестра выходили наружу как
  `export_gdocs run=run-a → Google Docs (облако)`.
* **Note (no canon change)**: правила формулировок целиком — doc 17 v0.5 § Словарь
  (`copy.ts` на фронте, `research/phrasing.py` на бэкенде). Инварианты тиров и
  реестра не менялись — поменялся только язык, которым интерфейс о них говорит.
## 2026-07-31 (поставка session-throughput, закрыта частично)
* **Canon change** — [LLM canon](/engineering/llm-canon.md): добавлено правило
  «схема под constrained decoding обязана быть плоской». Основание — замер стадии
  `compare`: схема с `dict[str, int | float | str]` сорвала таймаут 300 s дважды,
  тогда как плоская схема синтеза давала −68 % токенов. Следствие: `compare`
  остаётся каноничным до отдельного замера.
* **Structure**: появился `llm/json_chat.py` — паттерн «вызов модели → парсинг JSON
  → один повтор» жил копией в `synthesizer` и `compare_synthesizer`; DRY-гейт поймал
  это, когда добавление схемы сделало блоки идентичными. Инварианты не менялись.
* **Note (no canon change)**: `ComparisonResult.llm_stats` — телеметрия стадии
  `compare`, которая раньше выбрасывалась в runner'е. Это измерение, не политика.

## 2026-07-31 (поставка synth-speed)
* **Canon change** — [LLM canon](/engineering/llm-canon.md): синтез разделён по
  интентам. На извлекающих — `think: false` + `format: schema` + бюджет текста
  (−68 % выходных токенов при идентичном ответе, 4 прогона из 4 совпали до
  токена); на `content_search`/`design_audit` остаётся канон, потому что быстрый
  путь там бимодален (350 ↔ 1265 токенов при одной конфигурации). Запрет
  `format`×thinking уточнён: он снимается при выключенном рассуждении.
  Полные числа — doc 16 v0.7 § Быстрый синтез, doc 20 v0.3.
* **Note (важно для будущих замеров)**: два правила измерения, купленные этой
  поставкой. (1) Резать надо **выход**: 87–97 % времени синтеза — генерация, вход
  стоит 3–7 s из 37–174 s. (2) **Число фактов не годится как критерий качества** —
  при одинаковом счётчике извлечение съехало с `product_name: WX-9` на
  `order_form_filled: Да`; сверять надо ключи и значения.
* **Not measured, not touched**: финальный `compare` в сессии (вход 24K при N>3)
  остаётся каноничным до отдельного замера — записано, чтобы отсутствие правки не
  выглядело недосмотром.

## 2026-07-31 (поставка nav-model-split)
* **Canon change** — [LLM canon](/engineering/llm-canon.md): навигация разделена на
  два класса решений. Лёгкая `qwen3:8b` берёт решения, замкнутые на текущей
  странице; выбор ссылки по смыслу и синтез остаются на `qwen3:14b`; на
  hard-violation replan эскалируется на тяжёлую. Основание — замер на одном коде
  (8b вдвое быстрее на DOM-решениях, 3 прогона из 3 хуже на выборе статьи).
  Полные условия и числа — doc 16 v0.6 § Маршрутизация nav-решений, doc 14 v0.6.
* **Note**: инварианты тиров действий это не затронуло — маршрут выбирает, **кто
  решает**, а не что разрешено; политика подтверждений осталась как в
  [action tiers](/engineering/action-tiers.md).

## 2026-07-30 (поставка tier3-exit-smoke)
* **Canon change** — живой exit-прогон Tier 3 изменил инварианты, а не только
  код, поэтому waiver'а здесь нет: концепты обновлены по существу.
  [action tiers](/engineering/action-tiers.md): добавлены `fill_form` (форма за
  одно решение; каждое поле по I-H11, password отклоняет пачку целиком),
  «после handoff — только фиксация исхода» (один необратимый шаг за прогон),
  «закрытый человеком браузер = штатный конец», «значения полей в снапшоте
  никогда не включают password» и порядок ветвей в `interaction.py`
  (handoff **до** submit-confirm) с режимо-зависимой разметкой submit.
  `verified:` перевыставлен на 2026-07-30 — тир подтверждён человеком вживую.
* **Canon change** — [LLM canon](/engineering/llm-canon.md): прогрев модели до
  открытия браузера (`OllamaClient.warmup`, 8.7 → 3.6 s на первом шаге), правило
  «одно решение на форму», и запись о том, что формулировка правила промпта
  меняет поведение не меньше флагов («кнопку нажмёт человек» читалось как
  «действие не требуется»).
* **Note**: модель навигации в каноне остаётся `qwen3:14b` — замер `qwen3:8b`
  как лёгкой nav-модели ещё не сделан (следующая поставка); канон правится по
  результату замера, а не по ожиданию.

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
