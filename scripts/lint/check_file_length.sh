#!/usr/bin/env bash
# Длина файлов кода: prod <= 500 / tests <= 1000 строк, с baseline-ratchet.
#
# Одномоментный сплит всех god-файлов невозможен, поэтому вводится снимок текущих
# превышений (file_length_baseline.txt), который ТАЕТ по мере сплитов. Файл из
# baseline проходит при size <= снимок+HEADROOM; новый / вне baseline — hard 500/1000.
# Exemption-секция (файлы без шва для сплита) не тает.
#
#   Тип файла                 | Hard limit (вне baseline)
#   Production .py/.ts/.tsx    |    500
#   Tests (*/tests/*, *.test)  |   1000
#   (миграции / node_modules — без лимита; настрой is_excluded под себя)
#
# Настройка (env): MAX_LINES_PROD, MAX_LINES_TESTS, BASELINE_HEADROOM, EXEMPTION_HEADROOM.
#
# Режимы:
#   check_file_length.sh            # проверка; exit 1 при нарушении
#   check_file_length.sh --generate # пересобрать baseline из текущего дерева
#   check_file_length.sh --tighten  # опустить снимки ужавшихся baseline-файлов
#   STRICT=0 check_file_length.sh   # soft (warning, exit 0) — аварийно, виден в PR

MAX_LINES_PROD=${MAX_LINES_PROD:-500}
MAX_LINES_TESTS=${MAX_LINES_TESTS:-1000}
# Headroom к снимку baseline: точечные правки god-файла не блокируются до его сплита.
# Exemption получает больше (швов нет — рост правдоподобнее).
BASELINE_HEADROOM=${BASELINE_HEADROOM:-30}
EXEMPTION_HEADROOM=${EXEMPTION_HEADROOM:-50}
STRICT=${STRICT:-1}

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

# SCRIPT_DIR резолвим ДО cd в REPO_ROOT (BASH_SOURCE относителен cwd вызова).
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BASELINE="$SCRIPT_DIR/file_length_baseline.txt"

cd "$REPO_ROOT" || exit 1

red=$(printf '\033[31m')
yellow=$(printf '\033[33m')
green=$(printf '\033[32m')
reset=$(printf '\033[0m')

# --- helpers ---------------------------------------------------------------

# Пропустить путь (генерируемое / vendored). Настрой под свой проект.
is_excluded() {
  case "$1" in
    */migrations/*) return 0 ;;
    */node_modules/*) return 0 ;;
  esac
  return 1
}

# Тестовый файл? (feature-local tests/ тоже считаются.)
is_test() {
  case "$1" in
    *.test.ts | *.test.tsx | */tests/*) return 0 ;;
  esac
  return 1
}

# Файлы под exemption (нет шва для сплита — держим сознательно, лимит = снимок+EXEMPTION_HEADROOM).
# По умолчанию пусто; впиши сюда свои случаи через case-паттерны.
is_exempt_path() {
  case "$1" in
    __never_matches__) return 0 ;;
  esac
  return 1
}

base_limit_for() {
  if is_test "$1"; then echo "$MAX_LINES_TESTS"; else echo "$MAX_LINES_PROD"; fi
}

# Снимок baseline для точного пути (или пусто). Печатает "<snapshot>:<section>".
# awk-сравнение точной строки пути -> корректно с пробелами в пути.
baseline_lookup() {
  [[ -f "$BASELINE" ]] || return 0
  awk -v p="$1" '
    /^[[:space:]]*#/ { next }
    /^\[baseline\]/  { sect="baseline"; next }
    /^\[exemption\]/ { sect="exemption"; next }
    /^[0-9]+:/ {
      n=$0; sub(/:.*/, "", n)
      path=$0; sub(/^[0-9]+:/, "", path)
      if (path == p) { print n ":" sect; exit }
    }
  ' "$BASELINE"
}

collect_files() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
  else
    git ls-files '*.py' '*.ts' '*.tsx' 2>/dev/null
  fi
}

# --- --generate: пересобрать baseline из текущего дерева ---------------------

if [[ "${1:-}" == "--generate" ]]; then
  tmp_base=$(mktemp)
  tmp_exempt=$(mktemp)
  while IFS= read -r f; do
    is_excluded "$f" && continue
    [[ -f "$f" ]] || continue
    limit=$(base_limit_for "$f")
    lines=$(wc -l <"$f" | tr -d ' ')
    [[ "$lines" -gt "$limit" ]] || continue
    if is_exempt_path "$f"; then
      printf '%s:%s\n' "$lines" "$f" >>"$tmp_exempt"
    else
      printf '%s:%s\n' "$lines" "$f" >>"$tmp_base"
    fi
  done < <(git ls-files '*.py' '*.ts' '*.tsx' 2>/dev/null)

  {
    echo "# file_length_baseline.txt — снимок file-length гейта. Генерируется --generate, НЕ руками."
    echo "# Формат: <lines>:<path> (path в нотации git ls-files от repo-root)."
    echo "# [baseline] тает по мере сплитов (--tighten опускает снимки); файл проходит при size <= снимок+${BASELINE_HEADROOM}."
    echo "# [exemption] не тает (швов нет); лимит = снимок+${EXEMPTION_HEADROOM}, рост сверх — пере-ревью в PR."
    echo "# Вне обоих списков (в т.ч. любой новый файл) — hard ${MAX_LINES_PROD}/${MAX_LINES_TESTS}."
    echo "[baseline]"
    LC_ALL=C sort -t: -k2 "$tmp_base"
    echo "[exemption]"
    LC_ALL=C sort -t: -k2 "$tmp_exempt"
  } >"$BASELINE"

  rm -f "$tmp_base" "$tmp_exempt"
  n_base=$(grep -c '^[0-9]' "$BASELINE")
  echo "${green}baseline пересобран${reset}: $BASELINE ($n_base записей)"
  exit 0
fi

# --- проверка (и --tighten как её вариант) ----------------------------------

TIGHTEN=0
if [[ "${1:-}" == "--tighten" ]]; then
  TIGHTEN=1
  shift
  tmp_tight=$(mktemp)
fi

violations=0
tightened=0

check_file() {
  local file=$1
  local limit lines snap sect info allowed newsnap

  is_excluded "$file" && return
  [[ -f "$file" ]] || return

  limit=$(base_limit_for "$file")
  lines=$(wc -l <"$file" | tr -d ' ')

  info=$(baseline_lookup "$file")
  if [[ -n "$info" ]]; then
    snap=${info%%:*}
    sect=${info##*:}
    if [[ "$sect" == "exemption" ]]; then
      allowed=$((snap + EXEMPTION_HEADROOM))
    else
      allowed=$((snap + BASELINE_HEADROOM))
    fi
    # --tighten перезаписывает всю [baseline]-секцию из $tmp_tight, поэтому КАЖДАЯ
    # baseline-запись обязана сюда попасть — иначе неизменённые файлы молча выпадут.
    # Ратчет только ВНИЗ: снимок = min(строки, снимок); ужался <= лимита -> выпадает.
    if [[ "$TIGHTEN" == "1" && "$sect" == "baseline" ]]; then
      newsnap=$snap
      [[ "$lines" -lt "$snap" ]] && newsnap=$lines
      if [[ "$newsnap" -le "$limit" ]]; then
        tightened=$((tightened + 1))  # выпал из baseline (не пишем в tmp)
      else
        printf '%s:%s\n' "$newsnap" "$file" >>"$tmp_tight"
        [[ "$newsnap" -lt "$snap" ]] && tightened=$((tightened + 1))
      fi
      return
    fi
  else
    allowed=$limit
  fi

  if [[ "$lines" -gt "$allowed" ]]; then
    violations=$((violations + 1))
    if [[ "$STRICT" == "1" ]]; then
      printf '%s  ✗  %s: %d lines (> %d)%s\n' "$red" "$file" "$lines" "$allowed" "$reset"
    else
      printf '%s  ⚠  %s: %d lines (> %d)%s\n' "$yellow" "$file" "$lines" "$allowed" "$reset"
    fi
  fi
}

# --tighten перезаписывает всю [baseline]-секцию -> ОБЯЗАН видеть всё дерево, иначе
# усечёт baseline до переданных файлов. Обычная проверка уважает список файлов из хука.
while IFS= read -r f; do
  [[ -n "$f" ]] && check_file "$f"
done < <(if [[ "$TIGHTEN" == "1" ]]; then collect_files; else collect_files "$@"; fi)

if [[ "$TIGHTEN" == "1" ]]; then
  # Перезаписать [baseline]-секцию ужатыми снимками, [exemption] оставить как есть.
  # Шапку и exemption-секцию ЧИТАЕМ ДО редиректа: '>"$BASELINE"' усекает файл до
  # выполнения блока, поэтому чтение из него внутри {} вернуло бы пусто.
  header=$(grep '^#' "$BASELINE")
  exempt_section=$(awk '/^\[exemption\]/{p=1} p' "$BASELINE")
  {
    printf '%s\n' "$header"
    echo "[baseline]"
    LC_ALL=C sort -t: -k2 "$tmp_tight" 2>/dev/null
    [[ -n "$exempt_section" ]] && echo "$exempt_section"
  } >"$BASELINE"
  rm -f "$tmp_tight"
  echo "${green}--tighten: обновлено снимков/выпало из baseline: $tightened${reset}"
  exit 0
fi

if [[ "$violations" -gt 0 ]]; then
  hdr=$([[ "$STRICT" == "1" ]] && printf '%sERROR%s' "$red" "$reset" || printf '%sWARNING%s' "$yellow" "$reset")
  printf '\n%s: %d файл(ов) превышают лимит длины (вне baseline/exemption).\n' "$hdr" "$violations"
  echo "Лимиты: prod ${MAX_LINES_PROD} / tests ${MAX_LINES_TESTS}. Новый код держим под лимитом;"
  echo "баг-фикс god-файла из baseline — ок до его сплита."
  [[ "$STRICT" == "1" ]] && exit 1
fi

exit 0
