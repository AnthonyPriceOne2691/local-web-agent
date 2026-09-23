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

    def exclusion_reason(
        self,
        status: str,
        blocked_by: str | None,
        error: str | None,
        *,
        stage: str = "",
        pages_read: int | None = None,
    ) -> str:
        """Одно предложение: что случилось с сайтом и, если известно, из-за чего.

        Стадия и число прочитанных страниц нужны, чтобы не врать про виновника. Живой
        прогон T-3h: `legalbet.ru` прочитал **4 страницы**, включая целевую статью, и упал
        на синтезе таймаутом **локальной модели** — а человеку было сказано «не удалось
        прочитать — сайт не ответил за отведённое время». Неверно дважды.

        `pages_read=None` — «неизвестно», и тогда формулировка прежняя. Ноль и неизвестность
        различаются сознательно: с общим дефолтом `0` приписка «ни одна страница не
        открылась» полезла бы в каждое сообщение, включая те, где страницы читались.
        """
        table = (self._table.get("exclusion") or {}).get(self.lang) or {}
        what = table.get(status) or status.replace("_", " ")
        detail = self.humanize_detail(blocked_by or error)
        if stage == "SYNTHESIZE" and pages_read:
            low = (error or "").casefold()
            cause = self._technical("llm_timeout") if "timeout" in low else ""
            cause = cause or detail or self._technical("llm_failed")
            return self.say("read_but_no_answer", pages=pages_read, detail=cause)
        if status == "failed" and pages_read == 0 and not blocked_by:
            nothing = self.say("no_page_opened")
            return f"{what} — {nothing}" + (f", {detail}" if detail else "")
        return f"{what} — {detail}" if detail else what

    def _technical(self, key: str) -> str:
        """Причина из таблицы `technical` на языке запроса. Отдельно от `say`: там блок
        языка, а причины лежат своим словарём, и путать их — источник KeyError."""
        table = (self._table.get("technical") or {}).get(self.lang) or {}
        return str(table.get(key) or "")

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


_SENTENCE_END = re.compile(r"[.!?…]+(?=\s)")
_OPENERS = "\"'«“‘(["


def clip_at_sentence(text: str, limit: int) -> str:
    """Текст не длиннее `limit`, обрезанный по концу предложения, а не посреди слова.

    Дефект живой сессии: проза сравнения уходила в чат срезом `narrative[:600]`, и
    ответ заканчивался на «King Arthur's artic». Конец предложения — знак, за которым
    после пробела идёт заглавная буква: так «approx. 964» и «e.g. the» не рвут фразу.
    Если законченного предложения нет хотя бы на треть лимита, режем между словами
    и ставим многоточие — обрывок слова хуже честного «…».
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = 0
    for m in _SENTENCE_END.finditer(text, 0, limit + 1):
        if m.end() > limit:
            break
        rest = text[m.end() :].lstrip().lstrip(_OPENERS)
        if rest[:1].isupper():
            cut = m.end()
    if cut >= limit // 3:
        return text[:cut]
    head = text[: limit - 1]  # место под «…»
    if not text[limit - 1].isspace():  # граница внутри слова — слово отбрасываем целиком
        parts = head.rsplit(None, 1)
        head = parts[0] if len(parts) > 1 else head
    return head.rstrip(",;:—–- ") + "…"


def site_name(url: str) -> str:
    """Хост без `www` — то, чем человек называет сайт (не полный URL)."""
    host = urlparse(url).netloc or url
    return host.removeprefix("www.")


def action_name(tool: str) -> str:
    """Имя действия для чата; неизвестное — из snake_case в обычные слова."""
    return _ACTION_NAMES.get(tool, tool.replace("_", " "))
