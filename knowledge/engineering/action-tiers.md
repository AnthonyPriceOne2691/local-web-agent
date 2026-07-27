---
type: Policy
title: Тиры действий — автономность × обратимость
description: Агент автономен на обратимом, спрашивает на значимом и НЕ нажимает необратимое — эту кнопку жмёт человек.
status: stable
tags: [safety, actions, hitl]
generated:
  by: claude-code/fable-5
  at: 2026-07-27T00:00:00Z
verified:
  by: human:anthony
  at: 2026-07-20T00:00:00Z
resource: docs/25-action-framework.md
implementation:
  - backend/app/orchestrator/interaction.py
  - backend/app/contracts/rules/navigation.py
  - data/contracts/crawl.contract.yaml
---

# Purpose

Опасность не в автономности, а в её сочетании с **необратимостью**. Поэтому
действия разделены по двум осям, и политика подтверждения зависит от тира.

# Canonical rules

| Tier | Класс | Кто исполняет | Примеры |
|---|---|---|---|
| **0** | sink / отдача наружу | автономно; облако — по явному запросу (A-H4) | Google Docs, локальный файл |
| **1** | безопасная интеракция | **автономно** | «показать ещё», таб, пагинация |
| **2** | значимое (пишет) | агент, но **после подтверждения человека в чате** | submit формы, login |
| **3** | необратимое | **человек нажимает сам** в видимом браузере; агент только готовит | купить, оплатить, удалить, опубликовать |

- **Tier 2 ≠ Tier 3.** На Tier 2 человек подтверждает в чате, жмёт агент. На
  Tier 3 агент не жмёт **никогда**: подтверждение в чате — слишком дешёвый клик
  для необратимого, финальное действие делает человек на самой странице.
- **Пароли агент не хранит и не видит.** При login-стене человек вводит их сам в
  видимом браузере ([attended mode](/engineering/attended-mode.md)); в поля типа
  `password` агент не пишет никогда (I-H11).
- **Unattended + необратимое = отказ.** Без человека в цикле destructive-клик
  отклоняется контрактом (I-H12), а не «выполняется на свой риск».
- Признак destructive — словарь стемов в label кнопки (`destructive_signals` в
  `data/contracts/crawl.contract.yaml`). Ошибаемся **в безопасную сторону**:
  ложная пауза приемлема, ложный пропуск — нет. «Отправить» без контекста заказа
  остаётся Tier 2 (иначе каждая контакт-форма требовала бы человека).

# Enforcement

| Инвариант | Контракт | Где |
|---|---|---|
| click только по существующему не-submit элементу | I-H10 | `contracts/rules/navigation.py` |
| fill только в текстовые поля, никогда password | I-H11 | там же |
| destructive click → handoff/reject | I-H12 | там же, проверяется **до** I-H10 |
| Layer 2 действие tier ≥ 2 не исполняется само | A-H2/A-H3 | `research/runner.py` |

# Related

- Механика паузы: [attended mode](/engineering/attended-mode.md)
- Реестр действий Layer 2: [action registry](/engineering/action-registry.md)
- Полный дизайн и история решений: `docs/25-action-framework.md`,
  контракты — `docs/13-behavioral-contracts.md`
