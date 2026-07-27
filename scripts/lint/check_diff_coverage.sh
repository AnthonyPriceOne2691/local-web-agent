#!/usr/bin/env bash
# coverage-on-diff — DoD-отчёт покрытия ИЗМЕНЁННЫХ prod-файлов.
#
# НЕ pre-commit хук (полный сьют = минуты): запускается руками перед push / в DoD.
# Гоняет pytest c coverage-json, затем печатает покрытие каждого изменённого
# prod-файла (diff против BASE, дефолт origin/main) и сравнивает с целью (70%).
#
# База диффа:
#   • дифф до BASE пуст, но есть НЕзакоммиченные правки -> ЖЁЛТЫЙ ворнинг (рабочее
#     дерево скрипт не меряет — закоммить и повторить); STRICT=1 -> exit 1;
#   • дифф пуст и дерево чистое (только что запушено) -> авто-fallback на origin/main@{1}
#     (прошлая позиция = последний пуш); fallback отключается, если BASE задан снаружи.
#
# Настройка (env):
#   LINT_BE_DIR   — каталог backend с venv/pyproject/pytest (дефолт: backend)
#   LINT_COV_PKG  — пакет для --cov (дефолт: features)
#   LINT_PY_SRC   — прод-Python корень от repo-root (дефолт: $BE_DIR/$COV_PKG)
#   LINT_VENV     — путь к venv относительно backend (дефолт: .venv)
#
# Режимы:
#   check_diff_coverage.sh              # отчёт (exit 0 всегда)
#   STRICT=1 check_diff_coverage.sh     # exit 1: файл < MIN_PCT / грязное дерево
#   BASE=<ref> …                        # база диффа (дефолт origin/main)
#   SKIP_TESTS=1 …                      # переиспользовать существующий coverage.json

set -uo pipefail

STRICT=${STRICT:-0}
BASE_WAS_SET=${BASE+set}
BASE=${BASE:-origin/main}
MIN_PCT=${MIN_PCT:-70}
SKIP_TESTS=${SKIP_TESTS:-0}

BE_DIR=${LINT_BE_DIR:-backend}
COV_PKG=${LINT_COV_PKG:-features}
PY_SRC=${LINT_PY_SRC:-$BE_DIR/$COV_PKG}
VENV=${LINT_VENV:-.venv}

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT/$BE_DIR" || exit 1

red=$(printf '\033[31m'); yellow=$(printf '\033[33m'); green=$(printf '\033[32m'); reset=$(printf '\033[0m')

# git diff — от repo-root (git -C): pathspec от корня не матчится из cwd backend/.
list_changed() { # $1 = base-реф; закоммиченный дифф prod-файлов (без тестов)
  git -C "$REPO_ROOT" diff --name-only "$1"...HEAD -- "$PY_SRC/*.py" 2>/dev/null \
    | grep -vE '/tests/|/test_[^/]*\.py$' \
    | sed "s#^$BE_DIR/##"
}

# Незакоммиченные правки — их дифф-списком не увидеть, а сьют их исполняет:
# источник ложного зелёного.
dirty=$(git -C "$REPO_ROOT" status --porcelain -- "$PY_SRC/*.py" 2>/dev/null \
  | cut -c4- | grep -vE '/tests/|/test_[^/]*\.py$' || true)

changed=$(list_changed "$BASE")

if [[ -z "$changed" && -n "$dirty" ]]; then
  echo "${yellow}diff-coverage: коммитов относительно $BASE нет, но есть НЕзакоммиченные правки —${reset}"
  echo "${yellow}рабочее дерево скрипт не меряет. Закоммить и повторить. Незакоммичено:${reset}"
  echo "$dirty" | sed 's/^/  • /'
  [[ "$STRICT" == "1" ]] && exit 1
  exit 0
fi

# Запушено (origin/main == HEAD) и дерево чистое -> меряем последний пуш через reflog
# remote-tracking ветки. Только для дефолтного BASE: явный BASE=<ref> уважаем как есть.
if [[ -z "$changed" && -z "$BASE_WAS_SET" ]] \
  && git -C "$REPO_ROOT" rev-parse --verify -q 'origin/main@{1}' >/dev/null 2>&1; then
  changed=$(list_changed 'origin/main@{1}')
  if [[ -n "$changed" ]]; then
    prev_short=$(git -C "$REPO_ROOT" rev-parse --short 'origin/main@{1}')
    BASE="origin/main@{1} = $prev_short"
    echo "${yellow}diff-coverage: origin/main == HEAD (всё запушено) — меряю последний пуш: BASE=$BASE${reset}"
  fi
fi

if [[ -z "$changed" ]]; then
  echo "${green}diff-coverage: изменённых prod-файлов нет (BASE=$BASE)${reset}"
  exit 0
fi

if [[ -n "$dirty" ]]; then
  echo "${yellow}внимание: есть незакоммиченные правки — сьют их исполняет, но в отчёте ниже их нет:${reset}"
  echo "$dirty" | sed 's/^/  • /'
fi

if [[ "$SKIP_TESTS" != "1" ]]; then
  echo "diff-coverage: гоняю сьют с coverage (может занять минуты)…"
  "$VENV/bin/python" -m pytest -q --cov="$COV_PKG" --cov-report=json:coverage.json >/dev/null 2>&1
fi
if [[ ! -f coverage.json ]]; then
  echo "${red}coverage.json не найден (сьют не отработал?)${reset}"
  exit 1
fi

# changed — через env: пайп в `python - <<heredoc` не работает (heredoc занимает stdin).
CHANGED="$changed" "$VENV/bin/python" - "$MIN_PCT" "$STRICT" <<'PY'
import json
import os
import sys

min_pct = float(sys.argv[1])
strict = sys.argv[2] == "1"
changed = [line.strip() for line in os.environ.get("CHANGED", "").splitlines() if line.strip()]
files = json.load(open("coverage.json"))["files"]

fails = 0
print(f"{'файл':70s} {'stmts':>6s} {'miss':>5s} {'cov%':>6s}")
for path in changed:
    info = files.get(path)
    if info is None:
        print(f"{path:70s} {'—':>6s} {'—':>5s} {'0.0':>6s}  <- не исполнялся тестами вовсе")
        fails += 1
        continue
    s = info["summary"]
    pct = s["percent_covered"]
    mark = "" if pct >= min_pct else f"  <- ниже цели {min_pct:.0f}%"
    if pct < min_pct:
        fails += 1
    print(f"{path:70s} {s['num_statements']:6d} {s['missing_lines']:5d} {pct:6.1f}{mark}")

if fails:
    print(f"\n{fails} изменённых файл(ов) ниже цели {min_pct:.0f}%.")
    sys.exit(1 if strict else 0)
PY
rc=$?
[[ "$STRICT" == "1" ]] && exit "$rc"
exit 0
