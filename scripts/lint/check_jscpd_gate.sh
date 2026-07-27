#!/usr/bin/env bash
# DRY / copy-paste гейт (jscpd). Глобальный clone-count ратчет.
#
# jscpd считает clone-пары в прод-Python; снимок хранится в jscpd_baseline.txt; гейт
# падает, если число дублей ВЫРОСЛО (добавили копипаст). После консолидации дублей
# число падает — пере-снять baseline вниз через --generate. Порог jscpd: min-tokens 50.
#
# Бинарь jscpd ищется в node_modules фронта, затем в PATH. Нет бинаря — гейт не
# блокирует, только предупреждает (свежий clone без npm ci).
#
# Настройка (env):
#   LINT_PY_SRC  — каталог прод-Python для анализа, от repo-root (дефолт: backend/features)
#   LINT_FE_DIR  — фронт-каталог с node_modules (дефолт: frontend)
#
# Режимы:
#   check_jscpd_gate.sh             # проверка; exit 1 при росте дублей
#   check_jscpd_gate.sh --generate  # пере-снять baseline (текущее число дублей)
#   STRICT=0 check_jscpd_gate.sh    # soft (warning, exit 0)

set -uo pipefail

STRICT=${STRICT:-1}
PY_SRC=${LINT_PY_SRC:-backend/features}
FE_DIR=${LINT_FE_DIR:-frontend}
GENERATE=0
[[ "${1:-}" == "--generate" ]] && GENERATE=1

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BASELINE="$SCRIPT_DIR/jscpd_baseline.txt"

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT" || exit 1

red=$(printf '\033[31m'); yellow=$(printf '\033[33m'); green=$(printf '\033[32m'); reset=$(printf '\033[0m')

if [[ -x "$FE_DIR/node_modules/.bin/jscpd" ]]; then
  JSCPD="$FE_DIR/node_modules/.bin/jscpd"
elif command -v jscpd >/dev/null 2>&1; then
  JSCPD="jscpd"
else
  printf '%s⚠ jscpd не найден — DRY-гейт пропущен. Установка: npm i -D jscpd%s\n' "$yellow" "$reset"
  exit 0
fi

# Число clone-пар в $PY_SRC (python, min-tokens 50, без tests).
current_clones() {
  # Адаптация (CQG «Применимость»): venv/node_modules внутри дерева при LINT_PY_SRC=.
  "$JSCPD" "$PY_SRC" -f python -k 50 \
    -i "**/tests/**,**/test_*.py,**/.venv/**,**/node_modules/**,**/dist/**" -r console 2>/dev/null \
    | grep -oE 'Found [0-9]+ clones' | grep -oE '[0-9]+' | head -1
}

count=$(current_clones)
count=${count:-0}

if [[ "$GENERATE" == "1" ]]; then
  {
    echo "# jscpd_baseline.txt — снимок DRY-гейта. Генерируется --generate, НЕ руками."
    echo "# Одно число = кол-во clone-пар в прод-Python (python, min-tokens 50, без tests)."
    echo "# Гейт падает при РОСТЕ; после консолидации дублей пере-снять вниз (--generate)."
    echo "$count"
  } >"$BASELINE"
  echo "${green}jscpd baseline пересобран${reset}: $count clone-пар"
  exit 0
fi

baseline=$(grep -m1 -oE '^[0-9]+' "$BASELINE" 2>/dev/null)
baseline=${baseline:-0}

if [[ "$count" -gt "$baseline" ]]; then
  if [[ "$STRICT" == "1" ]]; then
    printf '%sERROR%s: дубли выросли: %d clone-пар (baseline %d).\n' "$red" "$reset" "$count" "$baseline"
    echo "Не копируй код: вынеси общий helper/константу (rule-of-three для логики)."
    echo "Если рост оправдан (напр. split-facade) — пере-снять снимок: --generate."
    exit 1
  fi
  printf '%sWARNING%s: дубли выросли: %d (baseline %d).\n' "$yellow" "$reset" "$count" "$baseline"
fi
exit 0
