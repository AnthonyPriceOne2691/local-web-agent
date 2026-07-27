#!/usr/bin/env bash
# Ратчет над самими снимками: baseline может только ТАЯТЬ.
#
# Локальные гейты сравнивают код со снимком, но никто не сравнивает СНИМОК с его
# прошлой версией. `--generate` на грязном дереве легализует свежие нарушения —
# гейт зелёный, правило мертво. Этот скрипт закрывает дыру: рост счётчика или
# новая запись в baseline = fail.
#
# Форматы: "<count>:<path>" (per-path) и "<N>" (global). Комментарии (#) и
# секции ([baseline]/[exemption]) игнорируются.
#
# Настройка (env):
#   BASE                    — ref для сравнения (дефолт: origin/main)
#   LINT_DIR                — каталог снимков (дефолт: scripts/lint)
#   STRICT=0                — soft (warning, exit 0); в CI ЗАПРЕЩЁН
#   ALLOW_BASELINE_GROWTH=1 — осознанный рост (например, массовое переименование
#                             файлов); обязан быть виден и объяснён в PR
set -euo pipefail

BASE=${BASE:-origin/main}
STRICT=${STRICT:-1}
LINT_DIR=${LINT_DIR:-scripts/lint}
ALLOW_BASELINE_GROWTH=${ALLOW_BASELINE_GROWTH:-0}

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  echo "baseline-ratchet: ref '$BASE' недоступен (shallow clone? нужен fetch-depth: 0)" >&2
  exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Снимок -> "path<TAB>count". Global-число получает ключ __global__.
normalize() {
  awk '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    /^[[:space:]]*\[/ { next }
    {
      i = index($0, ":")
      if (i > 0) { c = substr($0, 1, i - 1); p = substr($0, i + 1) }
      else       { c = $0;                    p = "__global__" }
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", c)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", p)
      if (c ~ /^[0-9]+$/) print p "\t" c
    }' "$1"
}

violations=0
checked=0

shopt -s nullglob
for cur in "$LINT_DIR"/*_baseline.txt; do
  name=$(basename "$cur")
  if ! git show "$BASE:$cur" >"$tmp/old.raw" 2>/dev/null; then
    echo "  skip (нет в $BASE, новый гейт): $name"
    continue
  fi
  checked=$((checked + 1))
  normalize "$tmp/old.raw" | sort >"$tmp/old.tsv"
  normalize "$cur" | sort >"$tmp/new.tsv"

  if ! awk -F'\t' -v f="$name" '
      NR == FNR { old[$1] = $2; next }
      {
        if (!($1 in old)) {
          printf "  %s: НОВАЯ запись %s (count %s) — свежее нарушение легализовано\n", f, $1, $2
          bad = 1
        } else if (($2 + 0) > (old[$1] + 0)) {
          printf "  %s: %s вырос %s -> %s\n", f, $1, old[$1], $2
          bad = 1
        }
      }
      END { exit bad ? 1 : 0 }' "$tmp/old.tsv" "$tmp/new.tsv"; then
    violations=$((violations + 1))
  fi
done

if [[ "$violations" -eq 0 ]]; then
  echo "baseline-ratchet: OK ($checked снимков сверено с $BASE)"
  exit 0
fi

if [[ "$ALLOW_BASELINE_GROWTH" == "1" ]]; then
  echo "baseline-ratchet: рост разрешён ALLOW_BASELINE_GROWTH=1 — объясни в PR" >&2
  exit 0
fi
if [[ "$STRICT" == "0" ]]; then
  echo "baseline-ratchet: WARNING (STRICT=0) — $violations снимков выросли" >&2
  exit 0
fi
echo "baseline-ratchet: FAIL — снимок переснят ВВЕРХ в $violations файл(ах)." >&2
echo "Починка: убрать нарушения в коде, затем --generate/--tighten; снимок только вниз (§7)." >&2
exit 1
