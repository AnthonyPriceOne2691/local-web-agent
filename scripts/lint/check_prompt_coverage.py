#!/usr/bin/env python3
"""Охват промпт-стора: у какого файла есть утверждение ПО СОДЕРЖАНИЮ (§14.4 п.2).

⚠ **Почему это не считается чтением.** «Файл упомянут в тесте» ничего не значит:
прежний двойник упоминал промпты в каждом прогоне и был слеп к их содержанию по
построению. Единственный честный признак — **порча**: если изменить файл и НИ
ОДИН тест не покраснел, утверждения по содержанию нет, чем бы тесты ни казались.

Поэтому здесь дифференциальный прогон, а не разбор кода: каждому файлу стора по
очереди приписывается маркер, гоняется быстрый набор, файл возвращается.
Возврат — на СТАРТЕ следующего шага и в `finally`: SIGTERM обходит `finally`, и
оставленная порча тише всего ломает следующий прогон (§14.6).

Список непокрытых обязан ТАЯТЬ — как `known_fail` в §3.5. Рост требует строки
решения, потому что новый непокрытый промпт это новая слепая зона, а не «пока
не дошли руки».

Использование:
  check_prompt_coverage.py             # сверить с baseline
  check_prompt_coverage.py --generate  # пере-снять (только вниз)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "data" / "prompts"
BASELINE = Path(__file__).resolve().parent / "prompt_coverage_baseline.txt"
MARK = "\n<!-- ПОРЧА ОХВАТА -->\n"
#: Быстрый набор: только кассетные тесты. Гонять весь сьют на каждый из
#: девятнадцати файлов — минуты, а гейт, который не влезает в бюджет, отключают.
PROBE = ["-k", "m_contracts", "-q", "--no-header", "-p", "no:cacheprovider"]


def store() -> list[Path]:
    return sorted(p for p in PROMPTS.rglob("*") if p.is_file())


def interpreter() -> str:
    """Питон, у которого ЕСТЬ pytest, — ищется, а не наследуется от вызывающего.

    ⚠ Первая редакция брала `sys.executable`, и это поймала канарейка доктора, а
    не прогон. Хук зовёт гейт венвовым питоном, доктор — системным; во втором
    pytest'а нет, `suite_is_red()` возвращала True всегда, гейт отказывался
    мерить, и канарейка честно уходила в SKIP «красный и без канарейки». То есть
    гейт зависел от того, КТО его позвал, а не от состояния проекта.
    """
    venv = ROOT / "backend" / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def suite_state() -> str:
    """`ok` · `red` · `no-pytest`. Третье — не провал, а НАЗВАННЫЙ пропуск."""
    r = subprocess.run([interpreter(), "-m", "pytest", "tests/", *PROBE],
                       cwd=ROOT / "backend", capture_output=True, text=True)
    if r.returncode == 0:
        return "ok"
    if "No module named pytest" in (r.stderr + r.stdout):
        return "no-pytest"
    return "red"


def suite_is_red() -> bool:
    return suite_state() != "ok"


def probe(f: Path) -> bool:
    """Ловится ли порча ЭТОГО файла. Оригинал возвращается всегда."""
    original = f.read_bytes()
    try:
        f.write_bytes(original + MARK.encode())
        return suite_is_red()
    finally:
        f.write_bytes(original)


def measure() -> tuple[list[str], list[str]]:
    """Дифференциальный прогон ЦЕЛИКОМ: «зелено без порчи, красно с ней».

    ⚠ Первая редакция считала только вторую половину — «сьют красный» — и
    контрольный прогон поймал её на лжи в самую выгодную сторону: удаляю файл
    кассеты целиком, и охват читается **19 из 19** вместо нуля. Причина в том,
    что без кассеты тест падает НА ЛЮБОМ входе, и красный переставал быть
    признаком того, что порчу заметили. То есть проба показывала идеальный охват
    ровно тогда, когда оракула нет вовсе.

    Поэтому чистое дерево проверяется ПЕРВЫМ, и красное чистое дерево — не повод
    печатать числа, а повод отказаться их печатать.
    """
    covered, blind = [], []
    for f in store():
        rel = str(f.relative_to(PROMPTS))
        # Возврат на СТАРТЕ: если прошлый прогон убили сигналом, `finally` не
        # отработал, и порча уехала бы в замер как «покрыто».
        text = f.read_bytes()
        if MARK.encode() in text:
            f.write_bytes(text.replace(MARK.encode(), b""))
        (covered if probe(f) else blind).append(rel)
    return covered, blind


def main() -> int:
    if not PROMPTS.is_dir():
        print("промпт-стора нет — охват мерить не на чем")
        return 0
    state = suite_state()
    if state == "no-pytest":
        # Честный пропуск с ИМЕНЕМ инструмента: гейт без pytest'а не может
        # ответить, и выдать это за успех — ровно тот класс, что канон ловит
        # `_probe_honest_skip`. Ноль, потому что это не нарушение проекта.
        print("prompt-coverage: SKIP — нет pytest у "
              f"{interpreter()}; охват мерить нечем (§14.4)")
        return 0
    if state == "red":
        print("быстрый набор КРАСНЫЙ на чистом дереве — охват мерить нечем: "
              "красное под порчей перестало быть признаком.\n"
              "Почини набор, потом мерь охват.", file=sys.stderr)
        return 1
    covered, blind = measure()
    total = len(covered) + len(blind)
    if "--generate" in sys.argv:
        BASELINE.write_text(
            "# Файлы промпт-стора БЕЗ утверждения по содержанию (§14.4 п.2).\n"
            "# Признак — порча: изменил файл, сьют не покраснел.\n"
            "# Список обязан ТАЯТЬ. Рост — решение с записью, а не «не дошли руки».\n"
            f"# охват: {len(covered)} из {total}\n"
            + "".join(f"{b}\n" for b in blind), encoding="utf-8")
        print(f"baseline снят: охват {len(covered)} из {total}")
        return 0
    if not BASELINE.is_file():
        print(f"нет {BASELINE.name} — сними: --generate", file=sys.stderr)
        return 1
    was = {ln.strip() for ln in BASELINE.read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.startswith("#")}
    now = set(blind)
    grew = sorted(now - was)
    print(f"prompt-coverage: покрыто {len(covered)} из {total}, "
          f"слепых {len(blind)} (в снимке {len(was)})")
    if grew:
        for b in grew:
            print(f"  ✗ {b}: порча не поймана, а в снимке файла нет", file=sys.stderr)
        print("Слепых стало БОЛЬШЕ — новый промпт без утверждения по содержанию.\n"
              "Заведи оракул (кассета/метаморфный по §6.5b) либо назови цену "
              "решением.", file=sys.stderr)
        return 1
    if (melted := sorted(was - now)):
        print(f"  растаяло: {', '.join(melted)} — пере-сними снимок (--generate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
