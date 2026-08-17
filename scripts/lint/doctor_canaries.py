#!/usr/bin/env python3
"""Канарейки: чем пробуется каждый гейт и что объявил проект.

Часть доктора (`cqg@1.82`, вход — `contour_doctor.py`). Здесь ДАННЫЕ проб и
чтение объявлений проекта; сами пробы — в `doctor_probes.py`. Разделено не по
красоте, а по планке 300 строк (§9.1a п.5): вместе это 400+.
"""

from __future__ import annotations

import json
from pathlib import Path

from doctor_core import SKIP, run

CANARIES: dict[str, tuple[str, str]] = {
    # grep-правила
    "config-access": ("canary.py", "import os\nX = os.getenv('SECRET')\n"),
    "di-indirection": ("canary.py", "from importlib import import_module\n"
                                    "m = import_module('pkg.sub')\n"),
    "service-no-web": ("service.py", "from fastapi import APIRouter\nr = APIRouter()\n"),
    "no-grab-bag-module": ("utils.py", "def helper():\n    return 1\n"),
    "blind-error": ("canary.py", 'def f():\n    raise Exception("bad")\n'),
    "unstructured-log": ("canary.py", "import logging\n"
                                      "logger = logging.getLogger(__name__)\n"
                                      "def f(url):\n"
                                      '    logger.info(f"fetch {url}")\n'),
    # ast-правила
    "silent-except": ("canary.py", "def f():\n    try:\n        pass\n"
                                   "    except Exception:\n        pass\n"),
    "inline-prompt": ("canary.py", 'P = """ты — помощник\n' + "строка\n" * 8 + '"""\n'),
    "cpu-in-async": ("canary.py", "import json\n"
                                  "async def f(rows):\n"
                                  "    for r in rows:\n"
                                  "        json.loads(r)\n"),
    # Односложные гейты: ключ — имя скрипта, у них нет `--list-rules`.
    "check_file_length.sh": ("huge.py", "x = 1\n" * 700),
    "check_complexity_gate.sh": ("complex.py",
        "def f(a):\n" + "".join(f"    if a == {i}:\n        return {i}\n"
                                for i in range(14))),
    "unbounded-list": ("canary.py", "from fastapi import APIRouter\n"
                                    "router = APIRouter()\n\n\n"
                                    '@router.get("/all")\n'
                                    "async def all_items() -> list[dict]:\n"
                                    "    return await repo.everything()\n"),
}


# Не гейты: измерительные инструменты и сам доктор. Канарейку им подсовывать
# бессмысленно — они ничего не запрещают. Раньше они попадали в SKIP и раздували

TOOL_DEPENDENT = {
    "check_jscpd_gate.sh": "jscpd",
    "check_deps_audit.sh": "pip-audit / npm",
    "check_mutation_gate.sh": "mutmut",
    "check_eslint_warnings.sh": "eslint / npm",
    "check_diff_coverage.sh": "pytest-cov",
    "check_ci_status.sh": "gh",
    "check_complexity_gate.sh": "ruff",
    "check_layers_gate.sh": "lint-imports / depcruise",
}

# `PATH` без homebrew и venv: coreutils и git на месте, а jscpd/mutmut/gh/ruff —
# нет. Та же раскладка, что в сьюте канона (`tests/`), и она не выдумана: гейты
# ищут инструмент через `command -v`, а живут эти инструменты вне /usr/bin.
BARE_PATH = "/usr/bin:/bin"

# Гейты, которых канон НЕ поставляет, — свои у проекта (`check_canon_vendor.sh` в
# первом настоящем развёртывании, находка 7). Канарейку для них доктор выдумать не
# может: класс нарушения знает только автор гейта. Но проект может её ОБЪЯВИТЬ —
# файлом ниже, — и тогда чужой гейт проверяется исполнением, как свои. Без этого
# «свой гейт» навсегда оставался SKIP, то есть областью, где ЛОЖЬ невидима, а
# именно чужие гейты никто больше и не проверяет.
#
# Формат — {имя скрипта: {"path": путь от корня репо, "content": текст}}:
#   {"check_canon_vendor.sh": {"path": "docs/canon/AGENT_STACK.md",
#                              "content": "подменённая копия канона\n"}}
OWN_CANARIES = "scripts/lint/canaries.json"


def _setup_gate_coverage(lab: Path) -> tuple[list[str], dict]:
    """Скрипт лежит в `scripts/lint`, но в конфиге его нет → мета-гейт краснеет.

    Именно этот случай и породил мета-гейт: jscpd был извлечён, адаптирован и не
    вписан, а приёмка показала 7/7 зелёных.
    """
    (lab / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks:\n      - id: nothing\n"
        "        name: ничего не подключает\n        entry: true\n"
        "        language: system\n", encoding="utf-8")
    (lab / "scripts" / "lint" / "check_orphan_gate.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    return [], {}


def _setup_new_dependency(lab: Path) -> tuple[list[str], dict]:
    """Пакет добавлен в манифест и НЕ объявлен в STATUS → гейт краснеет."""
    (lab / "backend").mkdir(exist_ok=True)
    man = lab / "backend" / "pyproject.toml"
    man.write_text('[project]\nname = "app"\ndependencies = ["pydantic>=2.0"]\n',
                   encoding="utf-8")
    (lab / "delivery" / "active").mkdir(parents=True, exist_ok=True)
    (lab / "delivery" / "active" / "STATUS.md").write_text(
        "# STATUS\n\n- class: S\n", encoding="utf-8")
    run(["git", "add", "-A"], lab)
    run(["git", "-c", "user.email=d@d", "-c", "user.name=d",
         "commit", "-qm", "manifest"], lab)
    run(["git", "branch", "-f", "b0"], lab)
    man.write_text('[project]\nname = "app"\n'
                   'dependencies = ["pydantic>=2.0", "httpx>=0.27"]\n', encoding="utf-8")
    run(["git", "add", "-A"], lab)
    run(["git", "-c", "user.email=d@d", "-c", "user.name=d",
         "commit", "-qm", "add dep"], lab)
    return [], {"BASE": "b0"}


def _setup_baseline_ratchet(lab: Path) -> tuple[list[str], dict]:
    """Снимок переснят ВВЕРХ → легализация свежих нарушений, гейт краснеет."""
    base = lab / "scripts" / "lint" / "file_length_baseline.txt"
    base.write_text("# снимок\n[baseline]\n120:backend/features/a.py\n", encoding="utf-8")
    run(["git", "add", "-A"], lab)
    run(["git", "-c", "user.email=d@d", "-c", "user.name=d",
         "commit", "-qm", "baseline"], lab)
    run(["git", "branch", "-f", "b0"], lab)
    base.write_text("# снимок\n[baseline]\n400:backend/features/a.py\n", encoding="utf-8")
    run(["git", "add", "-A"], lab)
    run(["git", "-c", "user.email=d@d", "-c", "user.name=d",
         "commit", "-qm", "raise snapshot"], lab)
    return [], {"BASE": "b0"}


# Гейты со своей постановкой: канарейка тут — не файл с нарушением, а СОСТОЯНИЕ
# репозитория (несвязанный скрипт, необъявленная зависимость, поднятый снимок).
DIRECT_SETUP = {
    "check_gate_coverage.sh": _setup_gate_coverage,
    "check_new_dependency.py": _setup_new_dependency,
    "check_baseline_ratchet.sh": _setup_baseline_ratchet,
}




class CanaryData:
    def _read_own_canaries(self) -> dict[str, list[tuple[str | None, str, str]]]:
        """Канарейки, объявленные проектом. Битый файл — НАЗВАТЬ, а не пропустить.

        Молчаливое «не разобрал → канареек нет» вернуло бы ровно тот класс, за
        которым доктор и придуман: объявление есть, проверки нет, и об этом никто
        не сказал.

        Ключ — `<скрипт>` **или** `<скрипт>:<правило>`, как в
        `not-applicable.json`. Форма с правилом обязательна, и это не симметрия
        ради симметрии: многоправильный гейт БЕЗ `--rule` падает с usage, а
        доктор принимал это за «гейт красный и без канарейки — судить нечем».
        Замерено на первом же применении: два адаптированных гейта Swift-проекта
        (`check_grep_gate.sh`, `check_ast_gate.py`) уходили в SKIP, то есть
        объявление снова принималось и не исполнялось — тот самый класс, ради
        которого этот механизм и чинили.
        """
        f = self.root / OWN_CANARIES
        if not f.is_file():
            return {}
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.add(SKIP, OWN_CANARIES, f"не разобран ({exc}) — свои гейты НЕ "
                                         "проверены, хотя канарейки объявлены")
            return {}
        out: dict[str, list[tuple[str | None, str, str]]] = {}
        for key, spec in (raw or {}).items():
            # Ключ с `_` в начале — КОММЕНТАРИЙ, а не имя гейта (§5.5). JSON
            # комментариев не имеет, поэтому формат документируют ключом, и
            # доктор читал его как объявление: `SKIP канарейка _ — объявление без
            # path/content`. Пропуск, которого нет, в собственной сводке
            # непокрытости — то есть инструмент врал про свою же слепую зону, и
            # лечился бы этот SKIP удалением пояснения из файла.
            if str(key).startswith("_"):
                continue
            if not (isinstance(spec, dict) and spec.get("path") and spec.get("content")):
                self.add(SKIP, f"канарейка {key}",
                         f"объявление без path/content в {OWN_CANARIES}")
                continue
            name, _, rule = str(key).partition(":")
            out.setdefault(name, []).append(
                (rule or None, str(spec["path"]), str(spec["content"])))
        return out


    # --- E. канарейки: главное ----------------------------------------------
    def _rules_of(self, script: Path) -> list[str]:
        """Список правил берётся У СКРИПТА (`--list-rules`), не дублируется тут."""
        cmd = ["python3", str(script)] if script.suffix == ".py" else ["bash", str(script)]
        code, out = run(cmd + ["--list-rules"], self.root)
        if code != 0:
            return []
        return [l.strip() for l in out.splitlines() if l.strip() and " " not in l.strip()]

