# 17 — UI Screens (CLI + Future Web)

> Local Web Agent · Design doc · **v0.7** · 2026-08-03

## MVP: CLI (Phase 1–3) → Chat UI (Phase 4, primary UX)

Web UI **не в Layer 1 MVP**. **Research Chat** — целевой интерфейс продукта с Phase 4 ([doc 24](24-research-chat-agent.md)). До этого: `agent crawl` и `agent research`.

---

## CLI flows

### Flow 1: Start crawl (blocking)

```
$ agent crawl --url https://acme.com --task "Find sales email"

Local Web Agent v0.1
Task: Find sales email
Start: https://acme.com
Limits: 10 pages, depth 2

[1/10] https://acme.com          → navigate → /contact
[2/10] https://acme.com/contact  → extract_now
[3/10] synthesizing...

Status: completed (3 pages, 42s)

Summary: Sales contact is sales@acme.com

Findings:
  • sales_email (high): sales@acme.com
    Evidence: "Email us at sales@acme.com" — /contact

Saved: data/runs/abc123/result.json
```

### Flow 2: Design audit (vision + multi-viewport)

```
$ agent crawl --url https://acme.com \
  --task "Audit design: colors, layout, mobile vs desktop" \
  --report report.md

[1/10] https://acme.com              → navigate → /pricing
[2/10] https://acme.com/pricing      → extract_now
[3/10] vision batch (4 calls: 2 pages × desktop+mobile+tablet on home)...
[4/10] synthesizing...

Status: completed (2 pages, 78s, vision 4/4 ok)

Summary: Blue primary (#2563eb); card grid desktop; hamburger mobile.

Design:
  • primary_colors: #2563eb, #ffffff
  • layout: three-column pricing cards, sticky header

Report: data/runs/def456/report.md  (open folder for images)
```

### Flow 3: Background crawl + poll

```
$ agent crawl --url ... --task "..." --no-wait
Run started: abc123
Poll: agent runs show abc123

$ agent runs show abc123 --watch   # Phase 2: refresh every 2s
```

### Flow 4: History

```
$ agent runs list

 ID       STATUS      PAGES  TASK                          STARTED
 abc123   completed   3      Find sales email              2h ago
 def456   blocked     1      Get pricing                   1d ago

$ agent runs show abc123 --steps
$ agent runs show abc123 --vision     # Phase 2: vision_insights summary per step
```

---

## CLI components (Rich)

| Component | Use |
|-----------|-----|
| `Progress` | Page counter [N/max] |
| `Spinner` | LLM planning / synthesis |
| `Table` | runs list |
| `Panel` | Summary + findings + design block |
| `Syntax` | JSON output optional |
| `Markdown` | `--report` file preview path in done message |

---

### Flow 5: Research Chat (Phase 4 — primary)

```
┌─────────────────────────────────────────────┐
│ You: a.com b.com c.com d.com                │
│      Compare design of each                 │
├─────────────────────────────────────────────┤
│ Agent: Design audit site 1/4 (a.com)…       │
│        ████████░░░░                           │
│ Agent: [table of differences]                 │
│        Open comparison_report.md              │
├─────────────────────────────────────────────┤
│ [ URLs or message…                  ] [Send] │
└─────────────────────────────────────────────┘
```

Side panel: linked runs, screenshot thumbs, per-site reports.

---

## Phase 4: Research Chat UI — реализовано (2026-07-19)

**Стек (факт):** React 19 + Vite 7 + TypeScript + Tailwind CSS v4 (`frontend/`). Prod: `npm run build` → `frontend/dist`, FastAPI монтирует на `/` (same-origin, CORS не нужен). Dev: `npm run dev` (5173) c proxy `/sessions|/runs|/health` → 8001.

### Layout (три стеклянных слоя над градиентным полотном)

```
┌─ Sidebar ─────┬─ Chat ────────────────────────┬─ Inspector ───────────┐
│ + New chat    │ header: title·state·Stop      │ tabs: Sites visited │ │
│ chat list     │ messages (user/agent/quiet)   │       What we found   │
│  (state,      │ progress card (SSE)           │ site cards:           │
│   N sites,    │ pause card (needs you)        │  state·goal·pages     │
│   relative    │ composer (Enter=send)         │  «How it got there»   │
│   time, ✕)    │ welcome: три примера задач    │  screenshots          │
│               │                               │ verdict: best·scores· │
│               │                               │  side by side·in short│
└───────────────┴───────────────────────────────┴───────────────────────┘
```

### Визуальный язык: liquid glass (v0.5)

- **Слои, а не рамки.** Контент живёт на полупрозрачных поверхностях с размытием
  (`backdrop-filter: blur + saturate`), тонкой светлой кромкой изнутри и мягкой
  тенью. Глубина = размытие + свет.
- **Полотно должно быть насыщенным.** Первый прогон был бледным (oklch 93–97 %) —
  стекло выглядело белой плашкой: слою нечего размывать. Итог: четыре цветных
  пятна + диагональный градиент, в тёмной теме те же координаты, темнее и глубже.
- **На светлой теме нужна внешняя тёмная линия** (`0 0 0 0.5px`) — иначе панель
  сливается с фоном. Проверено скриншотами, не на глаз в коде.
- **Рецепт стекла — утилиты в `index.css`** (`glass`, `glass-panel`, `glass-quiet`,
  `glass-hover`, `btn-accent`, `accent-surface`, `focus-ring`, `scroll-slim`), а не
  восемь классов на каждый блок: иначе поверхности разъезжаются.
- **Один акцент** (индиго-фиолет) + мята «готово» + янтарь «нужен человек» + роза
  «сломалось». Тон берётся из смысла статуса, а не из его названия.
- **Кликабельная поверхность держит кромку всегда** (`glass-slot`, прозрачная в
  покое): появление `border` только по наведению меняет размер бокса, и элемент
  дёргается под курсором. Проверяется измерением геометрии до/после `hover`, а не
  на глаз — сдвиг на 1px на скриншоте не виден, а в работе заметен.
- **Тёмная тема полноценная** (`prefers-color-scheme`), движение уважает
  `prefers-reduced-motion`, фон не анимирован (дёргающийся фон мешает читать).

### Словарь: интерфейс не говорит на языке кода (v0.5)

Требование владельца: только English и никакой внутренней лексики.

| Было (лексика кода) | Стало (язык пользователя) |
|---|---|
| `running_tools` · `comparing` · `not_found` | Visiting sites · Comparing sites · Nothing found |
| `Runs (3)` · `intent` | Sites visited · 3 · «Looking for an article» |
| `extract_now` · `OBSERVE` · `SYNTHESIZE` | Pulled the answer from this page · Read the page · Wrote up the findings |
| `Dimensions · content_completeness` | Side by side · «Compared on how complete the content is» |
| `winner` · `rankings` · `narrative` | Best of the bunch · How they scored · In short |
| `3/10 pages` · `loading <id>…` | 3 of 10 pages read · Loading what the agent saw… |
| `HTTP 409 run_in_progress` | «Another research run is still going. Wait for it, or stop it first.» |

- **Фронт:** `copy.ts` — единственное место перевода. Неизвестное значение падает
  в `humanizeKey` (snake_case → фраза), а не выходит наружу ключом.
- **Бэкенд:** `reporting/phrasing.py` — текст, который сочиняет сервер (заметки о
  шагах, ответы в чат, причины исключения сайта). Парсить строки на клиенте было
  бы хаком: текст правится там, где написан.

### Язык ответа — язык запроса (v0.7)

**Правило:** русский вопрос получает русский ответ, английский — английский. Язык
определяется по самому запросу (наличие кириллицы), без обращения к модели: решение
должно быть дешёвым и одинаковым при каждом прогоне.

**Что именно следует языку запроса:** проза модели (`summary`, `narrative`, причины,
`not_found`) **и наши строки внутри ответа** — «Оценки:», «Не вошли:», «Читаю …»,
приписка про непрочитанное. Второе не менее важно первого: исходным дефектом была не
русская проза, а **смесь** — английская строка «How they scored:» стояла над русским
абзацем.

**Что остаётся английским всегда:** подписи интерфейса — кнопки, табы, заголовки
карточек, статусы, «How it got there». Это мебель, а не ответ; словарь § Словарь
продолжает действовать без изменений.

**Исключение обязательное — цитаты.** Цитата остаётся дословной на языке страницы: она
доказательство и сверяется S-H3 против DOM (doc 13). Перевод сорвал бы сверку и
превратил бы факт в пересказ.

**Фразы живут в данных** — `data/phrasing/chat_phrases.yaml`, а не в коде (doc 18 § DRY);
модуль-читатель — `app/reporting/phrasing.py` (слой ниже `orchestrator` и `research`,
иначе import-linter справедливо ловит `orchestrator → research`):
иначе добавление языка означает правку кода. Тест держит наборы ключей симметричными —
пропущенный ключ в одном языке дал бы тихую английскую строку в русском ответе.

**История правила** (чтобы не «починить» его обратно): сначала проза шла на языке
задачи, а каркас был английским всегда → владелец увидел смесь и потребовал
единообразия → сделали всё английским → владелец уточнил: пусть будет язык запроса.
Итог — язык запроса ведёт и прозу, и каркас.

### Служебный текст не показывается человеку (v0.6)

В чат уезжал стек Playwright: `couldn't be read (Page.evaluate: TypeError: Cannot read
properties of null (reading 'innerText') at eval (…) at UtilityScript.evaluate (…))` —
три строки внутренностей там, где нужна одна фраза. Причина: `exclusion_reason`
приклеивал `error_message` целиком.

Правило: техническая причина переводится в человеческую (`the page never finished
loading`, `the site did not respond in time`), а **нераспознанное отбрасывается
целиком**. Лучше «couldn't be read» без деталей, чем внутренности в интерфейсе:
пользователю нужно знать, что сайт не прочитался, а не где упал наш JS.

### Раскрытие и движение (v0.6)

- **Обрезанный текст должен раскрываться.** Итог по сайту был `line-clamp-3`
  насовсем — прочитать его целиком было нельзя. Теперь одно действие на карточке
  разворачивает и полный текст, и шаги; у свёрнутого текста нижняя кромка
  растворяется (`clamp-soft`), чтобы обрыв читался как «есть продолжение».
- **Высота анимируется, а не скачет:** `reveal` (`grid-template-rows: 0fr → 1fr`) не
  требует знать высоту заранее, поэтому работает и для списка шагов, и для текста
  любой длины.
- **Промежутки задаёт список, а не элементы.** Карточки чатов стояли вплотную и
  читались как одна: `gap` у контейнера вместо отступов у каждой карточки — иначе он
  удваивается или исчезает при вставке блока подтверждения удаления.
- **Иконки — фигуры, а не глифы.** Плюс «+» набором выглядел съехавшим: у глифа своя
  метрика, оптический центр не совпадает с центром круга. Нарисован `svg`.
- **Контраст статуса — своими чернилами.** Акцент (58 % светлоты) хорош на плотной
  кнопке, но на полупрозрачной пилюле поверх насыщенного полотна сливался с фоном
  («Visiting sites» читался с трудом). Введены `--status-*-ink`: на светлой теме
  темнее акцента, на тёмной светлее. Контраст даёт цвет, а не размер шрифта.
- **Числа в таблице сравнения выровнены по центру** под своими заголовками и набраны
  `tabular-nums`: по левому краю колонка оценок не сравнивалась глазом.
- **Подсказка ввода не рвётся на узком окне.** Длинный placeholder обрезался на
  середине слова; CSS его не измеряет, поэтому подсказка про Enter/Shift+Enter
  вынесена под поле отдельным элементом — перенос теперь проходит между подсказками,
  а не внутри фразы.
- `prefers-reduced-motion` уважается, но **поведение остаётся**: раскрытие работает
  без анимации, иначе часть содержимого стала бы недостижимой.
- Тесты держат формулировки дословно (`test_research_runner`, `test_file_sink`,
  `test_actions_registry`): смена слов должна быть осознанной.

### Компоненты (`frontend/src/`)

| Файл | Ответственность |
|------|-----------------|
| `App.tsx` | только композиция экрана (три слоя) |
| `useSession.ts` | состояние чата + действия пользователя (`makeActions`) |
| `useSessionStream.ts` | SSE-подписка: единственное место с ресурсом времени жизни |
| `copy.ts` | человеческие формулировки: статусы, шаги, интенты, ошибки, счётчики |
| `api.ts` | REST-клиент + `subscribeSessionEvents` (дедуп реплея по `message.index`) |
| `types.ts` | зеркала Pydantic-схем |
| `components/Sidebar.tsx` | список чатов; удаление — подтверждением в интерфейсе |
| `components/Chat.tsx` | лента, прогресс, пауза, ошибка, composer |
| `components/Message.tsx` | пузыри user/agent; шаги агента — тихой строкой |
| `components/Inspector.tsx` | табы Sites visited / What we found |
| `components/RunCard.tsx` | состояние, цель, «How it got there», скриншоты |
| `components/ComparisonView.tsx` | best · scores · side by side · in short · left out |
| `components/StatusPill.tsx` | статус тоном по смыслу, точка «живёт» только когда идёт работа |
| `components/ProgressCard.tsx`, `ChallengeCard.tsx`, `Composer.tsx`, `WelcomeScreen.tsx` | прогресс, пауза, ввод, пустой экран |

### Доступность (v0.5)

- Строки чатов — настоящие `button` с `focus-visible`-кольцом (были кликабельные
  `div`, недостижимые с клавиатуры).
- Удаление — подтверждение внутри интерфейса вместо системного `confirm()`.
- У иконок-кнопок `aria-label`; у раскрывающихся карточек `aria-expanded`; у табов
  `aria-pressed`; у поля ввода — `aria-label`.
- Автотестов UI нет — это названо честно в поставке; проверка визуала —
  скриншотами light/dark на живом API.

### Поведение

- SSE `GET /sessions/{id}/events` (протокол — doc 15 v0.6); источник правды — `GET /sessions/{id}`: на `done` и tool-notes UI рефетчит сессию/runs.
- Cancel session (FR-3.8) из header; ошибки API (409 busy/run_in_progress) — красный баннер.
- **No WebSocket** — SSE poll pattern (exit doc 06). EventSource сам реконнектит; реплей дедупится.

### Out of scope for Web UI

- Real-time browser view (too heavy)
- Editing prompts / settings in UI (edit files in `data/prompts/`, env `LWA_*`)
- Отдельный «New Crawl» экран для Layer 1 — single-site задача решается тем же чатом (один URL → `single_site` intent)

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | CLI flows MVP; Web UI draft Phase 3 |
| 2026-07-05 | **v0.2:** design audit flow; --vision progress; report/design CLI; Web UI vision badges |
| 2026-07-05 | **v0.3:** Flow 5 Research Chat primary UX; Phase 4 (doc 24) |
| 2026-07-05 | **v0.3.1 (review):** Cancel run в Run detail (FR-3.8) |
| 2026-08-01 | **v0.5 (liquid glass + человеческий язык):** визуальный язык переписан на стеклянные слои над насыщенным полотном (§ Визуальный язык) — бледный фон первой версии не давал стеклу читаться, на светлой теме добавлена внешняя линия кромки; введён словарь формулировок (§ Словарь): `copy.ts` на фронте и `research/phrasing.py` на бэкенде, интерфейс больше не говорит `running_tools`/`extract_now`/`Dimensions`/`rubric`; язык только English (русские строки убраны из паузы, тумблера, примеров, а также из ответов бэкенда и заметок реестра действий); `App.tsx` → `useSession` + `useSessionStream` + `makeActions`; доступность: строки чатов стали кнопками с фокус-кольцом, системный `confirm()` заменён подтверждением в интерфейсе, добавлены `aria-*`; `SidePanel` → `Inspector`, `StatusBadge` → `StatusPill` |
| 2026-07-19 | **v0.4 (Phase 4 impl):** Chat UI реализован — React 19 + Vite 7 + TS + Tailwind v4 в `frontend/`; трёхколоночный layout (sidebar / chat+SSE progress / side panel Runs+Comparison со скриншотами и экспортом report.md); prod = статика из FastAPI, dev = Vite proxy; черновые экраны New Crawl/Settings заменены фактической структурой (single-site — через тот же чат) |
| 2026-08-03 | **v0.6 (язык вывода + правки интерфейса по списку владельца):** § Язык вывода — **английский всегда**, даже когда задача и сайты русские; отменено прежнее правило промптов «in the language of the TASK» (оно давало смесь языков в одном сообщении). Единственное исключение — **цитаты**: они доказательство и сверяются с DOM (S-H3), перевод сорвал бы сверку. § Служебный текст — стек Playwright больше не уезжает в чат: техническая причина переводится в человеческую, нераспознанное отбрасывается целиком. § Раскрытие и движение — обрезанный итог по сайту раскрывается (`clamp-soft` + `reveal` через `grid-template-rows`), промежутки карточек задаёт `gap` контейнера, плюс нарисован фигурой (глиф выглядел съехавшим), у статусов свои чернила `--status-*-ink` (акцент сливался с полотном), числа в таблице сравнения по центру и `tabular-nums`, подсказка ввода не рвётся на узком окне; `prefers-reduced-motion` убирает анимацию, но не поведение |
| 2026-08-03 | **v0.7 (язык ответа = язык запроса):** правило v0.6 «английский всегда» уточнено владельцем: русский вопрос получает русский ответ. Языку запроса следует **и проза модели, и наши строки внутри ответа** (каркас «Оценки:», заметки «Читаю …», приписка про непрочитанное) — исходным дефектом была именно смесь, а не русский текст. Подписи интерфейса остаются английскими всегда (мебель, не ответ). Цитаты — дословно на языке страницы (S-H3). Фразы вынесены в `data/phrasing/chat_phrases.yaml`; тест держит наборы ключей симметричными |
