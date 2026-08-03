"""Блокировка сторонней аналитики в браузере агента (doc 03 § Трекеры, doc 26 § T-3a-1).

Два повода, оба измеримые:

* **приватность** — обход чужих сайтов не должен отмечаться в их аналитике от имени
  этой машины; проект заявляет privacy-first, а до этой правки исправно исполнял чужие
  beacon-скрипты на каждой странице;
* **скорость** — зависший трекер держит DOMContentLoaded до сетевого таймаута: в
  испытании T-3a это стоило 2 сайтов из 3 и 46 % времени сессии.

Это **не** обход anti-bot: отпечаток не подделывается, защита не обманывается,
блокируется только телеметрия, к содержанию страницы не относящаяся.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import yaml


class TrackerBlocklist:
    """Список хостов трекеров + решение «блокировать ли этот URL».

    Совпадение по суффиксу домена (`umami.is` покрывает `cloud.umami.is`), потому что
    трекеры живут на поддоменах; часть записей — с началом пути (`facebook.com/tr`),
    так как один и тот же хост отдаёт и нужное, и пиксель.
    """

    def __init__(self, entries: list[str]) -> None:
        self._hosts: list[str] = []
        self._host_paths: list[tuple[str, str]] = []
        for raw in entries:
            entry = raw.strip().lower().lstrip(".")
            if not entry:
                continue
            if "/" in entry:
                host, _, path = entry.partition("/")
                self._host_paths.append((host, "/" + path))
            else:
                self._hosts.append(entry)

    @classmethod
    def load(cls, data_dir: Path) -> TrackerBlocklist:
        path = data_dir / "browser" / "tracker_hosts.yaml"
        if not path.exists():
            return cls([])
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(list(raw.get("hosts") or []))

    @property
    def size(self) -> int:
        return len(self._hosts) + len(self._host_paths)

    def blocks(self, url: str, *, page_host: str = "") -> bool:
        """Блокируется ли запрос. Хост самой страницы не блокируется никогда.

        Последнее — предохранитель: если хост сайта под обходом попал в список (а
        `plausible.io` и `matomo.cloud` вполне могут быть целью исследования), обход
        этого сайта не должен ломаться собственной блокировкой.
        """
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host:
            return False
        if page_host and _same_host(host, page_host.lower()):
            return False
        path = parts.path or "/"
        if any(_same_host(host, blocked) for blocked in self._hosts):
            return True
        return any(_same_host(host, h) and path.startswith(p) for h, p in self._host_paths)


def _same_host(host: str, blocked: str) -> bool:
    """Совпадение хоста целиком или как поддомена — не подстрокой.

    Подстрочное сравнение матчило бы `notgoogle-analytics.com`, поэтому граница
    проверяется точкой.
    """
    return host == blocked or host.endswith("." + blocked)
