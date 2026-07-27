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
