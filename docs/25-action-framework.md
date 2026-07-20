# 25 — Action Framework (агент действует на сайте)

> Local Web Agent · Design doc · **v0.7** · 2026-07-20

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

## Action Protocol + Registry

Сейчас инструменты Layer 2 — захардкоженный кортеж `KNOWN_TOOLS`
([research/runner.py](../backend/app/research/runner.py)). Заменяем на **реестр**:

```python
class Action(Protocol):
    name: str
    tier: int                       # 0..3 → политика подтверждения
    reversible: bool
    args_schema: type[BaseModel]    # типизация + валидация
    contract: ActionContract        # per-action проверка (расширяет doc 13)
    async def execute(self, ctx: ActionContext) -> ActionResult: ...
```

- **M-H1** («только зарегистрированные tools») из ограничения превращается в **точку
  расширения**: новое действие = новый плагин в `research/actions/`, раннер не трогаем.
- LLM-планнер ([llm_planner.py](../backend/app/research/llm_planner.py)) видит реестр;
  пост-валидация M-H1..M-H3 распространяется на новые действия.

**Пакет:** `app/research/actions/{base,registry}.py` + по модулю на действие
(`export_gdocs.py`, `click.py`, `fill.py`, …).

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
| Action registry + Protocol (рефактор `KNOWN_TOOLS`) | 6 |
| Tier 0 sink — Google Docs export ✅ (`sinks/gdocs.py`, переиспользует референс-решение); файл + registry-обёртка — след. | 6 🛠 |
| Tier 1 — safe interaction (click/expand/paginate), автономно | **6 ✅** (I-H10) |
| Browser interaction-примитивы + ACT-типы | 6 |
| Tier 2 login — attended-пауза (человек логинится сам, паролей не храним) | **6 ✅** |
| Tier 2 fill — заполнение текстовых полей (I-H11, не password) | **6 ✅** |
| Tier 2 submit — click submit под attended-подтверждением (confirm_action) | **6 ✅** |
| Credentials secure storage | 7 |
| Tier 3 — «агент готовит, человек нажимает» | 7+ |

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
| A-2 | Форма: агент заполняет по одному полю с подтверждением, или всю целиком → один submit-confirm? | 🔲 TBD |
| A-3 | Credentials storage | ✅ **не нужно**: attended-логин — человек вводит пароль в видимом браузере, агент не хранит/не видит; unattended-логин вне scope |

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
