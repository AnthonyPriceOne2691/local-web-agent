# 16 — Prompts Library

> Local Web Agent · Design doc · **v0.8** · 2026-08-03  
> **Канон LLM parameters** — этот документ. Doc 07 зеркалит.

**Не храним тексты промптов в design docs.** Только: какие файлы, за что отвечают, variables, ссылка на output schema. Рабочие тексты — в `data/prompts/` при реализации (итерация через Phase 0/1 spike).

## File layout

```
data/prompts/
├── navigator_system.txt       # Qwen — PLAN step
├── navigator_user.j2          # Jinja2: task, snapshot, links, budget
├── synthesizer_system.txt     # R1 — per-site extraction
├── synthesizer_user.j2        # Jinja2: task, snapshots + vision_insights
├── vision_system.txt          # qwen2.5vl — screenshot analyze
├── vision_user.j2             # Jinja2: task, url, profile, dom_excerpt
├── compare_system.txt         # R1 — N-site comparison (doc 24)
├── compare_user.j2            # Jinja2: task, rubric, site_summaries[]
├── meta_system.txt            # Qwen — research tool planning (doc 24)
└── meta_user.j2               # Jinja2: message, urls[], session context

data/prompts/rubrics/
├── design_diff.txt            # UC-1 compare dimensions (bullets, not prose prompt)
├── content_completeness.txt   # UC-2 compare dimensions
└── generic_merge.txt
```

Reload: on each run start (no restart required in dev).

---

## LLM parameters (canonical)

> **Structured outputs (review):** Ollama принимает в `format` не только `"json"`, но и **полную JSON Schema** — sampling ограничивается схемой, невалидный JSON почти исчезает. Для nav/meta/vision передаём Pydantic-схему (`Model.model_json_schema()`). Это снимает бо́льшую часть retry-веток I-H7.
>
> **R1 + format=json несовместимы со strip_thinking:** constrained decoding заставляет JSON с первого токена и **подавляет thinking-фазу** — теряется смысл reasoning-модели. Для R1: `format` не задаём, `think: true` (Ollama ≥ 0.9 отдаёт рассуждения отдельным полем `message.thinking`), JSON парсим из `content`; `strip_thinking()` — fallback для утечек `<think>`.

```yaml
navigation:    # PLAN step → qwen3:14b (D-2 closed 2026-07-18; fallback qwen2.5:14b-instruct)
  model: qwen3:14b
  light_model: qwen3:8b             # только DOM-локальные решения (§ Маршрутизация nav-решений)
  think: false                      # qwen3 в Ollama думает по умолчанию — для nav выключать
  num_ctx: 8192
  temperature: 0.4                  # drift auto-tighten → 0.2 (doc 13)
  max_tokens: 400
  stream: false
  format: schema:AgentAction        # JSON Schema constrained (doc 04)

synthesis:     # SYNTHESIZE → qwen3:14b single-model (D-3 closed; fallback deepseek-r1:14b)
  model: qwen3:14b
  num_ctx: 16384
  temperature: 0.2
  max_tokens: 4096
  stream: false
  # Два режима по интенту — § Быстрый синтез (замер 2026-07-31):
  reasoning_intents: [content_search, design_audit]   # канон ниже; `*` = только канон
  # канон (длинный ответ по природе):
  format: none                      # НЕ json: не душить thinking
  think: true                       # Ollama ≥0.9; thinking → message.thinking
  strip_thinking: fallback          # только при утечке <think> в content
  # быстрый путь (извлечение):
  fast_think: false
  fast_format: schema:SynthesisOutput   # запрет format×thinking снят: мыслей нет
  fast_summary_cap: 500                 # + правило «извлекай названные значения»

vision:        # VISION batch → qwen2.5vl:7b (doc 23)
  model: qwen2.5vl:7b
  num_ctx: 8192
  temperature: 0.2
  max_tokens: 1200
  stream: false
  format: schema:VisionInsight
  fallback_model: gemma3:12b        # llava:7b — legacy (2023), не default

meta:          # Research meta-agent → qwen2.5:14b-instruct (doc 24)
  model: qwen2.5:14b-instruct
  num_ctx: 8192
  temperature: 0.3
  max_tokens: 800
  stream: false
  format: schema:ToolCallPlan

compare:       # COMPARE → deepseek-r1:14b (doc 24)
  model: deepseek-r1:14b
  num_ctx: 16384                    # 24576 при N>3 сайтов (doc 20); только R1 в RAM — допустимо
  temperature: 0.0                  # замер 2026-08-03: 0.2 давала разброс до 8 пунктов
  max_tokens: 4096
  stream: false
  format: none
  think: true
  strip_thinking: fallback
```

Все pass'ы: `keep_alive: 0` на последнем запросе перед model swap (doc 14 § Swap mechanics).

---

## Быстрый синтез (schema-constrained, без рассуждения)

Замер 2026-07-31 разложил время синтеза: **87–97 % — генерация** (`eval_duration`),
вход 511–1316 токенов стоит 3–7 s. Значит резать надо выход, а не вход; при
`think: true` мысли занимают **48–73 %** выхода и до пользователя не доходят.

Два режима по интенту, оба измерены:

| Интент | Режим | Замер |
|---|---|---|
| извлечение (`contact`, `pricing`, `generic`, …) | `think: false` + `format: schema:SynthesisOutput` + бюджет `summary` | `contact`: **138 токенов против 427 (−68 %)** при том же факте и значении, 4 прогона из 4 идентичны до токена; action-кейс: 679 против 788 и **качество выше канона** — вернулись `product_name`/`product_price`/`delivery_time` |
| `content_search`, `design_audit` | **канон**: `think: true`, без `format` | попытка ускорить дала **бимодальный** выход: 350 ↔ 1265 токенов при одной конфигурации (то есть −65 % или +25 % — как повезёт). Блок `article` при этом всегда корректен, страдает не качество, а предсказуемость |

- **Запрет `format` × thinking остаётся в силе** (см. врезку выше) — но он перестаёт
  действовать, когда рассуждение выключено. Именно поэтому схема доступна только в
  быстром пути; включить её вместе с `think: true` нельзя.
- **Схема описывает только то, что пишет модель** (`SynthesisOutput`: summary /
  facts / not_found + опциональные article-блоки). Отдавать `ExtractionResult`
  целиком нельзя: там есть поля кода (`run_id`, `task`, `duration_seconds`) — схема
  попросила бы модель их выдумать.
- **Бюджет несёт правило «извлекай названные значения»**, и оно обязательно: схема
  без него дала эхо ввода (`order_form_filled: Да`) вместо содержимого страницы.
  Это же наблюдение — предупреждение о метриках: **число фактов не годится как
  критерий качества**, оно было одинаковым при явной деградации.
- Ручка `reasoning_intents: "*"` выключает быстрый путь целиком (аварийная).
- **Не измерено и потому не тронуто:** финальный `compare` в сессии (вход 24K при
  N>3, ответ по природе длинный) — остаётся каноничным до отдельного замера.

### Воспроизводимость `compare` (замер 2026-08-03)

Живой прогон показал, что оценки сайтов плавают между сессиями (Hugo 90 → 70,
Eleventy 60 → 85). Замер развёл две возможные причины: три уже прочитанных сайта
взяты из БД, обход исключён, `compare` прогнан дважды на **идентичном** входе.

| temperature | Прогон 1 | Прогон 2 |
|---|---|---|
| 0.2 (было) | 90 / 80 / 60 | 82 / 78 / 65 |
| **0.0 (стало)** | **82 / 80 / 70** | **82 / 80 / 70** — побитово, те же 1338 токенов |

Порядок сайтов совпал во всех четырёх прогонах; плавали именно **числа**. Сравнение
конкурентов — не творческая задача: одинаковый вход обязан давать одинаковый ответ,
иначе оценку нельзя показывать человеку как оценку. Ручка — `LWA_COMPARE_TEMPERATURE`.

**Чего температура НЕ лечит:** при близких кандидатах победитель определяется
формулировкой задачи. В сессии с «(getting started)» в тексте победил `docs.astro.build`
(95 против 85), в замере без этих слов — `www.11ty.dev` (82 против 80). Детерминизм
даёт воспроизводимость, а не единственно верный ответ; разрыв в 2 пункта нельзя
читать как «этот сайт лучше».

---

## Маршрутизация nav-решений (лёгкая × тяжёлая модель)

Одна модель на все решения навигатора — неверная экономия: класс решений разный.
Замер 2026-07-31 (`qwen3:8b` vs `qwen3:14b` **на одном коде**, два инстанса API,
фикстуры 8901/8904/8908; nav = сумма `total_duration` решений навигатора):

| Класс решения | `qwen3:8b` | `qwen3:14b` |
|---|---|---|
| локально по DOM (что заполнить, что нажать) | nav **9.4 s**, решения те же, 0 violations | nav 16.8 s |
| одна очевидная ссылка (contact page) | nav **10.1 s**, путь и ответ те же | nav 22.1 s |
| выбор статьи по смыслу | **3 прогона из 3**: 3× `G-H2` (уход за `max_depth`) + лишний хоп в 404-дубль, спасён fallback'ом | **0 violations в 2 из 2**, путь `статья → extract_now` |

Отсюда правило: **лёгкая модель отвечает только за решения, замкнутые на текущей
странице.** Скорость без качества навигации не считается — навигация по смыслу
это ядро продукта, а не оптимизируемая деталь.

| Условие | Модель |
|---|---|
| `light_model` пусто | тяжёлая (поведение до поставки `nav-model-split`) |
| replan после hard-violation | тяжёлая — **эскалация**: replan и есть сигнал, что лёгкая ошиблась |
| на странице нет живых интерактивных элементов | тяжёлая (решать локально нечего → это выбор ссылки) |
| предыдущее DOM-действие было на этом же URL | лёгкая (мы посреди интеракции) |
| задача просит действия (`action_keywords`) + элементы есть | лёгкая |
| иначе | тяжёлая |

- Словарь `action_keywords` (RU+EN) — **данные**: `data/navigation/nav_model_routing.yaml`.
  Ошибаться безопасно в сторону тяжёлой: она медленнее, но не уводит агента с пути.
- Реализация: `llm/model_router.py` (`pick_nav_model` — чистая функция, без сети и
  файлов), вызов — из `orchestrator/decide.py`; модель шага пишется в
  `llm_stats.model`, иначе маршрут нечем подтвердить.
- `navigate` в истории **сбрасывает** признак интеракции: ушли со страницы —
  следующее решение снова смысловое.
- Прогревается модель **первого** шага (`first_step_model`): на первом шаге истории
  ещё нет, решает формулировка задачи.
- Перед синтезом выгружаются **обе** nav-модели: иначе лёгкая держит свои ~5 GB,
  пока синтез работает на 16K ctx (дисциплина RAM, doc 14).

---

## Prompt responsibilities (outline only)

| File | Model | Purpose | Output schema |
|------|-------|---------|---------------|
| `navigator_*` | Qwen | Pick next action among top-K links | `AgentAction` (doc 04) |
| `synthesizer_*` | R1 | Per-site facts + evidence from snapshots | `ExtractionResult` (doc 05) |
| `vision_*` | qwen2.5vl | Describe screenshot; task-relevant visible facts | `VisionInsight` (doc 23) |
| `meta_*` | Qwen | Plan tool calls for research session | tool call JSON (doc 24) |
| `compare_*` | R1 | Rank/compare N site results | `ComparisonResult` (doc 05) |
| `rubrics/*` | — | Dimension checklist injected into compare prompt | referenced by rubric id |

### Shared rules (all JSON prompts)

- Output valid JSON only; schema in linked doc
- No invented URLs, prices, emails without evidence
- Log prompt file hash/version in run/session config for reproducibility
- **Язык ответа = язык task/сообщения пользователя** (summary, narrative, chat reply); ключи JSON — всегда en snake_case

---

## Template variables

### navigator_user.j2

| Variable | Content |
|----------|---------|
| `task` | User task string |
| `current_url` | |
| `snapshot` | Truncated PageSnapshot |
| `visited` | List `{url, title}` max 10 |
| `links` | **Top-10 scored candidates** из CandidateQueue (doc 21) — не сырые links; было «15», выровнено с docs 04/21 |
| `pages_left` | int |
| `depth_left` | int |

### synthesizer_user.j2

| Variable | Content |
|----------|---------|
| `task` | |
| `snapshots` | PageSnapshot incl. `vision_insights` (doc 20 truncate) |
| `step_trace` | URLs visited in order |

### vision_user.j2

| Variable | Content |
|----------|---------|
| `task` | User task |
| `url` | Page URL |
| `profile` | desktop \| tablet \| mobile |
| `dom_excerpt` | First ~1500 chars of main_text |

Image: Ollama `images[]`, not in Jinja template.

### meta_user.j2

| Variable | Content |
|----------|---------|
| `message` | Latest user message |
| `urls` | Parsed URL list |
| `session_history` | Truncated prior turns |
| `tools` | Tool registry descriptions |

### compare_user.j2

| Variable | Content |
|----------|---------|
| `comparison_task` | User compare question |
| `rubric` | Rubric id + dimension bullets from `rubrics/` |
| `site_summaries` | Truncated ExtractionResult per run |

---

## Prompt versioning

- Version in file header when implementing (`data/prompts/`, not design doc)
- Store `prompt_versions` in `crawl_runs.config_json` / `research_sessions.config_json`

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial prompts library |
| 2026-07-05 | vision/synthesizer params; file layout |
| 2026-07-05 | compare_*, meta_*, rubrics/ (doc 24) |
| 2026-07-05 | **v0.3:** removed prompt body text from design; outlines + variables only |
| 2026-07-05 | **v0.4 (review):** structured outputs (JSON Schema в `format`) для nav/meta/vision; конфликт `format:json`×`strip_thinking` у R1 устранён → `think:true` + отдельное поле thinking; vision fallback → gemma3:12b; compare num_ctx 24576 при N>3; правило языка ответа |
| 2026-07-05 | **v0.4.1 (review-2):** navigator links = top-10 candidates (было 15 — рассинхрон с docs 04/21) |
| 2026-07-31 | **v0.7 (замер синтеза):** новая секция **§ Быстрый синтез** — на извлекающих интентах синтез идёт `think: false` + `format: schema:SynthesisOutput` + бюджет `summary` (−68 % токенов при идентичном ответе; на action-кейсе качество выше канона), на `content_search`/`design_audit` остаётся канон (быстрый путь там бимодален: 350 ↔ 1265 токенов). Запрет `format`×thinking уточнён: он снимается при выключенном рассуждении. Добавлено предупреждение «число фактов не критерий качества» (одинаковое количество скрывало деградацию). `compare` не измерен и не тронут |
| 2026-07-31 | **v0.6 (замер лёгкой nav-модели):** новая секция **§ Маршрутизация nav-решений** — `light_model: qwen3:8b` берёт только решения, замкнутые на текущей странице (заполнить/нажать), выбор ссылки по смыслу и синтез остаются на `qwen3:14b`; таблица условий + эскалация на тяжёлую после hard-violation; словарь `action_keywords` → `data/navigation/nav_model_routing.yaml`; в `llm_stats` добавлена `model`. Основание: 8b вдвое быстрее на DOM-решениях и в 3 прогонах из 3 хуже на выборе статьи (`G-H2` + хоп в 404) |
| 2026-07-18 | **v0.5 (Phase 2 exit-бенчмарк):** synthesizer_system — vision-aware: evidence получил поле `source: dom\|vision`, правило «факт только из VISION-блока → source: vision»; добавлены prod-промпты `vision_system.txt` + `vision_user.j2` (doc 23); **канон nav/synth → `qwen3:14b` single-model** (D-2/D-3 closed по бенчмарку doc 06 v0.6; пара qwen2.5+r1 — fallback) |
| 2026-08-03 | **v0.8:** `compare` детерминирован (`temperature: 0.0`) по замеру на идентичных входах: 0.2 давала разброс до 8 пунктов, 0.0 — побитовое совпадение. Порядок был стабилен всегда; плавали числа |
