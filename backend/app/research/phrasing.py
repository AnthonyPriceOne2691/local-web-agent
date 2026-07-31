"""Формулировки для сообщений, которые видит пользователь (doc 17 § Wording).

Зеркало фронтового `copy.ts`: там переводятся значения (статусы, шаги), здесь —
текст, который сочиняет бэкенд (заметки о шагах, ответы в чат). Держим в одном
месте по той же причине: строка, написанная по месту, назавтра уезжает в интерфейс
внутренним словарём проекта — `crawl_site`, `Tier 2`, `max_sites`.

Язык — английский (решение владельца, doc 17).
"""

from __future__ import annotations

from urllib.parse import urlparse

# Человеческие имена действий планнера. Ключи — внутренние (реестр действий),
# значения — то, что уместно прочитать в чате.
_ACTION_NAMES = {
    "crawl_site": "read a site",
    "compare_results": "compare the sites",
    "get_run_result": "look again at what a site said",
    "list_session_runs": "list the sites from this chat",
    "export_gdocs": "copy the write-up to Google Docs",
    "export_file": "save the write-up to a file",
}


def site_name(url: str) -> str:
    """Хост без `www` — то, чем человек называет сайт (не полный URL)."""
    host = urlparse(url).netloc or url
    return host.removeprefix("www.")


def action_name(tool: str) -> str:
    """Имя действия для чата; неизвестное — из snake_case в обычные слова."""
    return _ACTION_NAMES.get(tool, tool.replace("_", " "))


# Почему сайт не попал в сравнение. Раньше строка начиналась со статуса кода
# (`failed: …`, `blocked: …`) — читателю это ничего не говорит.
_EXCLUSION = {
    "failed": "couldn't be read",
    "blocked": "blocked us",
    "not_found": "had nothing on the topic",
    "partial": "was only partly readable",
    "canceled": "was stopped",
}


def exclusion_reason(status: str, blocked_by: str | None, error: str | None) -> str:
    """Одно предложение: что случилось с сайтом и, если известно, из-за чего."""
    what = _EXCLUSION.get(status, status.replace("_", " "))
    detail = blocked_by or error
    return f"{what} ({detail})" if detail else what
