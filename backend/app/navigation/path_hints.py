"""Загрузка data/navigation/path_hints.yaml (doc 21). Данные, не код."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_INTENT_CATEGORIES = ("contact", "contact_legal", "about", "pricing", "careers", "docs", "commercial", "blog")


class PathHints:
    def __init__(self, data: dict[str, Any]):
        self._data = data or {}

    @classmethod
    def load(cls, navigation_dir: Path) -> PathHints:
        path = navigation_dir / "path_hints.yaml"
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def slugs_for(self, intent: str) -> list[str]:
        if intent == "content_search":
            return [str(s) for s in self._data.get("blog", [])]
        return [str(s) for s in self._data.get(intent, [])] if intent in _INTENT_CATEGORIES else []

    @property
    def legal_slugs(self) -> list[str]:
        return [str(s) for s in self._data.get("contact_legal", [])]

    @property
    def intent_keywords(self) -> dict[str, list[str]]:
        return {k: [str(x) for x in v] for k, v in (self._data.get("intent_keywords") or {}).items()}

    @property
    def learn_markers(self) -> tuple[str, ...]:
        """Как называются обучающие разделы (`wiki`, `school`, `academy`, `гайд`). Признак
        жанра, который и просит задача «как делать X» (doc 21 § Обучающее против промо)."""
        return tuple(str(w).casefold() for w in self._data.get("learn_markers") or ())

    @property
    def promo_markers(self) -> tuple[str, ...]:
        """Бонусы, фрибеты, розыгрыши: тема совпадает, а ответа на «как делать» там нет."""
        return tuple(str(w).casefold() for w in self._data.get("promo_markers") or ())

    @property
    def task_stopwords(self) -> frozenset[str]:
        """Служебные слова задачи — не сигнал темы. Один словарь на sitemap-фильтр и
        оценку ссылок: раньше он жил в коде `sitemap.py`, и второй потребитель завёл бы
        копию. frozenset — чтобы результат можно было кэшировать по задаче."""
        return frozenset(str(w).casefold() for w in self._data.get("task_stopwords") or ())
