#!/usr/bin/env bash
# Grep-гейты для конвенций, у которых нет готового линтера.
#
# Механика — per-file baseline-ratchet: текущие (легаси) нарушения живут в снимке
# `<count>:<path>` и тают по мере правки файлов; файл ВНЕ снимка (в т.ч. любой новый)
# обязан иметь 0 нарушений. Ратчет только вниз: файл из baseline проходит при
# count <= снимок; --generate пере-снимает снимок вниз.
#
# Правила:
#   config-access      — getattr(config,...) / os.getenv / os.environ вне config/
#                        (опечатка в настройке должна падать, а не тихо дефолтиться)
#   di-indirection     — (pkg|session|ctx): Any + importlib.import_module("...") reach-back
#                        (DI вместо importlib-магии; Any в новых сигнатурах запрещён)
#   service-no-web     — импорт web-фреймворка (fastapi) в сервис-слое
#   no-grab-bag-module — файлы-помойки utils/misc/common/helpers.py без темы
#
# Настройка (env):
#   LINT_PY_SRC  — корневой каталог прод-Python для гейтов, от repo-root (дефолт: backend/features)
#
# Режимы:
#   check_grep_gate.sh --rule config-access             # проверка; exit 1 при регрессии
#   check_grep_gate.sh --rule config-access --generate  # пересобрать baseline правила
#   STRICT=0 check_grep_gate.sh --rule ...              # soft (warning, exit 0)

set -uo pipefail

STRICT=${STRICT:-1}
PY_SRC=${LINT_PY_SRC:-backend/features}
RULE=""
GENERATE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rule) RULE="${2:-}"; shift 2 ;;
    --generate) GENERATE=1; shift ;;
    *) shift ;;
  esac
done

# SCRIPT_DIR резолвим ДО cd в REPO_ROOT (BASH_SOURCE относителен cwd вызова).
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Токен-граница делается через (^|[^A-Za-z_.]) вместо \b: BSD grep (macOS) \b не держит.
# FILTER (опц.) — grep -E по путям: сузить правило до подмножества файлов по имени.
FILTER=""
case "$RULE" in
  config-access)
    PATTERN='getattr\([[:space:]]*config|(^|[^A-Za-z_.])os\.getenv|(^|[^A-Za-z_.])os\.environ'
    BASELINE="$SCRIPT_DIR/config_access_baseline.txt"
    LABEL='config-access: getattr(config,...) / os.getenv вне config/'
    HINT='Читай настройку через типизированный config.X (опечатку ловит type-checker). Дефолт — один раз в config/.'
    ;;
  di-indirection)
    PATTERN='(^|[^A-Za-z_])(pkg|session|ctx)[[:space:]]*:[[:space:]]*Any|import_module\([[:space:]]*["'"'"']'
    BASELINE="$SCRIPT_DIR/di_indirection_baseline.txt"
    LABEL='di-indirection: (pkg|session|ctx): Any / importlib reach-back'
    HINT='Новый код: явные зависимости через параметры/Protocol, конкретные типы вместо Any.'
    ;;
  service-no-web)
    PATTERN='^[[:space:]]*(from fastapi|import fastapi)'
    FILTER='/services/|service\.py$'
    BASELINE="$SCRIPT_DIR/service_no_web_baseline.txt"
    LABEL='service-no-web: сервис-слой не импортирует web-фреймворк'
    HINT='HTTP-примитивы (Request/Depends/HTTPException) — в роутере. Сервис принимает id-параметры и бросает доменные исключения, не HTTP.'
    ;;
  no-grab-bag-module)
    # Любая строка = нарушение: правило имени файла, не содержимого. Новый
    # utils/misc/common/helpers.py (без темы) имеет count>0 -> hard fail; легаси в
    # baseline и не растёт. `_helpers.py` (с подчёркиванием) FILTER не матчит — разрешён.
    PATTERN='^'
    FILTER='/(utils|misc|common|helpers)\.py$'
    BASELINE="$SCRIPT_DIR/no_grab_bag_baseline.txt"
    LABEL='no-grab-bag-module: файлы-помойки utils/misc/common/helpers.py без темы запрещены'
    HINT='Имя модуля описывает ответственность: <topic>.py / <topic>_helpers.py / _helpers.py рядом с фичей.'
    ;;
  *)
    echo "unknown --rule: '${RULE}' (config-access|di-indirection|service-no-web|no-grab-bag-module)" >&2
    exit 2
    ;;
esac

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT" || exit 1

red=$(printf '\033[31m'); yellow=$(printf '\033[33m'); green=$(printf '\033[32m'); reset=$(printf '\033[0m')

# Прод-.py под $PY_SRC, без тестов. git ls-files рекурсивен; пути — от repo-root.
#
# Адаптация проекта (CQG «Применимость»): при LINT_PY_SRC=. в выборку попадает и
# сам harness (scripts/lint/*, okf_*, delivery_*, merge_guard). Эти скрипты по
# КОНТРАКТУ настраиваются через env (CQG §6 предписывает LINT_PY_SRC/STRICT/BASE),
# поэтому правило config-access к ним неприменимо — это не легаси в baseline, а
# другая область. Прод-код проекта (backend/app, cli) сканируется как обычно.
TOOLING_RE='^scripts/(lint/|okf_|delivery_|merge_guard)'
list_targets() {
  local out
  out=$(git ls-files "$PY_SRC/" 2>/dev/null \
    | grep -E '\.py$' \
    | grep -vE '/tests/|/test_[^/]*\.py$' \
    | grep -vE "$TOOLING_RE")
  [[ -n "${FILTER:-}" ]] && out=$(printf '%s\n' "$out" | grep -E "$FILTER")
  printf '%s\n' "$out"
}

# Число строк-нарушений в файле (grep -c всегда печатает число; 0 при отсутствии).
count_hits() { grep -cE "$PATTERN" "$1" 2>/dev/null; }

# Снимок для точного пути (awk-сравнение точной строки — корректно с пробелами в пути).
baseline_lookup() {
  [[ -f "$BASELINE" ]] || return 0
  awk -v p="$1" '
    /^[[:space:]]*#/ { next }
    /^[0-9]+:/ {
      n=$0; sub(/:.*/, "", n)
      path=$0; sub(/^[0-9]+:/, "", path)
      if (path == p) { print n; exit }
    }
  ' "$BASELINE"
}

# --- --generate: пересобрать baseline --------------------------------------
if [[ "$GENERATE" == "1" ]]; then
  tmp=$(mktemp)
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    hits=$(count_hits "$f")
    [[ "$hits" -gt 0 ]] && printf '%s:%s\n' "$hits" "$f" >>"$tmp"
  done < <(list_targets)
  {
    echo "# ${BASELINE##*/} — снимок grep-гейта. Генерируется --generate, НЕ руками."
    echo "# Правило: ${LABEL}"
    echo "# Формат: <count>:<path> (path от repo-root)."
    echo "# Ратчет вниз: файл проходит при count <= снимок; файл ВНЕ снимка (новый) — hard 0."
    LC_ALL=C sort -t: -k2 "$tmp"
  } >"$BASELINE"
  n=$(grep -c '^[0-9]' "$BASELINE" 2>/dev/null || echo 0)
  echo "${green}baseline пересобран${reset}: $BASELINE ($n файлов, правило ${RULE})"
  rm -f "$tmp"
  exit 0
fi

# --- проверка ---------------------------------------------------------------
violations=0
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  hits=$(count_hits "$f")
  [[ "$hits" -gt 0 ]] || continue
  snap=$(baseline_lookup "$f")
  allowed=${snap:-0}
  if [[ "$hits" -gt "$allowed" ]]; then
    violations=$((violations + 1))
    if [[ "$STRICT" == "1" ]]; then
      printf '%s  ✗  %s: %d нарушений (разрешено %d)%s\n' "$red" "$f" "$hits" "$allowed" "$reset"
    else
      printf '%s  ⚠  %s: %d нарушений (разрешено %d)%s\n' "$yellow" "$f" "$hits" "$allowed" "$reset"
    fi
  fi
done < <(list_targets)

if [[ "$violations" -gt 0 ]]; then
  hdr=$([[ "$STRICT" == "1" ]] && printf '%sERROR%s' "$red" "$reset" || printf '%sWARNING%s' "$yellow" "$reset")
  printf '\n%s: %d файл(ов) нарушают правило %s (вне baseline или сверх снимка).\n' "$hdr" "$violations" "$RULE"
  printf '%s\n' "$HINT"
  echo "Легаси-файл из baseline — ок до его чистки; новый код держим на нуле. Пересъём вниз: --generate."
  [[ "$STRICT" == "1" ]] && exit 1
fi
exit 0
