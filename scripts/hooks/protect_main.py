#!/usr/bin/env python3
"""protect-main hook (Delivery §10.1 / A.11): блокирует опасные git-команды.

PreToolUse-хук для Bash: читает JSON события со stdin, смотрит на команду.
Exit 2 = блок (stderr уходит агенту), exit 0 = разрешено.

Закрывает то, что на бесплатном тарифе не закрыто серверной защитой ветки
(см. delivery/STACK-ACCEPTANCE.md § Остатки): force-push в main и удаление
основной ветки. Не заменяет branch protection — поднимает цену случайности.

Проверка идёт по **отдельным командам** и по **отдельным аргументам**, а не по
всей строке: раньше правила матчились подстрокой, поэтому признаки складывались
из разных мест и хук блокировал безобидное. Ложное срабатывание вреднее пропуска
— обойти его стоит ноль (разбить составную команду на две), после чего хук
перестают воспринимать серьёзно и там, где он прав.
"""

from __future__ import annotations

import json
import re
import sys

PROTECTED = ("main", "master")

# Разделители команд в одной строке. Из-за проверки по всей строке `-f` из
# `pkill -f "uvicorn app.main:app"` складывался со словом `main` из соседней
# команды, и пуш ветки читался как переписывание истории.
SEPARATORS = re.compile(r"(?:&&|\|\||;|\||\n)")

GIT_PUSH = re.compile(r"\bgit\b.{0,80}?\bpush\b", re.IGNORECASE | re.DOTALL)
GIT_RESET_HARD = re.compile(r"\bgit\b.{0,40}?\breset\b.*--hard\b", re.IGNORECASE | re.DOTALL)
FORCE_FLAG = re.compile(r"(?:--force\b|--force-with-lease\b|(?<!\w)-f\b)", re.IGNORECASE)
DELETE_FLAG = re.compile(r"(?:--delete\b|(?<!\w)-d\b)", re.IGNORECASE)


def segments(command: str) -> list[str]:
    """Составная команда → отдельные команды.

    Разделение эвристическое: кавычки, подстановки и here-doc не разбираются.
    Ошибается оно в **безопасную** сторону — нераспознанный разделитель (например
    одиночный `&`) оставляет два фрагмента одним сегментом, то есть правило скорее
    заблокирует, чем пропустит. Опасная команда целиком живёт в одном сегменте,
    поэтому дробление её не прячет.
    """
    return [seg.strip() for seg in SEPARATORS.split(command) if seg.strip()]


def _names_protected_branch(token: str) -> bool:
    """Указывает ли аргумент на main/master (сам, с remote или в refspec).

    Смотрим на **весь токен**, а не на подстроку: `\\bmain\\b` совпадало внутри
    имени ветки (`fix/protect-main-segments`), из-за чего force-push своей же
    ветки блокировался. Ветка вида `feature/main` будет принята за защищённую —
    это осознанная ошибка в безопасную сторону.
    """
    for part in token.lstrip("+").split(":"):
        name = part.strip().rstrip("/").lower()
        if name in PROTECTED or any(name.endswith(f"/{p}") for p in PROTECTED):
            return True
    return False


def _names_remote_protected(token: str) -> bool:
    """Ссылка на remote-tracking main/master (`origin/main`, `refs/heads/master`)."""
    name = token.strip().lower()
    return any(name.endswith(f"/{p}") for p in PROTECTED)


def _force_push_to_protected(segment: str) -> bool:
    if not (GIT_PUSH.search(segment) and FORCE_FLAG.search(segment)):
        return False
    return any(_names_protected_branch(t) for t in segment.split())


def _delete_protected(segment: str) -> bool:
    if not GIT_PUSH.search(segment):
        return False
    tokens = segment.split()
    # `--delete main` или refspec с пустой левой частью (`:main` = удалить ветку).
    signalled = bool(DELETE_FLAG.search(segment)) or any(t.startswith(":") for t in tokens)
    return signalled and any(_names_protected_branch(t) for t in tokens)


def _hard_reset_to_remote_protected(segment: str) -> bool:
    if not GIT_RESET_HARD.search(segment):
        return False
    # Локальный `reset --hard main` законен (откат рабочего дерева); опасен именно
    # сброс на remote-состояние — он молча уничтожает локальную работу.
    return any(_names_remote_protected(t) for t in segment.split())


RULES = (
    (
        _force_push_to_protected,
        "force-push в main/master запрещён (Delivery §4.2). "
        "Нужен переписанный main — это HITL-решение человека.",
    ),
    (_delete_protected, "удаление main/master на remote запрещено."),
    (
        _hard_reset_to_remote_protected,
        "git reset --hard origin/main уничтожает локальную работу — останови и спроси человека.",
    ),
)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # не наш формат — не мешаем работе
    command = str((event.get("tool_input") or {}).get("command", ""))
    if not command:
        return 0
    for segment in segments(command):
        for rule, message in RULES:
            if rule(segment):
                print(f"blocked: {message}", file=sys.stderr)
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
