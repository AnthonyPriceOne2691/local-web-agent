"""Контур ruff: канонные правила действуют вне `backend/`, а не только внутри.

Зачем тест. Конфига в корне не было, а ruff берёт **ближайший** конфиг вверх по
дереву: `backend/**` брал `backend/pyproject.toml`, а `cli/**` и `scripts/**` не
находили ничего и линтовались дефолтным набором (E4/E7/E9/F). Хук при этом был
зелёным — «гейт есть, проверки нет». Удаление корневого `ruff.toml` вернёт ровно
это состояние молча, поэтому проверка смотрит на **разрешённые настройки файла**,
а не на факт существования конфига.

Дискриминатор — `line_length`: канон проекта 110, дефолт ruff 88.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CANON_LINE_LENGTH = "linter.line_length = 110"

# По одному представителю каждого каталога вне backend/: если контур сузят,
# упадёт ровно тот, кого выкинули.
COVERED = ["cli/main.py", "scripts/okf_validate.py", "scripts/hooks/protect_main.py"]


def _settings_for(rel: str) -> str:
    ruff = shutil.which("ruff") or f"{sys.executable} -m ruff"
    done = subprocess.run(
        [*ruff.split(), "check", "--show-settings", rel],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout


@pytest.mark.parametrize("rel", COVERED)
def test_canon_ruff_config_applies_outside_backend(rel: str) -> None:
    assert (REPO / rel).is_file(), f"файл-представитель исчез: {rel}"
    settings = _settings_for(rel)
    assert CANON_LINE_LENGTH in settings, (
        f"{rel} линтуется НЕ канонным конфигом (нет '{CANON_LINE_LENGTH}'). "
        "Скорее всего пропал корневой ruff.toml — тогда каталог молча вернётся "
        "к дефолтному набору ruff."
    )


def test_backend_keeps_its_own_config() -> None:
    """Корневой конфиг не должен перехватывать backend: у него свой pyproject."""
    settings = _settings_for("app/main.py".replace("app/", "backend/app/"))
    assert CANON_LINE_LENGTH in settings
