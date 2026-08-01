"""protect_main hook: блокирует опасное и НЕ мешает безопасному.

Половина кейсов здесь — «должен пропустить». Именно они и есть смысл поставки:
хук матчил правила по всей строке команды, поэтому признаки из разных команд
складывались (`-f` из `pkill -f …` плюс слово `main` из `app.main:app`) и пуш
ветки читался как force-push. Ложное срабатывание вреднее пропуска — обойти его
стоит ноль, и защита превращается в шум.

Хук вызывается как процесс, через stdin-JSON: проверяется настоящая граница
(разбор события + exit code), а не внутренняя функция.

Опасные строки собраны **из частей-констант**: иначе этот файл сам не пройдёт
хук, когда его содержимое попадёт в командную строку (git commit -m, grep, cat).

Негативный контроль (без него проверка пустая):
    PROTECT_MAIN_HOOK=/tmp/protect_main_old.py pytest tests/test_protect_main_hook.py
на несегментной версии кейсы «должен пропустить» падают.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(
    os.environ.get(
        "PROTECT_MAIN_HOOK",
        Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "protect_main.py",
    )
)

# Части-константы: опасные команды не встречаются в файле целиком.
GIT = "git"
PUSH = "pu" + "sh"
FORCE = "--fo" + "rce"
FORCE_SHORT = "-" + "f"
LEASE = "--force-with-" + "lease"
MAIN = "ma" + "in"
DELETE = "--dele" + "te"
RESET = "res" + "et"
HARD = "--ha" + "rd"


def run_hook(command: str) -> int:
    """Exit code хука для команды. 2 = блок, 0 = разрешено."""
    event = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    done = subprocess.run(
        [sys.executable, str(HOOK)], input=event, capture_output=True, text=True, check=False
    )
    return done.returncode


ALLOWED = [
    # Обычная работа с main — хук про перезапись истории, а не про main вообще.
    f"{GIT} {PUSH} origin {MAIN}",
    f"{GIT} {PUSH}",
    f"{GIT} fetch origin {MAIN} && {GIT} merge origin/{MAIN}",
    # Пуш ветки: force допустим, потому что ветка не main.
    # Вторая регрессия того же класса: имя ветки СОДЕРЖИТ слово main.
    f"{GIT} {PUSH} {FORCE} origin fix/protect-{MAIN}-segments",
    f"{GIT} {PUSH} {FORCE} origin fix/{MAIN}-guard",
    f"{GIT} {PUSH} {FORCE_SHORT} origin feature/x",
    f"{GIT} {PUSH} {FORCE} origin HEAD:fix/{MAIN}tenance",
    # Регрессия поставки: флаг в одной команде, слово main — в другой.
    f'pkill {FORCE_SHORT} "uvicorn app.{MAIN}:app"; {GIT} {PUSH} origin fix/a',
    f'{GIT} {PUSH} origin fix/a && pkill {FORCE_SHORT} "uvicorn app.{MAIN}:app"',
    f"grep {FORCE_SHORT} {MAIN} file.txt | head -3",
    # Разделитель — перевод строки (многострочная команда).
    f"pkill {FORCE_SHORT} app.{MAIN}:app\n{GIT} {PUSH} origin fix/a",
    # reset --hard локально (не на origin/main) — законный откат рабочего дерева.
    f"{GIT} {RESET} {HARD} HEAD",
    f"{GIT} {RESET} {HARD} {MAIN}",
]

BLOCKED = [
    f"{GIT} {PUSH} {FORCE} origin {MAIN}",
    f"{GIT} {PUSH} origin {MAIN} {FORCE}",
    f"{GIT} {PUSH} {FORCE_SHORT} origin {MAIN}",
    f"{GIT} {PUSH} {LEASE} origin {MAIN}",
    f"{GIT} {PUSH} {FORCE} upstream master",
    # Опасное посреди составной команды — сегментация не должна ничего прятать.
    f"echo start && {GIT} {PUSH} {FORCE} origin {MAIN} && echo done",
    f"{GIT} {PUSH} {DELETE} origin {MAIN}",
    f"{GIT} {PUSH} origin :{MAIN}",
    f"{GIT} {RESET} {HARD} origin/{MAIN}",
    # Те же цели в других формах записи: с remote-префиксом, refspec'ом и `+`.
    f"{GIT} {PUSH} {FORCE} origin HEAD:{MAIN}",
    f"{GIT} {PUSH} {FORCE} origin +{MAIN}:{MAIN}",
    f"{GIT} {PUSH} {FORCE} origin refs/heads/{MAIN}",
    f"{GIT} {RESET} {HARD} upstream/master",
]


@pytest.mark.parametrize("command", ALLOWED)
def test_safe_commands_pass(command: str) -> None:
    assert run_hook(command) == 0, f"ложное срабатывание на: {command}"


@pytest.mark.parametrize("command", BLOCKED)
def test_dangerous_commands_blocked(command: str) -> None:
    assert run_hook(command) == 2, f"пропущено опасное: {command}"


def test_blocked_command_explains_itself() -> None:
    """Сообщение уходит агенту в stderr — без него блок читается как поломка."""
    event = json.dumps({"tool_input": {"command": f"{GIT} {PUSH} {FORCE} origin {MAIN}"}})
    done = subprocess.run(
        [sys.executable, str(HOOK)], input=event, capture_output=True, text=True, check=False
    )
    assert done.returncode == 2
    assert "blocked:" in done.stderr


def test_empty_and_foreign_events_do_not_block() -> None:
    """Не наш формат события — не мешаем работе (хук не обязан понимать всё)."""
    for payload in ('{"tool_input": {}}', '{"tool_input": null}', "{}", "not json at all", ""):
        done = subprocess.run(
            [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, check=False
        )
        assert done.returncode == 0, f"блок на безобидном событии: {payload!r}"
