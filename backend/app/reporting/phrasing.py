"""Формулировки для сообщений, которые видит пользователь (doc 17 § Wording).

Зеркало фронтового `copy.ts`: там переводятся значения (статусы, шаги), здесь —
текст, который сочиняет бэкенд (заметки о шагах, ответы в чат). Держим в одном
месте по той же причине: строка, написанная по месту, назавтра уезжает в интерфейс
внутренним словарём проекта — `crawl_site`, `Tier 2`, `max_sites`.

**Язык ответа — язык запроса** (решение владельца, doc 17 v0.7): русский вопрос
получает русский ответ, английский — английский. Это касается и прозы модели, и строк
из этого модуля: смешение как раз и было дефектом («How they scored:» английской
строкой над русским текстом). Подписи самого интерфейса (кнопки, табы, заголовки
карточек, статусы) остаются английскими всегда — это мебель, а не ответ.

Сами фразы живут в `data/phrasing/chat_phrases.yaml`: словарь в данных, а не в коде
(doc 18 § DRY) — иначе добавление языка означает правку кода.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

# Человеческие имена действий планнера. Ключи — внутренние (реестр действий),
# значения — то, что уместно прочитать в чате. Имена действий остаются английскими:
# они появляются в заметках рядом с подписями интерфейса.
_ACTION_NAMES = {
    "crawl_site": "read a site",
    "compare_results": "compare the sites",
    "get_run_result": "look again at what a site said",
    "list_session_runs": "list the sites from this chat",
    "export_gdocs": "copy the write-up to Google Docs",
    "export_file": "save the write-up to a file",
}

_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")

# Ключи технических причин ищутся в тексте исключения. Порядок важен: `timeout`
# проверяется раньше общего `connection`.
_TECHNICAL_MATCH = (
    ("timeout", "timeout"),
    ("err_timed_out", "timeout"),
    ("err_name_not_resolved", "dns"),
    ("err_connection", "connection"),
    ("net::", "connection"),
    ("targetclosed", "browser_closed"),
    ("robots", "robots"),
    ("innertext", "never_loaded"),
    ("execution context", "kept_reloading"),
)
_MAX_DETAIL_CHARS = 90


def task_language(task: str) -> str:
    """Язык запроса: `ru`, если в нём есть кириллица, иначе `en`.

    Определяется по самому тексту, без обращения к модели: решение должно быть
    дешёвым и одинаковым при каждом прогоне. Смешанный запрос («найди pricing page»)
    считается русским — по языку, на котором человек обращается.
    """
    return "ru" if _CYRILLIC.search(task or "") else "en"


class Phrases:
    """Фразы одного языка. Загружается один раз, дальше только подстановка."""

    def __init__(self, table: dict[str, Any], lang: str) -> None:
        self._table = table
        self.lang = lang if lang in table else "en"

    @classmethod
    def load(cls, data_dir: Path, task: str) -> Phrases:
        path = data_dir / "phrasing" / "chat_phrases.yaml"
        table: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(table, task_language(task))

    def say(self, key: str, **kwargs: Any) -> str:
        """Фраза по ключу. Отсутствующий ключ — ошибка конфигурации, а не тихий пропуск."""
        block = self._table.get(self.lang) or {}
        template = block.get(key) or (self._table.get("en") or {}).get(key)
        if template is None:
            raise KeyError(f"chat_phrases.yaml: нет фразы '{key}'")
        return str(template).format(**kwargs)

    def exclusion_reason(self, status: str, blocked_by: str | None, error: str | None) -> str:
        """Одно предложение: что случилось с сайтом и, если известно, из-за чего."""
        table = (self._table.get("exclusion") or {}).get(self.lang) or {}
        what = table.get(status) or status.replace("_", " ")
        detail = self.humanize_detail(blocked_by or error)
        return f"{what} — {detail}" if detail else what

    def humanize_detail(self, detail: str | None) -> str:
        """Короткая человеческая причина или пусто. Стеки и внутренние типы не проходят.

        Дефект живого прогона: `Page.evaluate: TypeError: Cannot read properties of null
        (reading 'innerText') at eval (…) at UtilityScript.evaluate (…)` уезжал в чат
        целиком. Пользователю нужно знать, что сайт не прочитался, а не где упал наш JS.
        """
        if not detail:
            return ""
        low = detail.casefold()
        table = (self._table.get("technical") or {}).get(self.lang) or {}
        for needle, key in _TECHNICAL_MATCH:
            if needle in low:
                return str(table.get(key) or "")
        first_line = detail.strip().splitlines()[0].strip()
        looks_technical = (
            "error:" in low[:60]
            or low.startswith(("at ", "traceback"))
            or "exception" in low[:60]
            or ("/" in first_line and first_line.endswith((")", ";")))
        )
        if looks_technical or len(first_line) > _MAX_DETAIL_CHARS:
            return ""
        return first_line


def site_name(url: str) -> str:
    """Хост без `www` — то, чем человек называет сайт (не полный URL)."""
    host = urlparse(url).netloc or url
    return host.removeprefix("www.")


def action_name(tool: str) -> str:
    """Имя действия для чата; неизвестное — из snake_case в обычные слова."""
    return _ACTION_NAMES.get(tool, tool.replace("_", " "))
