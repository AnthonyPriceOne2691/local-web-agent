# Design Documents Index

> Local Web Agent · Design doc · **v2.1** · 2026-08-05

Планирование проекта ведётся через design docs в этой папке: любое изменение дизайна = правка дока + запись в changelog + bump версии в шапке, и версии в шапке, индексе и changelog обязаны совпадать (инвариант [CLAUDE.md](../CLAUDE.md)).

Phase 0–7 закрыты, решения D-1..D-14 закрыты (см. [06-mvp-phases.md](06-mvp-phases.md) — новых фаз там нет, только таблица необязательных улучшений). Процессное состояние и текущая поставка — [delivery/active/STATUS.md](../delivery/active/STATUS.md).

## Document map

| Doc | Status | Description |
|-----|--------|-------------|
| [00-project-overview.md](00-project-overview.md) | ✅ **v0.4** | Two-layer arch; Research Chat UX; action-capable (Phase 6) |
| [01-requirements.md](01-requirements.md) | ✅ **v0.6** | FR/NFR incl. FR-6/FR-7 (actions, Tier 0–3); SSRF, cancel, D-12, hop depth |
| [02-architecture.md](02-architecture.md) | ✅ **v0.2.1** | Layer 1 + Layer 2 |
| [03-browser-pipeline.md](03-browser-pipeline.md) | ✅ **v0.10** | Playwright pipeline; robots своим UA; SPA fallback; ожидание `commit` + короткий бюджет DOMContentLoaded |
| [04-crawl-orchestrator.md](04-crawl-orchestrator.md) | ✅ **v0.7** | Agent loop + VISION_BATCH; hop depth; landing domain |
| [05-extraction-schema.md](05-extraction-schema.md) | ✅ **v0.4** | ComparisonResult + excluded; article candidates |
| [06-mvp-phases.md](06-mvp-phases.md) | ✅ **v0.12.1** | **Phases 0–7 DONE**; дальше — только backlog улучшений |
| [07-tech-stack.md](07-tech-stack.md) | ✅ **v0.2.1** | Stack + LLM settings (async_api, deps) |
| [12-session-storage.md](12-session-storage.md) | ✅ **v0.6** | SQLite + research sessions реализованы; legacy-импорт; sweep |
| [13-behavioral-contracts.md](13-behavioral-contracts.md) | ✅ **v0.9** | ABC; I-H10 click / I-H11 fill safety; submit под attended-confirm; **I-H12** destructive → handoff |
| [14-llm-model-split.md](14-llm-model-split.md) | ✅ **v0.6** | qwen3 канон; лёгкая 8b на DOM-решения; VLM; fallback-пара |
| [15-api-cli-spec.md](15-api-cli-spec.md) | ✅ **v0.9** | + SSE events, report, статика UI, attended resume/`challenge_wait` (kinds: challenge/login/confirm_submit/handoff) |
| [16-prompts-library.md](16-prompts-library.md) | ✅ **v0.11** | Params: structured outputs, think; маршрутизация nav-моделей; быстрый синтез; **язык ответа = язык запроса** |
| [17-ui-screens.md](17-ui-screens.md) | ✅ **v0.7** | CLI flows; Chat UI: liquid glass + человеческий словарь; язык ответа = язык запроса; раскрытие карточек, движение |
| [18-engineering-standards.md](18-engineering-standards.md) | ✅ **v0.4** | 500 LOC, SOLID, DRY, coverage; контур ruff + mypy на scripts/ |
| [19-phase0-benchmark-results.md](19-phase0-benchmark-results.md) | ✅ **v1.0 DONE** | Все гейты ✅; qwen3 single-model рекомендация |
| [20-context-token-budget.md](20-context-token-budget.md) | ✅ **v0.4** | Token budget; non-Latin; compare N>3; вход синтеза ≠ латентность |
| [21-navigation-hints.md](21-navigation-hints.md) | ✅ **v0.11** | + content_search, sitemap P2.5, RU keywords; **тема главнее формы**, отбор по счёту, а не по позиции в DOM; штрафы смотрят путь; тема в транслите, обучающий жанр против промо, выбор внутри раздела |
| [22-page-screenshots.md](22-page-screenshots.md) | ✅ **v0.4** | PNG multi-viewport; D-11 closed (detect→hide→click) |
| [23-vision-analysis.md](23-vision-analysis.md) | ✅ **v0.3** | Key pages, failure modes; qwen2.5vl |
| [24-research-chat-agent.md](24-research-chat-agent.md) | ✅ **v0.15** | Phase 4 DONE; attended + видимость окна по надобности; Phase 6 actions; неполный обход виден в итоговом ответе; причина исключения называет виновника |
| [25-action-framework.md](25-action-framework.md) | ✅ **v1.2** | Действия целиком: Tier 0 sinks (Google Docs + файл) · Tier 1 click · Tier 2 login/fill/submit · **Tier 3 handoff** (агент готовит, человек нажимает) — Phase 6–7 |
| [26-real-site-trials.md](26-real-site-trials.md) | 🛠 **v0.14** | Испытания на реальных сайтах: протокол по типам (магазин / SPA / новости), язык задачи RU+EN, отобранные сайты, журнал результатов (T-3, T-2b, T-3d…T-3h: 15 дефектов) |

> Номера 08–11 не используются (историческая нумерация, выровнена с voice-interview-coach).

## Project status

| Phase | Status |
|-------|--------|
| Design docs | ✅ **все решения D-1..D-14 закрыты**; review pass 2 (hop depth D-13, RU keywords, article candidates D-14, startup sweep, partial failure) + D-11 closed |
| Phase 0 Benchmark | ✅ **DONE 2026-07-13** — все exit-критерии пройдены ([doc 19](19-phase0-benchmark-results.md) v1.0); хвосты: real re-check p50, qwen3 на real перед финалом D-2/D-3 |
| Phase 1 Agent loop | ✅ **DONE 2026-07-18** — backend/app + cli + prompts; 30 тестов, coverage 87%, E2E 3/3 ([doc 06](06-mvp-phases.md) § Phase 1) |
| **Phase 2 Full MVP** | ✅ **DONE 2026-07-18** — exit-бенчмарк 4/5 (80% гейт) + vision E2E (#8) + PLAN p50 7.9 s ([doc 06](06-mvp-phases.md) § Phase 2); 96 тестов, cov 93% |
| **Phase 3 Research Agent** | ✅ **DONE 2026-07-18** — UC-1/UC-2 exit-бенчмарк пройден ([doc 06](06-mvp-phases.md) § Phase 3); 115 тестов |
| **Phase 4 Chat UI** | ✅ **DONE 2026-07-19** — UI + SSE + `planner: llm`; UC-1/UC-2 прогнаны целиком из чата в браузере (9.9 / 18.1 мин), follow-up диалог и re-crawl через планнер работают ([doc 06](06-mvp-phases.md) § Phase 4) |
| **Phase 5 attended-режим** | ✅ **DONE 2026-07-19** — human-in-the-loop прохождение anti-bot challenge (видимый браузер, `waiting_user`, resume, SSE `challenge_wait`, Chat UI, CLI `--attended`); 137 тестов. **Подтверждён вживую** на публичном сайте за managed challenge: пауза → человек прошёл проверку сам → контент прочитан ([doc 24](24-research-chat-agent.md) § Attended-режим) |
| **Phase 6 Action Framework** | ✅ **DONE 2026-07-20** — агент действует на сайте ([doc 25](25-action-framework.md)): Tier 1 автономный click · Tier 2 login/fill/submit под подтверждением человека · persist-session · Tier 0 sinks (Google Docs + файл) · Action registry (`research/actions/`, A-H1/A-H2). Живой E2E «найди статью → скопируй в Google Docs»; 181 тест ([doc 06](06-mvp-phases.md) § Phase 6–7) |
| **Phase 7 Tier 3 handoff** | ✅ **DONE 2026-07-30** — «агент готовит, человек нажимает»: необратимую кнопку агент не жмёт никогда (I-H12 + пауза `handoff`). Живой exit-прогон: агент заполнил форму, выбрал «Оплатить заказ», **человек нажал**, агент зафиксировал `order_number = WX9-1337`; девять дефектов прогона исправлены; 200 тестов ([doc 25](25-action-framework.md) v1.1–v1.2) |
| **Дальше** | Фаз в дизайне больше нет. Текущий этап — **испытания на реальных сайтах** ([doc 26](26-real-site-trials.md): протокол, отобранные сайты, журнал) + backlog улучшений ([doc 06](06-mvp-phases.md) § Phase 5+). Состояние поставок — [delivery/active/STATUS.md](../delivery/active/STATUS.md) |

## Conventions

- Версия в шапке: `v0.x`
- **Changelog** в конце каждого документа
- Статусы: ✅ зафиксировано · 🔲 TBD · ❌ out of scope
- Новые docs: `21-`, `22-`, … по мере необходимости

## Review order (recommended)

1. Overview → Requirements
2. Architecture → Browser pipeline → **Context/token budget (20)**
3. Crawl orchestrator → **Navigation hints (21)** → Extraction schema
4. Behavioral contracts → MVP phases → **Vision (23)** → **Research Chat (24)** → Tech stack
5. Benchmark results (19) — перед стартом Phase 1

## Pending decisions

**Открытых решений нет** — все D-1..D-14 закрыты; таблица ведётся как запись принятых решений с обоснованием.

| ID | Decision | Status |
|----|----------|--------|
| D-1 | Browser runtime | ✅ Playwright (Chromium headless, **async_api**) — **подтверждён Phase 0** (0 браузерных сбоев) |
| D-2 | LLM planning + navigation | ✅ **CLOSED (2026-07-18):** `qwen3:14b` (`think:false`) — подтверждён Phase 2 exit-бенчмарком на real-сайтах (playwright.dev ✅, ollama.com ✅; PLAN p50 7.9 s). Канон doc 16 v0.5; qwen2.5:14b — fallback |
| D-3 | LLM structured extraction | ✅ **CLOSED (2026-07-18):** `qwen3:14b` (`think:true`) — **single-model split** (ноль свопов; synth max 95.9 s на python.org vs 203 s у r1 в Phase 0). r1:14b — fallback (doc 16 v0.5) |
| D-4 | Observation mode MVP | ✅ DOM-first + screenshots (doc 22) |
| D-5 | Interface Layer 1 | ✅ CLI + REST Phase 1–2 |
| D-5b | Primary product UX | ✅ **Research Chat UI Phase 4** ([doc 24](24-research-chat-agent.md)) |
| D-6a | Page screenshot capture | ✅ **CLOSED** ([doc 22](22-page-screenshots.md)) |
| D-6b | Vision LLM on screenshots | ✅ **CLOSED + подтверждён Phase 0:** `qwen2.5vl:7b` — 5/5 рубрика, JSON 100%, p95 14.3 s ([doc 19](19-phase0-benchmark-results.md) Part B) |
| D-7 | Multi-site execution | ✅ **CLOSED:** sequential queue only ([doc 24](24-research-chat-agent.md)) |
| D-8 | Two-layer architecture | ✅ **CLOSED** ([doc 24](24-research-chat-agent.md)) |
| D-9 | Chat as primary UX | ✅ **CLOSED** Phase 4 ([doc 24](24-research-chat-agent.md)) |
| **D-10** | **Site navigation strategy** | ✅ **CLOSED:** hybrid hints + LLM top-K ([doc 21](21-navigation-hints.md), ref SEOLB) |
| **D-11** | **Cookie-banner dismissal (design audit)** | ✅ **CLOSED:** detect → CSS-hide (default, без согласия) → CMP-click reject-first (fallback); Phase 1 honest capture ([doc 22](22-page-screenshots.md)) |
| **D-12** | **API concurrency** | ✅ **CLOSED:** 1 активный crawl глобально; 409 на второй POST; startup sweep ([doc 15](15-api-cli-spec.md), [doc 12](12-session-storage.md)) |
| **D-13** | **max_depth semantics** | ✅ **CLOSED:** hop depth (навигационные переходы), не сегменты URL — иначе UC-2/sitemap нерабочие ([doc 04](04-crawl-orchestrator.md) policy #2) |
| **D-14** | **content_search: сколько статей искать** | ✅ **CLOSED:** до 3 кандидатов per site, R1 выбирает лучшую — «самая полная», не «первая найденная» ([doc 21](21-navigation-hints.md)) |

## Reference

- **Agent Behavioral Contracts:** Bhardwaj, arXiv:[2602.22302](https://arxiv.org/abs/2602.22302) · локально: `/Users/anthony/Documents/2602.22302v1.pdf`
- **Navigation hints (боевой референс):** Linkbuilding `CONTACT_SCRAPER_FALLBACK_DESIGN.md` (SEOLB-499) → [doc 21](21-navigation-hints.md)

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-08-05 | **v2.1:** doc 21 -> v0.11, doc 26 -> v0.14 (выбор внутри раздела: различает то слово задачи, которого нет в контексте страницы — эталонная статья на хабе #26 -> #1; три ограничения правила поставлены замером) |
| 2026-08-05 | **v2.0:** doc 15 -> v0.9, doc 16 -> v0.11, doc 24 -> v0.15, doc 26 -> v0.13 (починка найденного в T-3h: бюджет синтеза 420 s по замеру 28 стадий, прочитанное не выбрасывается при падении синтеза, глубина обхода перестала быть тихой — флаг CLI + поле API + действующее число в ответе) |
| 2026-08-04 | **v1.9:** doc 24 -> v0.14, doc 26 -> v0.12 (живой прогон T-3h: маршрут первого хопа подтверждён на legalbet, A/B сорван сетью; причина исключения теперь называет виновника — «прочитано 4 стр., ответ не собрался: модель не ответила» вместо «сайт не ответил») |
| 2026-08-04 | **v1.8:** doc 21 -> v0.10, doc 26 -> v0.11 (T-3g: первый хоп починен по объявленному заранее критерию — хаб к статьям в top-10 на всех трёх корнях; тема ищется и в транслитерированном пути, обучающий жанр против промо, вес жанра двойной) |
| 2026-08-04 | **v1.7:** doc 24 -> v0.13, doc 26 -> v0.10 (живой прогон T-3f: 0 статей из 3 как в базовой линии, маршрут сменился на записи; оговорка про неполный обход теперь доходит до итогового ответа; замер контаминирован глубиной — записано как моя ошибка) |
| 2026-08-04 | **v1.6:** doc 21 -> v0.9, doc 26 -> v0.9 (T-3e: офлайн-замер всей цепочки — правка T-3d проверялась на хопе 2, а прогон умирал на хопе 1; штрафы формулы смотрят путь, а не весь URL; блокер прогона — VPN-тоннель машины) |
| 2026-08-04 | **v1.5:** doc 21 -> v0.8, doc 03 -> v0.10, doc 20 -> v0.4 (испытание T-3d: тема главнее формы; лимит ссылок — предохранитель по памяти, отбор по счёту) |
| 2026-08-03 | **v1.4:** doc 16 → v0.10 и doc 17 → v0.7 (язык ответа = язык запроса; каркас ответа следует тому же языку, подписи интерфейса остаются английскими) |
| 2026-08-03 | **v1.3:** doc 16 → v0.9 и doc 17 → v0.6 (язык вывода — английский всегда; служебный текст не показывается человеку; раскрытие карточек и движение) |
| 2026-08-03 | **v1.2:** doc 03 → v0.9 (стратегия ожидания навигации — находка испытания T-3a: чужая аналитика держала DOMContentLoaded 30 s и стоила 2 сайтов из 3) |
| 2026-08-03 | **v1.1:** зарегистрирован [doc 26](26-real-site-trials.md) — протокол испытаний на реальных сайтах (магазин / SPA / новости, задачи RU+EN, отобранные сайты, журнал результатов). Строка «Дальше» в Project status теперь ссылается на него |
| 2026-08-03 | **v1.0 (первая версионированная ревизия индекса):** плюс doc 06 → v0.12.1 (persist `cf_clearance` в § Phase 5+ помечен сделанным). У индекса не было ни версии, ни changelog — сам он нарушал § Conventions, поэтому его расхождение с доками ничем не ловилось. Синхронизированы версии пяти доков, где индекс отстал (01 v0.5.3→v0.6, 06 v0.10→v0.12, 13 v0.8.3→v0.9, 15 v0.7→v0.8, 25 🛠 v0.8→✅ v1.2); у всех 22 доков шапка и индекс сверены. Таблица **Project status** дополнена Phase 6 и Phase 7 и строкой «Дальше» (фаз больше нет, идут испытания на реальных сайтах); Phase 5 переведена из 🛠 в ✅ (живое подтверждение 2026-07-19). Отмечено, что открытых решений нет |
