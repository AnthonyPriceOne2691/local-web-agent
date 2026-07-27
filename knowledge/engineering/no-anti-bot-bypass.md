---
type: Policy
title: Обход anti-bot защиты запрещён навсегда
description: Fingerprint-спуфинг, undetected-браузеры и captcha-солверы вне scope; проверку проходит человек в attended-режиме.
status: stable
tags: [safety, ethics, scope]
generated:
  by: claude-code/fable-5
  at: 2026-07-27T00:00:00Z
verified:
  by: human:anthony
  at: 2026-07-20T00:00:00Z
resource: docs/24-research-chat-agent.md
implementation:
  - backend/app/observer/blockers.py
---

# Purpose

Решение обсуждено и закрыто (2026-07-20): агент **не притворяется человеком**
перед защитой. Это не техническое ограничение, а граница продукта — поэтому
записано как канон, а не как «пока не сделали».

# Canonical rules

- **Вне scope навсегда:** undetected-драйверы, camoufox и подобные, спуфинг
  fingerprint/User-Agent ради обхода детекта, captcha-solver сервисы.
- Обнаружен challenge → агент честно ставит паузу (attended) или помечает run
  `blocked`. Никаких попыток «протиснуться».
- Проверку проходит **человек**, один раз на домен, пока жив cookie
  (`persist_session`) — [attended mode](/engineering/attended-mode.md).
- `robots.txt` соблюдается по умолчанию.

# Почему именно так

| Аргумент | Суть |
|---|---|
| Честность | Обход = враньё защите сайта о том, кто ты |
| Privacy-first | Solver-сервисы и облачные обходы ломают принцип «ничего не уходит с машины» |
| Не масштабируется | На сотнях сайтов обход всё равно не спасает; ~80% дают нужные клики и без него |
| Ценность в другом | «Магия» проекта — что агент *думает* при анализе, а не что он пронырлив |

# Related

- Что агент делает вместо обхода: [action tiers](/engineering/action-tiers.md)
- Детект блокеров и thin-guard: `docs/13-behavioral-contracts.md`
