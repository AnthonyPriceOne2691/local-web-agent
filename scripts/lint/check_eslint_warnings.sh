#!/usr/bin/env bash
# ESLint warning-count ратчет (фронт). Глобальный счётчик предупреждений.
#
# Per-file eslint-хук блокирует только errors (без --max-warnings=0), поэтому warnings
# росли бы молча. Здесь: полный прогон eslint по фронт-src, снимок суммы warnings в
# eslint_warnings_baseline.txt; гейт падает, если счётчик ВЫРОС. Правишь файл с
# warnings -> счисти часть и пере-сними вниз (--generate). Только вниз.
#
# Бинарь eslint ищется в node_modules фронта, затем в PATH. Нет бинаря — гейт не
# блокирует, только предупреждает (свежий clone без npm ci). Нет самого каталога
# фронта — тоже skip: backend-only проект не должен падать на фронт-гейте.
#
# Настройка (env): LINT_FE_DIR — фронт-каталог с package.json/src (дефолт: frontend)
#
# Режимы:
#   check_eslint_warnings.sh             # проверка; exit 1 при росте
#   check_eslint_warnings.sh --generate  # пере-снять baseline (текущее число warnings)
#   STRICT=0 check_eslint_warnings.sh    # soft (warning, exit 0)

set -uo pipefail

STRICT=${STRICT:-1}
FE_DIR=${LINT_FE_DIR:-frontend}
GENERATE=0
[[ "${1:-}" == "--generate" ]] && GENERATE=1

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BASELINE="$SCRIPT_DIR/eslint_warnings_baseline.txt"

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

red=$(printf '\033[31m'); yellow=$(printf '\033[33m'); green=$(printf '\033[32m'); reset=$(printf '\033[0m')

# Каталога фронта нет (backend-only проект / другой layout) — не наша забота, skip.
# Без этой проверки `cd` печатал сырую ошибку шелла и ронял коммит на exit 1.
if [[ ! -d "$REPO_ROOT/$FE_DIR" ]]; then
  printf '%s⚠ нет каталога фронта (%s) — eslint warning-ратчет пропущен. Настройка: LINT_FE_DIR%s\n' \
    "$yellow" "$FE_DIR" "$reset"
  exit 0
fi
cd "$REPO_ROOT/$FE_DIR" || exit 1

if [[ -x "node_modules/.bin/eslint" ]]; then
  ESLINT="node_modules/.bin/eslint"
elif command -v eslint >/dev/null 2>&1; then
  ESLINT="eslint"
else
  printf '%s⚠ eslint не найден — warning-ратчет пропущен. Установка: npm ci%s\n' "$yellow" "$reset"
  exit 0
fi

# Полный прогон по src: сумма warnings из JSON-репорта. Errors здесь не считаем —
# их блокирует per-file eslint-хук на каждом коммите.
current_warnings() {
  "$ESLINT" src --format json 2>/dev/null \
    | node -e 'let d="";process.stdin.on("data",c=>d+=c).on("end",()=>{try{const r=JSON.parse(d);console.log(r.reduce((a,f)=>a+f.warningCount,0));}catch{console.log("");}})'
}

count=$(current_warnings)
if [[ -z "$count" ]]; then
  printf '%sERROR%s: не удалось посчитать eslint warnings (пустой/битый JSON-вывод eslint).\n' "$red" "$reset"
  exit 1
fi

if [[ "$GENERATE" == "1" ]]; then
  {
    echo "# eslint_warnings_baseline.txt — снимок warning-count ратчета. Генерируется --generate, НЕ руками."
    echo "# Одно число = сумма ESLint warnings полного прогона фронт-src (errors гейтит сам eslint-хук)."
    echo "# Гейт падает при РОСТЕ; счистил предупреждения — пере-снять вниз (--generate). Вверх не переснимается."
    echo "$count"
  } >"$BASELINE"
  echo "${green}eslint warnings baseline пересобран${reset}: $count"
  exit 0
fi

baseline=$(grep -m1 -oE '^[0-9]+' "$BASELINE" 2>/dev/null)
if [[ -z "$baseline" ]]; then
  printf '%sERROR%s: baseline не найден (%s) — сними снимок: --generate\n' "$red" "$reset" "$BASELINE"
  exit 1
fi

if [[ "$count" -gt "$baseline" ]]; then
  if [[ "$STRICT" == "1" ]]; then
    printf '%sERROR%s: ESLint warnings выросли: %d (baseline %d).\n' "$red" "$reset" "$count" "$baseline"
    echo "Новые предупреждения не проходят: почини правило (частые — max-lines-per-function, react-hooks/exhaustive-deps)."
    echo "Рост оправдан (редко) — пере-снять снимок: --generate."
    exit 1
  fi
  printf '%sWARNING%s: ESLint warnings выросли: %d (baseline %d).\n' "$yellow" "$reset" "$count" "$baseline"
elif [[ "$count" -lt "$baseline" ]]; then
  echo "${yellow}warnings уменьшились ($count < baseline $baseline) — ужми снимок: --generate${reset}"
fi
exit 0
