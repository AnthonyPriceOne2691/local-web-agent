# 00 — Project Overview

> Local Web Agent · Design doc · **v0.4** · 2026-07-20

## One-liner

Локальный **research agent** с чатом: пользователь кидает URL (один или пачкой), формулирует задачу — агент **сам выбирает инструменты** (crawl, vision, compare), обходит сайты и возвращает ответ, в т.ч. сравнительный. Движок crawl — на MacBook Air M5, без облачных API.

## Контекст

**Кто:** Anton Aspidov — AI Automation Engineer. Опыт с LLM pipelines, internal tools, behavioral contracts (см. Voice Interview Coach в том же workspace).

**Проблема:** классические парсеры (CSS-селекторы, regex) ломаются на каждом новом сайте. Облачные агенты («зайди на сайт и найди X») работают, но отправляют URL и контент на чужие серверы. Нужен **личный research agent**, который ведёт себя как человек при просмотре сайта, но живёт только на локальной машине.

**Решение:** двухслойная архитектура ([doc 24](24-research-chat-agent.md)):

1. **Research Chat Agent (Layer 2):** чат → meta-agent → tool calls → compare → ответ пользователю
2. **Crawl Worker (Layer 1):** один сайт — observe → navigate → vision → ExtractionResult

**Layer 1** (один сайт):

1. Пользователь задаёт **задачу** и **стартовый URL**
2. Агент **наблюдает** страницу (DOM, текст, ссылки, скриншоты)
3. **Планирует** следующий шаг: перейти / извлечь / завершить
4. Возвращает **ExtractionResult** с evidence

**Layer 2** (multi-site, целевой UX):

1. Пользователь в **чате** кидает N URL + задачу («сравни дизайн», «найди статью у конкурентов»)
2. Meta-agent планирует: N × `crawl_site` (sequential) → `compare_results`
3. Ответ в чат + comparison report

## Чем это не является

| Не это | Почему |
|--------|--------|
| Простой scraper (title, email regex) | Цель — семантическое понимание и навигация |
| Облачный browser agent (ChatGPT browsing) | Privacy + offline |
| Массовый crawler (millions of pages) | Solo tool, controlled scope |
| Anti-bot bypass tool | Out of scope; уважаем robots.txt и rate limits |

## Целевые сценарии использования

- **Design audit:** скриншоты + vision + сравнение нескольких сайтов (UC-1, doc 24)
- **Competitive content:** найти статью на N сайтах, сравнить полноту (UC-2, doc 24)
- **Research:** найти pricing, team page, office locations, product features

## Принятые решения (на старте проектирования)

| Решение | Значение | Статус |
|---------|----------|--------|
| Развёртывание | Локально на Mac | ✅ зафиксировано |
| Железо | MacBook Air 13 M5, 32 GB RAM, 512 GB SSD | ✅ зафиксировано |
| Browser | Playwright (Chromium headless) | ✅ зафиксировано |
| Observation MVP | **DOM-first (desktop)** + **screenshots** desktop/tablet/mobile (doc 22) | ✅ зафиксировано |
| Vision LLM on screenshots | **`qwen2.5vl:7b`** batch analyze → vision_insights (doc 23) | ✅ Phase 2 |
| Privacy | Все crawl runs, snapshots, LLM prompts — локально | ✅ зафиксировано |
| Cloud fallback | Не в MVP | ❌ out of scope |
| Interface MVP (Layer 1) | **CLI** + REST API | ✅ Phase 1–2 |
| **Product UX (Layer 2)** | **Research Chat** + `agent research` | ✅ Phase 3–4 ([doc 24](24-research-chat-agent.md)) |
| Chat UI | **Phase 4** — primary interface | ✅ зафиксировано |
| Multi-site | **Sequential queue** only (M5 RAM) | ✅ D-7 closed |
| Two-layer architecture | Layer 2 meta-agent + Layer 1 crawl worker | ✅ D-8 ([doc 24](24-research-chat-agent.md)) |
| **Навигация по сайту** | **Hybrid:** deterministic hints (slug dictionaries, ref SEOLB) + LLM top-K | ✅ ([doc 21](21-navigation-hints.md)) |
| **Действия на сайте (Phase 6)** | Action framework: Tier 0 sink + Tier 1 автономная безопасная интеракция (click не-submit); Tier 2+ (submit/login) под attended-подтверждением | 🛠 started ([doc 25](25-action-framework.md)) |
| **Контроль модели** | **Agent Behavioral Contracts** (arXiv:2602.22302) — runtime enforcer **до** Playwright | ✅ ([doc 13](13-behavioral-contracts.md)) |
| Tech stack | Python FastAPI + Playwright + Ollama (doc 07) | ✅ зафиксировано |
| LLM split | Qwen 14B (nav) + **qwen2.5vl:7b** (vision) + R1 14B (JSON) | ✅ **provisional** — A/B в Phase 0 (qwen3:14b single-model, gpt-oss:20b — doc 14) |
| Concurrency | **1 активный crawl глобально** (D-12); второй POST /runs → 409 | ✅ (doc 15) |
| Cookie banners (design audit) | Honest capture MVP; best-effort dismiss Phase 2 (D-11, doc 22) | 🔲 proposed |
| Phase 0 benchmark | Обязателен до prod-кода | 🔲 next |

## Отличие от облачного «зайди на сайт»

| Аспект | Cloud agent | Local Web Agent |
|--------|-------------|-----------------|
| Данные | Уходят на API провайдера | Остаются на Mac |
| Скорость | Быстрее (мощные GPU) | Медленнее, но приемлемо для research |
| Качество рассуждений | GPT-4 class | 14B local — хуже на сложных задачах |
| Стоимость | Подписка / токены | Бесплатно после setup |
| Кастомизация | Ограничена | Полный контроль prompts, contracts, storage |

## Success criteria

- **Phase 0:** один сайт, одна задача — agent находит ответ за **< 10 страниц** и **< 5 min** wall time
- **MVP:** 5 типовых задач на 5 разных сайтах — **≥ 80%** success rate (answer found + evidence)
- **Phase 2 (Layer 1 MVP):** single-site crawl + vision + contracts
- **Phase 3:** multi-site `agent research` + compare synthesis
- **Phase 4:** Research Chat UI — основной способ использования
- **Usability:** «4 сайта, сравни дизайн» → осмысленный comparative report за **< 20 min** (4 sites sequential)
- **Privacy:** zero outbound LLM calls; Playwright только к явно указанным URL

## Связанные документы

- [01-requirements.md](01-requirements.md)
- [02-architecture.md](02-architecture.md)
- [04-crawl-orchestrator.md](04-crawl-orchestrator.md)
- [06-mvp-phases.md](06-mvp-phases.md)
- [13-behavioral-contracts.md](13-behavioral-contracts.md) — ABC (arXiv:2602.22302)
- [21-navigation-hints.md](21-navigation-hints.md) — hybrid navigation (SEOLB ref)
- [24-research-chat-agent.md](24-research-chat-agent.md) — multi-site chat, compare, UC-1/UC-2

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-07-05 | Initial overview from design discussion |
| 2026-07-05 | Контроль модели через ABC (arXiv:2602.22302) зафиксирован в решениях |
| 2026-07-05 | Hybrid navigation: SEOLB path hints + LLM top-K (doc 21) |
| 2026-07-05 | Page screenshots (Playwright PNG, doc 22); vision batch Phase 2 (doc 23) |
| 2026-07-05 | **v0.2:** two-layer architecture; Research Chat (doc 24); D-7/D-8/D-9 |
| 2026-07-05 | **v0.3 (review):** vision-тег → qwen2.5vl:7b; LLM split помечен provisional (Phase 0 A/B); решения D-11 (cookie banners), D-12 (concurrency=1) |
| 2026-07-20 | **v0.4 (Phase 6 start):** идентичность эволюционирует read-only research → **action-capable** — агент не только читает, но и действует на сайте (Action framework, [doc 25](25-action-framework.md)): Tier 0 sink + Tier 1 автономная безопасная интеракция; Tier 2+ под подтверждением. Anti-bot bypass по-прежнему out of scope (галочку CF жмёт человек, attended) |
