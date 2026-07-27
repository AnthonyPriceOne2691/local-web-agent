#!/usr/bin/env python3
"""protect-main hook (Delivery §10.1 / A.11): блокирует опасные git-команды.

PreToolUse-хук для Bash: читает JSON события со stdin, смотрит на команду.
Exit 2 = блок (stderr уходит агенту), exit 0 = разрешено.

Закрывает то, что на бесплатном тарифе не закрыто серверной защитой ветки
(см. delivery/STACK-ACCEPTANCE.md § Остатки): force-push в main и удаление
основной ветки. Не заменяет branch protection — поднимает цену случайности.
"""

from __future__ import annotations

import json
import re
import sys

# force-push в main/master в любом порядке флагов и с любым remote
FORCE_PUSH = re.compile(
    r"\bgit\b.{0,80}?\bpush\b(?=.*(?:--force\b|--force-with-lease\b|(?<!\w)-f\b))"
    r".*\b(main|master)\b",
    re.IGNORECASE | re.DOTALL,
)
DELETE_MAIN = re.compile(
    r"\bgit\b.{0,80}?\bpush\b.*(?:--delete\b|\s:)\s*(?:origin\s+)?(main|master)\b",
    re.IGNORECASE | re.DOTALL,
)
HARD_RESET_REMOTE = re.compile(
    r"\bgit\b.{0,40}?\breset\b.*--hard\b.*\borigin/(main|master)\b",
    re.IGNORECASE | re.DOTALL,
)

RULES = (
    (FORCE_PUSH, "force-push в main/master запрещён (Delivery §4.2). "
                 "Нужен переписанный main — это HITL-решение человека."),
    (DELETE_MAIN, "удаление main/master на remote запрещено."),
    (HARD_RESET_REMOTE, "git reset --hard origin/main уничтожает локальную работу — "
                        "останови и спроси человека."),
)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # не наш формат — не мешаем работе
    command = str((event.get("tool_input") or {}).get("command", ""))
    if not command:
        return 0
    for pattern, message in RULES:
        if pattern.search(command):
            print(f"blocked: {message}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
