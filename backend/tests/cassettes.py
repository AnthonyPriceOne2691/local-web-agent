"""Кассеты с хэшем промпта в КЛЮЧЕ — двойник, чей ответ зависит от промпта.

⚠ **Зачем это заведено.** Прежний двойник (`FakeOllama`) брал ответ из очереди:
он записывал `kwargs`, но отдавал следующий скриптованный ответ независимо от
того, что пришло. Значит выход НЕ МОГ зависеть от текста промпта **по
построению**, и сьют охранял МЕСТО промпта, а не его содержание.

Замер, из которого модуль родился (ось 5, проба 2026-08-18): удаление ключевой
инструкции из промпта заметили **0 механик из 4**, при том что переименование
того же файла роняет 63 теста, а поломка загрузчика — те же 63. Обратный прогон
доказывал, что стенд умеет краснеть; краснеть он умел на ВСЁМ, кроме содержания.

Здесь ответ ищется по ключу, в который входит `sha256` промпта. Промпт изменился
→ ключа нет → тест падает ГРОМКО и с адресом: имя файла промпт-стора и хэш.
Это и есть слой 3 пятой оси: без него порча промпта невозможна к обнаружению.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

#: Промпт-стор проекта. Нужен ТОЛЬКО для диагностики промаха — назвать файл,
#: который изменился. На поиск ответа он не влияет: ключ считается от того, что
#: реально ушло в модель, а не от того, что лежит на диске. Иначе двойник судил
#: бы диск вместо вызова — ровно та подмена, из-за которой прежний не работал.
PROMPTS = Path(__file__).resolve().parents[2] / "data" / "prompts"
CASSETTES = Path(__file__).resolve().parent / "cassettes"
RECORD = os.environ.get("RECORD_CASSETTES") == "1"


def _short(digest: bytes) -> str:
    """Короткий адрес содержимого в base32, а НЕ в hex.

    ⚠ Выбор представления, а не косметика. Hex-строка высокой энтропии — это
    ровно то, что `detect-secrets` обязан считать утечкой ключа, и на первом же
    коммите кассеты он и покраснел (пять срабатываний на одном файле). Ослабить
    гейт исключением каталога было бы дороже находки: в записанном ответе модели
    токен оказаться МОЖЕТ, и тогда исключение спрячет настоящую утечку. base32
    даёт ту же стойкость к коллизии и не притворяется ключом.
    """
    return base64.b32encode(digest).decode("ascii").rstrip("=").lower()[:12]


def key_for(model: str, system: str, user: str) -> str:
    """Ключ кассеты. Разделитель обязателен: без него склейка полей даёт
    коллизию на паре, где конец одного равен началу другого."""
    h = hashlib.sha256()
    for part in (model, system, user):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return _short(h.digest())


def store_hashes() -> dict[str, str]:
    """`{путь: sha12}` по всему промпт-стору — снимок на момент прогона."""
    out = {}
    if PROMPTS.is_dir():
        for f in sorted(PROMPTS.rglob("*")):
            if f.is_file():
                rel = str(f.relative_to(PROMPTS))
                out[rel] = _short(hashlib.sha256(f.read_bytes()).digest())
    return out


def store_drift(recorded: dict[str, str]) -> list[str]:
    """Чем стор отличается от записанного — ИМЕНАМИ файлов.

    ⚠ Ради этого функция и существует. Первая редакция диагноза искала файл,
    ТЕЛО которого равно отправленному системному промпту, — и на живом случае
    не нашла ничего: планировщик СОБИРАЕТ system из `meta_planner_system.txt` и
    тел `tools/*.txt`. Сообщение честно говорило «промпт изменился», но адреса
    не давало, то есть было советом без исполнителя — ровно тем классом, что
    контур закрывал днём раньше. Снимок стора в кассете отвечает адресом.
    """
    now = store_hashes()
    out = [f"{k}: изменён" for k in sorted(set(recorded) & set(now)) if recorded[k] != now[k]]
    out += [f"{k}: УДАЛЁН" for k in sorted(set(recorded) - set(now))]
    out += [f"{k}: НОВЫЙ" for k in sorted(set(now) - set(recorded))]
    return out


class CassetteOllama:
    """Двойник модели, у которого ответ ЗАВИСИТ от промпта.

    `replies` — очередь на запись новых кассет (`RECORD_CASSETTES=1`) и ТОЛЬКО
    на неё. В обычном прогоне очередь не трогается: если бы она была фолбэком
    на промах, промах перестал бы быть красным — и двойник вернулся бы к тому
    поведению, ради отказа от которого написан.
    """

    def __init__(self, name: str, replies: list[str | dict] | None = None):
        self.name = name
        self._replies = list(replies or [])
        self.calls: list[dict] = []
        self.unloaded: list[str] = []
        self.warmed: list[str] = []
        self._path = CASSETTES / f"{name}.json"
        self._tape: dict[str, dict] = {}
        self._prompts: dict[str, str] = {}
        if self._path.is_file():
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._prompts = raw.get("_prompts", {})
            self._tape = raw.get("entries", {})

    async def chat(self, **kwargs) -> tuple[str, dict]:
        self.calls.append(kwargs)
        model = str(kwargs.get("model", ""))
        system = str(kwargs.get("system", ""))
        user = str(kwargs.get("user", ""))
        key = key_for(model, system, user)
        entry = self._tape.get(key)
        if entry is None:
            if RECORD:
                return self._record(key, model, system, user)
            drift = store_drift(self._prompts)
            where = (
                "\n".join(f"    {d}" for d in drift)
                if drift
                else "    стор совпадает со снимком — промпт собран в коде либо изменился шаблон user"
            )
            raise AssertionError(
                f"кассеты {self.name}[{key}] нет — промпт изменился.\n"
                f"  что разошлось с записанным снимком промпт-стора:\n{where}\n"
                f"  модель: {model}\n"
                f"  Если правка промпта НАМЕРЕННАЯ, перезапиши кассеты:\n"
                f"    RECORD_CASSETTES=1 python -m pytest {self._hint()}\n"
                f"  и прочитай дифф кассет ГЛАЗАМИ: изменившийся ответ — это\n"
                f"  изменившееся поведение, а не механическая правка снимка."
            )
        reply = entry["reply"]
        content = json.dumps(reply, ensure_ascii=False) if isinstance(reply, (dict, list)) else str(reply)
        return content, entry.get("stats", {"eval_count": 42})

    def _hint(self) -> str:
        return f"backend/tests -k {self.name}"

    def _record(self, key: str, model: str, system: str, user: str) -> tuple[str, dict]:
        reply = self._replies.pop(0) if self._replies else {"action": "stop", "reasoning": "out of replies"}
        self._tape[key] = {"model": model, "reply": reply, "stats": {"eval_count": 42}}
        self._prompts = store_hashes()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"_prompts": self._prompts, "entries": self._tape},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        content = json.dumps(reply, ensure_ascii=False) if isinstance(reply, (dict, list)) else str(reply)
        return content, {"eval_count": 42}

    # --- остальная поверхность клиента: та же, что у FakeOllama --------------
    async def warmup(self, model: str, keep_alive: str | int = "10m") -> None:
        self.warmed.append(model)

    async def unload(self, model: str) -> None:
        self.unloaded.append(model)

    async def unload_many(self, *models: str) -> None:
        for model in dict.fromkeys(m for m in models if m):
            await self.unload(model)

    async def health(self) -> dict:
        return {"reachable": True, "version": "0.31.1", "models": ["fake"]}

    async def aclose(self) -> None:  # pragma: no cover - trivial
        pass
