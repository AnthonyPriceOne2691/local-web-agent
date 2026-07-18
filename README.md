# Local Web Agent

Локальный **research agent** с чатом: кидаете URL (один или пачкой), описываете задачу — агент сам ходит по сайтам, делает скрины, сравнивает результаты. **Только на вашей машине**, без облачных API.

**Статус:** Design phase · Phase 0 benchmark — 🔲  
**Автор:** Anton Aspidov  
**Планирование:** см. [`docs/`](docs/)

## Идея в одном предложении

Не scraper с CSS-селекторами, а **двухслойный agent**: Layer 1 обходит один сайт; Layer 2 (Research Chat) оркестрирует N сайтов и сравнивает («опиши дизайн 4 конкурентов», «у кого полнее статья про X»). См. [`docs/24-research-chat-agent.md`](docs/24-research-chat-agent.md).

## Железо (зафиксировано)

| Параметр | Значение |
|----------|----------|
| Машина | MacBook Air 13 **M5** |
| RAM | **32 GB** |
| SSD | **512 GB** |
| Развёртывание | **Local-only**, offline inference |

## Документы

| Doc | Описание |
|-----|----------|
| [docs/README.md](docs/README.md) | Индекс всех design docs |
| [docs/00-project-overview.md](docs/00-project-overview.md) | Контекст, цели, решения |
| [docs/06-mvp-phases.md](docs/06-mvp-phases.md) | Phases 0–3, exit criteria |

> ⚠️ Код пишется **только после** Phase 0 benchmark (см. [docs/06-mvp-phases.md](docs/06-mvp-phases.md)).

## Контроль модели

Поведение LLM ограничивается **Agent Behavioral Contracts** (Bhardwaj, [arXiv:2602.22302](https://arxiv.org/abs/2602.22302)) — runtime enforcer **до** Playwright, не prompt-only. Детали: [docs/13-behavioral-contracts.md](docs/13-behavioral-contracts.md).

## Навигация по сайтам

**Hybrid navigation** (боевой референс: Linkbuilding SEOLB-499): slug-словари, homepage-first, LLM выбирает among top-K кандидатов — не угадывает URL. [docs/21-navigation-hints.md](docs/21-navigation-hints.md) · `data/navigation/path_hints.yaml`

## Скриншоты страниц

На каждом OBSERVE — PNG в **desktop / tablet / mobile** (design audit — все три). Навигация и DOM — desktop. [docs/22-page-screenshots.md](docs/22-page-screenshots.md) · `data/navigation/viewports.yaml`

## Ближайший шаг

Phase 0 — spike: Playwright + Ollama + один сайт + одна задача → замер latency и качества извлечения.
