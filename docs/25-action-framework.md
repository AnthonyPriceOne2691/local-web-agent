# 25 — Action Framework (агент действует на сайте)

> Local Web Agent · Design doc · **v1.2** · 2026-08-03

## Назначение

Расширить агента с **read-only research** до **action-capable**: агент не только читает
и анализирует, но и **выполняет действия** — доставляет результат наружу (Google Docs,
файл) и **взаимодействует с самим сайтом** (клик, раскрытие, ввод, submit).

Это **сознательная эволюция спины проекта** (Phase 6). Уточнение по тирам: **Tier 1
(click по не-submit элементу) НЕ инвертирует FR-4.2** — он делает FR-4.2 **границей
Tier 1/Tier 2** (submit/login по-прежнему hard, но теперь как порог, а не тотальный
запрет всякой интеракции). Полная conditional-формулировка FR-4.2 нужна лишь на **Tier 2**
(submit/login под подтверждением). Правки: doc 01 (FR-7 + FR-4.2 note) / doc 13
(I-H7 +click, I-H10 click-safety) / doc 00 (идентичность) — см. § Requirements impact. Anti-bot bypass как был, так и остаётся **вне scope навсегда**
(doc 24): агент честно действует как авторизованный пользователь, а не притворяется
человеком перед защитой. Challenge проходит человек (attended, doc 24).

---

## Ключевой принцип: автономность × обратимость

Опасность не в автономности, а в её сочетании с **необратимостью**. Две независимые оси:

| | Обратимо | Необратимо |
|---|---|---|
| **Автономно** (агент сам) | ✅ целевая магия | ⛔ запрещено |
| **С подтверждением** (human-in-the-loop) | излишне | ✅ безопасно |

**Правило:** агент действует автономно на всём **обратимом**; пауза-подтверждение
включается **только на необратимом**. Автономность там, где не жалко; человек в цикле
там, где жалко. Это масштабирует «магию» без babysitting каждого клика.

---

## Таксономия действий (тиры)

| Tier | Класс | Трогает сайт? | Обратимо? | Автономия | Примеры |
|------|-------|---------------|-----------|-----------|---------|
| **0** | output / sink | нет (отдаёт наружу) | н/д | автономно + consent на «наружу» | → Google Docs, → файл, → Notion, → буфер |
| **1** | safe interaction | да, без сайд-эффектов | ✅ | **автономно** | клик «показать ещё», раскрыть таб, пагинация, hover-reveal |
| **2** | consequential | да, пишет | ⚠️ частично | **подтверждение (attended)** | submit формы, login |
| **3** | destructive | да, необратимо | ❌ | **человек нажимает сам** (агент готовит) | купить, удалить, запостить, отправить |

**Credentials** (нужны для Tier 2 login) — отдельный sub-дизайн безопасного хранения
(§ Credentials); не в первой итерации.

---

## Action Protocol + Registry ✅ (реализовано 2026-07-20)

Захардкоженные кортежи Layer 2 (`KNOWN_TOOLS` в runner + `PLANNER_TOOLS` в
llm_planner — успели разойтись) заменены **реестром** — пакет
[research/actions/](../backend/app/research/actions/):

```python
@dataclass(frozen=True)
class ActionSpec:
    name: str
    tier: int              # 0..3 → политика подтверждения (A-H2/A-H3)
    reversible: bool
    cloud: bool            # A-H4: результат покидает машину → явный запрос
    structural: bool       # поток (очередь/cooldown/финал) ведёт runner
    enforce: EnforceHook   # пер-action контракт плана (M-H3 и родня)
    execute: ExecuteHook   # reply-block действия; None у structural
    note: NoteHook         # M-S1 tool-нота
```

- **M-H1/A-H1** («только зарегистрированные tools») — **точка расширения**: новое
  действие = модуль в `research/actions/` (`register(ActionSpec(...))`) + описание
  для meta-промпта в `data/prompts/tools/<name>.txt` (промпты в data/, doc 18);
  runner и llm_planner не трогаем.
- Пост-валидация плана: membership + пер-action `enforce` — через реестр; в
  планнере остаются только кросс-плановые правила (M-H2 счётчик crawl'ов,
  «compare один и последним»). Блок «Available tools» meta-промпта собирается
  из реестра (`prompt_block` → `{TOOLS_BLOCK}` в meta_planner_system.txt).
- Runner: `structural` действия (crawl_site, compare_results) ведёт сам (очередь,
  cooldown, терминальная compare-стадия); reply-block действия исполняет через
  `spec.execute`; **tier ≥ 2 без подтверждения не исполняется** (A-H2/A-H3 гейт).
- Зарегистрировано: `crawl_site` (tier 1, structural) · `get_run_result` ·
  `list_session_runs` · `compare_results` (structural) · `export_gdocs`
  (tier 0, cloud) · `export_file` (tier 0, локальный sink — первый плагин).
- Отличие от эскиза v0.1: вместо class-Protocol с `args_schema`/`ActionContract` —
  frozen dataclass с enforce-хуком (контекстные проверки вида «run_id из сессии»
  дают больше, чем схема аргументов; отдельный ActionContract не понадобился).

---

## Политика подтверждения (переиспользует Phase 5)

**Attended-субстрат (doc 24) — готовый механизм «подтверди перед действием»:**

```
Tier 0-1 (обратимо)  → execute() сразу, автономно
Tier 2   (значимо)   → run → waiting_user + metadata.pending_action
                       → SSE action_confirm {action, args, url}
                       → Chat UI карточка «Агент хочет: <action>. Выполнить?»
                       → resume → execute()
Tier 3   (необратимо)→ агент НЕ выполняет; готовит и отдаёт человеку (draft/ссылка)
```

`waiting_user / resume / видимый браузер / ChallengeCard` уже построены и проверены
вживую — карточка подтверждения действия делается по образцу `ChallengeCard`.

---

## Tier 3 — handoff: «агент готовит, человек нажимает» (Phase 7)

**Ключевое отличие от Tier 2:** на Tier 2 человек подтверждает в чате — **жмёт агент**.
На Tier 3 агент не жмёт **никогда**, даже с подтверждением: подтверждение в чате — слишком
дешёвый клик для необратимого действия (купить / удалить / опубликовать / оплатить).
Финальную кнопку человек нажимает **сам, в видимом браузере** — физическое действие
на самой странице, где видно *что именно* произойдёт.

### Механика handoff (переиспользует attended-субстрат Phase 5)

```
nav выбирает click по destructive-элементу (task этого требует)
  ├─ unattended → I-H12 hard reject (нет человека — некому нажать)
  └─ attended   → агент НЕ кликает → gate.handoff_action(описание)
                  → run waiting_user, challenge {kind: "handoff", action: "..."}
                  → SSE challenge_wait → ChallengeCard: «Я подготовил <X>.
                    Нажми кнопку сам в открытом браузере, затем “Готово”»
                  → человек жмёт кнопку НА СТРАНИЦЕ (или решает не жать)
                  → пауза кончается ПО ЛЮБОМУ из двух:
                     · явный resume (кнопка «Готово» / POST /runs/{id}/resume), либо
                     · страница изменилась и изменение держится два опроса подряд
                  → reobserve_in_place (страница уже с результатом)
                  → агент продолжает (extract → synthesize фиксирует исход)
```

**Чем кончается пауза Tier 3 (v1.2).** Человек, нажавший кнопку на странице, уже
сделал своё действие — требовать от него второе подтверждение в интерфейсе значит
просить дважды об одном и том же. Поэтому агент во время паузы **смотрит на подпись
страницы** (URL + отпечаток текста, `page_probe`) и продолжает сам, когда она
изменилась.

Осторожность важнее удобства, поэтому:

- изменение засчитывается только если **держится два опроса подряд** — страница
  дёргается сама (дозагрузка, баннер, редирект), и принять это за действие человека
  значит зафиксировать исход, которого ещё нет;
- **явный resume сильнее** и проверяется первым — человек всегда может сказать
  «я закончил» сам;
- чем кончилась пауза, видно в записи прогона: `handoff_resolved_by` =
  `resume` · `page_change` · `timeout`;
- **Tier 2 (`confirm_submit`) автодетекта не получает**: там человек не действует на
  странице, а отвечает «да/нет» — «страница моргнула» не может значить «разрешил».

«Подготовка» = всё обратимое до финальной кнопки: navigate + Tier 1 click
(раскрытия) + Tier 2 fill (поля формы — автономно, I-H11). Handoff — единственная
новая примитива; пауза/resume/re-observe — те же, что challenge/login/confirm.

### Детект destructive (I-H12)

Сигнал — **словарь стемов/фраз в label элемента** (`data/contracts/crawl.contract.yaml`,
правило `click_destructive_handoff`, params `destructive_signals`; словарь в data/, не в
коде — doc 18): buy / pay / purchase / checkout / place order / delete / remove /
publish / оплат / купи / заказ / удал / опубликов / …

- **Ошибка в безопасную сторону:** false positive (кнопка «PayPal» словила `pay`) — это
  лишняя пауза с человеком, приемлемо; false negative страхуется Tier 2 — *любой* submit
  и так не выполняется без человека (I-H10 → confirm).
- **`send` / «отправить» без контекста заказа — НЕ Tier 3** (решение T-1): отправка
  формы = Tier 2 confirm_submit, иначе каждая контакт-форма превращалась бы в handoff.
  Фразы «place order / submit order / отправить заказ» — в словаре.
- I-H12 проверяется **до** attended-пропуска I-H10 и закрывает его дыру: submit-кнопка
  с destructive-сигналом («Оплатить заказ») больше не может пройти путём
  Tier 2 confirm (где нажал бы агент) — только handoff.

### Requirements / контракты

- **I-H12 (doc 13):** click по destructive-элементу агент не исполняет: unattended →
  reject; attended → handoff (человек жмёт сам). Enforcement — та же санитарная
  логика, что I-H10/I-H11 (enforcer до ACT + развилка в `interaction.act_on_element`).
- **A-H3 enforcement:** Layer 1 — I-H12; Layer 2 — runner-гейт `tier ≥ 2` (реестр, v0.9)
  уже не исполняет tier-3 действия.
- **SSE:** payload `challenge_wait` расширяется опциональным `action` (описание
  подготовленного шага для карточки) — doc 15.
- **Nav-промпт:** click по submit/pay/destructive разрешён **только когда task прямо
  требует действия** — система сама возьмёт подтверждение (Tier 2) или передаст
  финальный клик человеку (Tier 3). Правило «NEVER click submit/pay» смягчается до
  task-условия (иначе Tier 2/3 недостижимы для планировщика).

### Референс-сценарий (exit Phase 7, фикстура `store_checkout`)

Задача: «оформи заказ: имя X, email Y, адрес Z — доведи до оплаты» (attended).
Агент: страница товара → форма → fill имя/email/адрес (автономно) → click
«Оплатить заказ» → I-H12 → handoff-пауза → **человек нажимает кнопку сам** →
страница «Заказ принят» → resume → re-observe → результат зафиксирован в extract.
Negative: «Удалить корзину» (bare button, не submit) — unattended reject I-H12;
такой элемент Tier 1 больше не считает безопасным.

---

## Browser Protocol + State machine

- **Browser Protocol** ([browser/base.py](../backend/app/browser/base.py)) — read-only
  (`raw_snapshot / screenshot / page_url`). Добавить interaction-примитивы:
  `click(selector) / fill(selector, text) / select / submit`. Playwright их умеет —
  технически легко; риск не в API, а в решении *когда* их звать.
- **State machine** ([orchestrator/states.py](../backend/app/orchestrator/states.py)):
  ACT = navigate → ACT ∈ {navigate, click, fill, submit, sink}. DECIDE (nav-модель)
  выбирает из богатого пространства — больше промпт, планка уверенности на ACT растёт.
- **Понимание форм** — какие поля есть и что вписывать — отдельная extraction-задача
  поверх снапшота.

---

## Cloud carve-out для sink-действий (Tier 0)

Google Docs / Notion — это **облако**, а проект privacy-first (NFR-2.1/2.2, «ноль
облака»). Экспорт наружу легитимен, но это **сознательное, подтверждаемое** действие
пользователя (свой анализ → свой документ), а не молчаливый дефолт и не телеметрия.
Правило: любое действие, покидающее машину, требует явного consent. Локальные sink'и
(файл) — без consent.

**Реализация Google Docs (Tier 0) — `app/sinks/gdocs.py`:** переиспользует логику Node-решения
`run.js` (docs.documents.create + batchUpdate insertText) и его OAuth-авторизацию из референс-папки
`Gdocs-tabs editor` (credentials.json + token.json, **gitignored** — auth-материал) через
`refresh_token`, без повторного логина. google-либы — optional extra `gdocs` (ленивый импорт →
сервис работает без них, иначе `GdocsUnavailable`). Старые пресеты (`actions.json`/`action-presets.json`)
не используются — sink строит свежий вызов. Проверено вживую: документ создан и прочитан обратно.

---

## Credentials (Tier 2)

**Attended-логин (реализовано): агент паролей НЕ хранит и НЕ видит.** `login_wall` → пауза
(та же машинерия, что challenge в Phase 5) → человек логинится в видимом браузере сам →
resume → агент читает контент под логином (`reobserve_in_place`). Это снимает весь домен
хранения секретов и держит privacy-first. Хранилище credentials (Keychain и т.п.) понадобилось
бы только для **unattended**-логина — а он вне scope (login = Tier 2 = требует человека).

**Повторный вход не нужен (persist_session, реализовано):** cookie сессии (cf_clearance +
login) сохраняется в профиль по хосту (`runs/profiles/<host>.json`, gitignored — auth-материал);
следующие заходы на домен уже авторизованы, пока cookie жив. Человек логинится/проходит проверку
**один раз на домен**, не каждую сессию. Паролей всё равно не храним — только cookie. Включается
`persist_session` (config/RunConfig); по умолчанию off (запись auth-cookie на диск — сознательный выбор).

---

## Phase mapping

| Item | Phase |
|------|-------|
| Action registry + Protocol (рефактор `KNOWN_TOOLS`/`PLANNER_TOOLS`) | **6 ✅** (A-H1/A-H2 enforced) |
| Tier 0 sink — Google Docs export ✅ (`sinks/gdocs.py`) + `export_gdocs` action в LLM-планнере (consent = явный запрос) | 6 ✅ |
| Tier 0 sink — файл (`sinks/file.py` + `export_file`, локальный, без consent; первый плагин реестра) | **6 ✅** |
| Tier 1 — safe interaction (click/expand/paginate), автономно | **6 ✅** (I-H10) |
| Browser interaction-примитивы + ACT-типы | **6 ✅** (click/fill + ACT-типы в Tier 1/2) |
| Tier 2 login — attended-пауза (человек логинится сам, паролей не храним) | **6 ✅** |
| Tier 2 fill — заполнение текстовых полей (I-H11, не password) | **6 ✅** |
| Tier 2 submit — click submit под attended-подтверждением (confirm_action) | **6 ✅** |
| Credentials secure storage | 7 (не нужен, пока unattended-логин вне scope — A-3) |
| Tier 3 — «агент готовит, человек нажимает» (§ Tier 3 handoff: I-H12 + `handoff_action`) | **7 ✅** (живой exit-прогон 2026-07-30) |

---

## Contracts (Layer 2 actions, новые A-*)

| ID | Rule |
|----|------|
| A-H1 | Действие выполняется только если зарегистрировано в реестре |
| A-H2 | Tier ≥ 2 не выполняется без подтверждения (attended resume) |
| A-H3 | Tier 3 агентом **не** выполняется — только подготовка |
| A-H4 | Sink «наружу» (облако) требует явного user-consent |
| A-H5 | Credentials не попадают в логи и в контекст LLM |
| A-H6 | Anti-bot bypass остаётся запрещён (doc 24) — действия только как авторизованный пользователь |

---

## Requirements impact (нужна правка спины — отдельно, с явного go)

| Doc | Изменение |
|-----|-----------|
| doc 01 | ✅ **FR-7** добавлен (v0.5); FR-4.2 уточнён как граница Tier 1/Tier 2; Login automation → Tier 2 |
| doc 13 | ✅ **I-H7** +click, **I-H10** click-safety, `click_safety` YAML (v0.8, Tier 1); класс A-* для sink — при Tier 0 |
| doc 00 | ✅ идентичность read-only → **action-capable** (v0.4) |
| doc 24 | Реестр вместо `KNOWN_TOOLS`; связка с attended для action_confirm |

---

## Open decisions

| ID | Вопрос | Статус |
|----|--------|--------|
| A-1 | Селекторы для click/fill: CSS/текст vs нумерация элементов | ✅ **нумерация** (element referencing, спайк A-1 2026-07-20): агент ссылается по `index` ∈ `interactive_elements`; click-time — тот же селектор + visibility + document order |
| A-2 | Форма: агент заполняет по одному полю с подтверждением, или всю целиком → один submit-confirm? | ✅ **вся форма + один confirm** (Tier 2 submit, v0.6): fill автономен (I-H11), пауза-подтверждение — одна, перед submit |
| A-3 | Credentials storage | ✅ **не нужно**: attended-логин — человек вводит пароль в видимом браузере, агент не хранит/не видит; unattended-логин вне scope |
| T-1 | Граница destructive-словаря: где Tier 2 submit, где Tier 3 handoff? | ✅ **словарь узкий, ошибка в безопасную сторону** (v1.0): `send`/«отправить» без контекста заказа — Tier 2 confirm; «place order / отправить заказ / pay / buy / delete / publish …» — Tier 3. False positive = лишняя пауза (ок), false negative страхуется I-H10 confirm |
| T-2 | Как агент входит в handoff: отдельное действие LLM или enforcement? | ✅ **enforcement, не доверие LLM** (v1.0): nav может выбрать click по destructive (когда task требует) — I-H12 гейтит: unattended reject, attended → interaction сворачивает клик в handoff-паузу |
| T-3 | Референс-сценарий exit Phase 7 | ✅ фикстура `store_checkout` (v1.0): fill имя/email/адрес → click «Оплатить заказ» → handoff → человек жмёт → «Заказ принят» зафиксирован; negative — «Удалить корзину» unattended reject |

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-19 | v0.1: Action Framework — агент действует на сайте. Ось автономность×обратимость; тиры 0-3; Action registry вместо `KNOWN_TOOLS`; подтверждение через attended-субстрат (Phase 5); cloud carve-out для sink; FR-4.2 инверсия (спина — правится отдельно) |
| 2026-07-20 | **v0.2 (Tier 1 старт):** уточнено — Tier 1 click НЕ инвертирует FR-4.2, а делает его границей Tier 1/Tier 2 (submit/login = порог). Спина правлена: doc 00 v0.4, doc 01 v0.5 (FR-7), doc 13 v0.8 (I-H7+click, I-H10 click-safety). A-1 закрыт (нумерация элементов). Спайк A-1 element referencing реализован (read-only) |
| 2026-07-20 | **v0.3 (Tier 2 login):** attended-логин реализован — `login_wall` + attended → пауза (человек логинится в видимом браузере), паролей агент не хранит/не видит; `looks_like_challenge` расширен на login_wall + login thin-guard (виджет на толстой странице ≠ login_wall). **A-3 credentials закрыт** (человек вводит сам). doc 13 v0.8.1 (I-H3 attended), doc 01 v0.5.1 (FR-7.4). Next Tier 2: submit-формы под action_confirm (A-2) |
| 2026-07-20 | **v0.4 (persist-session):** § Credentials — `persist_session`: storage_state (cookie сессии cf_clearance+login) по хосту в `runs/profiles/` (gitignored), повторный заход без нового логина/проверки, пока cookie жив; паролей не храним. `Settings.profile_path`, `PlaywrightSession` load/save storage_state, opt-in флаг. Закрывает backlog doc 24 «cookie сессии по доменам» (doc 24 v0.8). Живой смоук: cookie run1 → виден в run2 |
| 2026-07-20 | **v0.5 (Tier 2 fill):** `fill`-действие — агент вписывает текст в поля (`AgentAction.fill`+value, `Browser.fill_element`, `interaction.act_on_element` для click+fill). **I-H11** fill-safety (только текстовые поля, никогда password — doc 13 v0.8.2). Навигатор учит fill. Живой смоук: text/textarea заполнены на реальном DOM, password не тронут. **Next: submit** — click submit под attended-подтверждением (reuse `waiting_user`/resume; A-2 = вся форма + один confirm) |
| 2026-07-20 | **v0.6 (Tier 2 submit — submit-формы завершены):** submit под attended-подтверждением. `EventAttendedGate.confirm_action` (пауза `waiting_user`, kind=`confirm_submit`, reuse resume + SSE `challenge_wait` + `ChallengeCard`); `ctx.attended` + `click_target_safe` пропускает submit при attended (иначе reject); `act_on_element` паузит на submit → confirmed=execute / declined(timeout)=None→stop. `build_action_context` вынесен из loop.py (headroom). doc 13 v0.8.3 (I-H10), doc 24 v0.9. Живой смоук: fill+submit onsubmit на реальной форме |
| 2026-07-20 | **v0.7 (Tier 0 sink — Google Docs):** `app/sinks/gdocs.py` — экспорт в Google Doc (create + insertText), переиспользует логику и OAuth Node-решения `run.js` из референс-папки `Gdocs-tabs editor` (gitignored) через `refresh_token`, без повторного логина. Optional extra `gdocs` (ленивый импорт). `Settings.gdocs_dir`/`gdocs_credentials`/`gdocs_token`. Старые пресеты не используются. Проверено вживую (doc создан + read-back). Осталось: registry-обёртка Tier 0 + consent-гейт + вызов из research-флоу |
| 2026-07-20 | **v0.8 (Tier 0 registry-обёртка):** `export_gdocs` — action LLM-планнера (`PLANNER_TOOLS` + meta-промпт + M-H3: run_id только из сессии); `runner._export_gdocs` собирает контент из результата run'а (article/facts) и зовёт `sinks/gdocs`. **Consent (A-H4) = явный запрос пользователя** («скопируй в Google Docs»); облачное действие помечается tool-нотой (M-S1). `GdocsUnavailable`/сеть → сообщение в чат, сессия не падает. Проверено вживую E2E: runner→sink→реальный Google Doc. Замыкает исходный сценарий «найди статью и скопируй в Google Docs» |
| 2026-07-20 | **v0.9 (Action registry + file-sink — Phase 6 закрыта):** § Registry реализован — пакет `research/actions/` (`ActionSpec` frozen dataclass + `registry`), `KNOWN_TOOLS`/`PLANNER_TOOLS` удалены; membership (M-H1/**A-H1**) и пер-action enforce (M-H3) — через реестр в обоих путях (runner + llm_planner); **A-H2/A-H3 гейт в runner** (tier ≥ 2 без подтверждения не исполняется); блок tools meta-промпта собирается из `data/prompts/tools/<name>.txt` (`{TOOLS_BLOCK}`). **File-sink** — `sinks/file.py` + действие `export_file` (Tier 0 локальный, без consent; basename-санитайз, файл в artifacts сессии) — первый плагин реестра: runner/planner не менялись. Общая сборка контента экспорта → `sinks/content.py` (DRY gdocs/file). Phase mapping: registry ✅, file-sink ✅, browser-примитивы ✅; A-2 закрыт (вся форма + один confirm, v0.6). 180 тестов |
| 2026-07-20 | **v1.0 (Tier 3 handoff — дизайн, Phase 7):** § Tier 3 — «агент готовит, человек нажимает»: handoff-механика на attended-субстрате (`gate.handoff_action` по образцу `confirm_action`, kind=`handoff`, resume → re-observe; агент финальную кнопку не жмёт никогда — жмёт человек в видимом браузере). **I-H12** destructive-click: словарь стемов в `crawl.contract.yaml` (`destructive_signals`), unattended → reject, attended → handoff; закрывает дыру Tier 2 (submit «Оплатить» больше не проходит через confirm, где нажал бы агент). SSE `challenge_wait` +`action`; nav-промпт: click submit/pay только когда task прямо требует. Решения T-1 (узкий словарь, send=Tier 2), T-2 (enforcement, не доверие LLM), T-3 (референс — фикстура `store_checkout`) |
| 2026-07-30 | **v1.1 (Tier 3 ✅ живой exit-прогон):** сценарий пройден на фикстуре `store_checkout`: агент заполнил форму одним `fill_form`, ВЫБРАЛ «Оплатить заказ» → пауза `handoff` → **человек нажал сам** → агент прочитал исход и зафиксировал факт `order_number = WX9-1337`. Девять дефектов, которые юниты не показывали, найдены прогоном и исправлены: (1) в снапшот добавлено `value` полей (агент трижды заполнял одно поле, не видя заполненности; password не собирается никогда); (2) действие **`fill_form`** — вся форма за одно решение LLM, I-H11 проверяет каждое поле пачки (password в пачке отклоняет её целиком); (3) `rate_limit_ms` убран из DOM-действий (он про вежливость к серверу, а click/fill запросов не делают) → `DOM_SETTLE_MS` 250; (4) пометки элементов зависят от режима — раньше submit был «do NOT click» всегда, из-за чего handoff в attended был **недостижим**; (5) формулировка «PICK THIS» вместо «человек нажмёт» (второе модель читала как «действие не нужно» и не выбирала клик); (6) **прогрев nav-модели** параллельно robots/пробам — первый шаг стоил 8.7 s против 3.6 s; (7) в attended закрывается стартовое пустое окно Chromium + `bring_to_front` (человек смотрел не в то окно); (8) закрытый человеком браузер → `handoff_result`, а не `TargetClosedError` из середины ACT; (9) **один необратимый шаг за прогон**: после handoff агент фиксирует исход, а не ищет следующую кнопку (на живом прогоне потянулся к «Удалить корзину» — I-H12 остановил). 200 тестов |
| 2026-08-03 | **v1.2:** пауза Tier 3 кончается по resume **или** по устойчивому изменению страницы (`page_probe`, два опроса подряд); `handoff_resolved_by` в записи прогона; Tier 2 confirm автодетекта не получает. Находка живого прогона: человек нажал кнопку и ждал, агент стоял |
