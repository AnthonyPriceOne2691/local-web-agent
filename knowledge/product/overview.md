---
type: Overview
title: Local Web Agent — что это
description: Локальный action-capable research-агент: читает сайты, сравнивает, действует на них и отдаёт результат наружу — всё на одной машине.
status: stable
tags: [product, privacy]
generated:
  by: claude-code/fable-5
  at: 2026-07-27T00:00:00Z
implementation: []   # обзор продукта, не поведение конкретного модуля
---

# Purpose

Агент исследует сайты **вместо человека** и на локальной машине (MacBook Air M5,
32 GB): обходит страницы по смыслу, извлекает факты с цитатами-доказательствами,
сравнивает N сайтов по рубрике, действует на странице (клик/ввод/submit) и
доставляет результат (Google Docs / файл).

# Два слоя

| Слой | Что делает | Вход |
|---|---|---|
| Layer 1 — crawl worker | один сайт: OBSERVE → DECIDE → ACT → SYNTHESIZE | `agent crawl --url --task` |
| Layer 2 — research-сессия | N сайтов последовательно + сравнение | `agent research`, Chat UI |

Поверх — Chat UI (React + SSE) с LLM-планнером: сообщение без URL превращается в
план действий над уже готовыми результатами сессии.

# Canonical rules

- **LLM только локально** (Ollama). Ноль телеметрии, ноль облачных моделей.
- **Единственный sanctioned outbound** — экспорт в Google Docs по явному запросу
  пользователя (Tier 0 sink, opt-in). Всё остальное не уходит с машины.
- **API слушает только `127.0.0.1`**; одновременно активен один crawl.
- **robots.txt соблюдается**; обход anti-bot защиты запрещён навсегда —
  [no anti-bot bypass](/engineering/no-anti-bot-bypass.md).
- **Необратимое делает человек** — [action tiers](/engineering/action-tiers.md).

# Related

- Тиры действий: [action tiers](/engineering/action-tiers.md)
- Человек в цикле: [attended mode](/engineering/attended-mode.md)
- Модели и промпты: [LLM canon](/engineering/llm-canon.md)
- Полный дизайн (25 доков): [design docs](/references/design-docs.md)
