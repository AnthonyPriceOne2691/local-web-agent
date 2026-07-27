---
type: Design
title: Attended-режим — человек в цикле
description: Одна механика паузы (waiting_user → resume) обслуживает anti-bot проверку, логин, подтверждение submit и handoff необратимого шага.
status: stable
tags: [hitl, safety, attended]
generated:
  by: claude-code/fable-5
  at: 2026-07-27T00:00:00Z
resource: docs/24-research-chat-agent.md
implementation:
  - backend/app/orchestrator/attended.py
---

# Purpose

Некоторые шаги агент не может (или не должен) делать сам: anti-bot проверка,
логин, отправка формы, необратимое действие. Вместо обхода защиты или слепого
клика агент **останавливается и передаёт управление человеку**, затем продолжает
с того же места.

# Canonical rules

- Пауза = статус run `waiting_user` + `metadata.challenge` (`kind`, `url`,
  опц. `action`). Браузер при `attended` запускается видимым (`headless=False`).
- Снятие паузы — только человеком: `POST /runs/{id}/resume` или
  `POST /sessions/{id}/resume` (в Chat UI — кнопка на карточке).
- После resume читаем **уже открытую** страницу (`reobserve_in_place`), без
  повторного `goto`: повторная навигация спровоцировала бы новую проверку и
  потеряла бы результат действия человека.
- Четыре вида паузы — одна машинерия, разные `kind`:

| `kind` | Что делает человек | Дальше |
|---|---|---|
| `captcha` | проходит проверку | агент продолжает обход |
| `login_wall` | логинится сам (пароль остаётся у него) | агент читает контент под логином |
| `confirm_submit` | подтверждает в чате | **агент** нажимает submit (Tier 2) |
| `handoff` | **нажимает кнопку сам** в браузере | агент только фиксирует исход (Tier 3) |

- Таймаут ожидания — `attended_wait_timeout_s` (по умолчанию 300 с); истёк →
  действие не выполняется, run останавливается честно.
- `waiting_user` **держит глобальный лок** (D-12): браузер открыт, второй crawl
  не стартует; после рестарта зависший run помечается failed.
- Повторный вход не нужен: `persist_session` хранит cookie сессии по хосту
  (`runs/profiles/<host>.json`, gitignored). Пароли не хранятся — только cookie.

# Границы

Это **не** обход детекта: cookie привязан к IP+браузеру и живёт ограниченно.
Снимается рутина навигации, а не сам факт проверки —
[no anti-bot bypass](/engineering/no-anti-bot-bypass.md).

# Related

- Что требует какой паузы: [action tiers](/engineering/action-tiers.md)
- Протокол SSE и ручки: `docs/15-api-cli-spec.md`
