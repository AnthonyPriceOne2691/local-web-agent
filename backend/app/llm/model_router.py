"""Какая модель принимает решение навигатора: лёгкая или тяжёлая (doc 16).

Замер 2026-07-31 на одном коде (`qwen3:8b` vs `qwen3:14b`, фикстуры 8901/8904/8908):

| Класс решения | Лёгкая | Тяжёлая |
|---|---|---|
| локально по DOM (что заполнить/нажать) | nav 9.4 s, решения те же | nav 16.8 s |
| одна очевидная ссылка | nav 10.1 s, путь тот же | nav 22.1 s |
| выбор статьи по смыслу | 3 из 3 прогонов: G-H2 + хоп в 404 | 0 violations в 2 из 2 |

Отсюда правило: лёгкая модель отвечает только за решения, замкнутые на текущей
странице. Выбор ссылки, `extract_now` vs `navigate` и синтез — тяжёлая.
`pick_nav_model` **чистая**: ни сети, ни LLM, ни файлов — словарь ключевых слов
приходит аргументом, читает его `NavRouting` из `data/navigation/`.
"""

from __future__ import annotations

import yaml

from app.config import Settings
from app.schemas.snapshot import PageSnapshot

# Действия, после которых агент продолжает работать с той же страницей: значит
# следующее решение тоже про её DOM (дозаполнить форму, нажать кнопку).
DOM_ACTIONS = frozenset({"fill", "fill_form", "click"})


def task_asks_action(task: str, action_keywords: tuple[str, ...]) -> bool:
    """Просит ли задача действия на странице (casefold substring, RU+EN)."""
    text = task.casefold()
    return any(kw in text for kw in action_keywords)


def pick_nav_model(
    *,
    heavy: str,
    light: str,
    task: str,
    snapshot: PageSnapshot,
    last_dom_url: str | None,
    action_keywords: tuple[str, ...],
    replanning: bool = False,
) -> str:
    """Модель для следующего решения навигатора.

    `light` пустой → лёгкая модель не настроена, всё на тяжёлой (поведение до
    поставки `nav-model-split`). `replanning=True` → предыдущее решение поймал
    hard-контракт, и повтор идёт на тяжёлой: замер показал, что лёгкая ошибается
    именно на смысловых решениях, а replan — сигнал такой ошибки.
    """
    if not light:
        return heavy
    if replanning:  # эскалация: лёгкая уже ошиблась на этом шаге
        return heavy
    if not any(not el.disabled for el in snapshot.interactive_elements):
        return heavy  # локально решать нечего → это выбор ссылки
    if last_dom_url == snapshot.url:
        return light  # мы посреди интеракции на этой же странице
    return light if task_asks_action(task, action_keywords) else heavy


def last_dom_action_url(steps: list[tuple[str, str, str]]) -> str | None:
    """URL последнего DOM-действия из (state, action, url) или None.

    Принимает кортежи, а не `CrawlStep`: роутер живёт в `app.llm` и не должен
    зависеть от схемы run'а — направление слоёв ловит import-linter.
    """
    for state, action, url in reversed(steps):
        if state != "ACT":
            continue
        if action in DOM_ACTIONS:
            return url
        if action == "navigate":
            return None  # ушли со страницы — интеракция кончилась
    return None


class NavRouting:
    """Словарь маршрутизации + пара моделей (данные из `data/navigation/`)."""

    def __init__(self, action_keywords: tuple[str, ...], heavy: str, light: str):
        self.action_keywords = action_keywords
        self.heavy = heavy
        self.light = light

    @classmethod
    def load(cls, settings: Settings) -> NavRouting:
        path = settings.navigation_dir / "nav_model_routing.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        words = data.get("action_keywords") or []
        return cls(
            tuple(str(w).casefold() for w in words),
            heavy=settings.nav_model,
            light=settings.nav_light_model,
        )

    def pick(
        self,
        *,
        task: str,
        snapshot: PageSnapshot,
        steps: list[tuple[str, str, str]],
        replanning: bool = False,
    ) -> str:
        return pick_nav_model(
            heavy=self.heavy,
            light=self.light,
            task=task,
            snapshot=snapshot,
            last_dom_url=last_dom_action_url(steps),
            action_keywords=self.action_keywords,
            replanning=replanning,
        )

    def expects_human_action(self, task: str) -> bool:
        """Ожидается ли участие человека на странице по формулировке задачи.

        Тот же словарь, что и для выбора модели: задача, просящая заполнить или
        нажать, почти наверняка дойдёт до submit или Tier 3 handoff. Для таких задач
        окно браузера открывается сразу — перезапуск в видимый режим потерял бы
        заполненную форму (doc 24 § Видимость окна).
        """
        return task_asks_action(task, self.action_keywords)

    def first_step_model(self, task: str) -> str:
        """Кого греть до открытия браузера: первый шаг решает форму или ссылку.

        На первом шаге истории ещё нет, поэтому решает только формулировка задачи;
        если она про действие — грузим лёгкую, иначе тяжёлую.
        """
        if self.light and task_asks_action(task, self.action_keywords):
            return self.light
        return self.heavy
