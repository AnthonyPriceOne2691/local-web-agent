#!/usr/bin/env bash
# Мерж через гейты, а не кнопкой. Замена required status checks там, где их нет
# (бесплатный тариф, приватный репо, не-GitHub хостинг).
#
# Отличие от pre-push: проверяется СЛИТОЕ состояние — то, что реально окажется в
# целевой ветке. Ветка может быть зелёной, а после слияния с ушедшим вперёд main
# — красной; required checks в режиме strict ловят именно это.
#
# Механика: отдельный worktree на целевой ветке -> merge --no-commit -> прогон
# гейтов там -> мерж в основном клоне только при зелёном. Рабочее дерево не
# трогается, конфликт не оставляет репо в merge-состоянии.
#
# Usage:
#   scripts/merge_guard.sh <source-branch> [target-branch]   # default target: main
#   DRY_RUN=1 scripts/merge_guard.sh feat/x                  # только проверить
set -euo pipefail

SOURCE=${1:?usage: merge_guard.sh <source-branch> [target-branch]}
TARGET=${2:-main}
DRY_RUN=${DRY_RUN:-0}

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

red=$(printf '\033[31m'); green=$(printf '\033[32m'); yellow=$(printf '\033[33m'); reset=$(printf '\033[0m')
die() { printf '%smerge_guard: %s%s\n' "$red" "$1" "$reset" >&2; exit 1; }

# Интерпретатор резолвим, а не хардкодим: на macOS и в свежих дистрибутивах
# бинаря `python` нет вовсе, есть только `python3` (или venv проекта).
PY=${PYTHON:-}
if [[ -z "$PY" ]]; then
  for cand in backend/.venv/bin/python .venv/bin/python python3 python; do
    if [[ -x "$cand" ]] || command -v "$cand" >/dev/null 2>&1; then PY=$cand; break; fi
  done
fi
[[ -n "$PY" ]] || die "не найден python (задай PYTHON=/path/to/python)"

git rev-parse --verify --quiet "$SOURCE" >/dev/null || die "нет ветки '$SOURCE'"
git rev-parse --verify --quiet "$TARGET" >/dev/null || die "нет ветки '$TARGET'"
[[ -z "$(git status --porcelain)" ]] || die "рабочее дерево грязное — закоммить или спрячь правки"

WT=$(mktemp -d)/merge-check
cleanup() { git worktree remove --force "$WT" >/dev/null 2>&1 || true; }
trap cleanup EXIT

printf 'merge_guard: проверяю %s -> %s на слитом состоянии\n' "$SOURCE" "$TARGET"
git worktree add --quiet --detach "$WT" "$TARGET" || die "не смог создать worktree"

# Мерж в worktree КОММИТИТСЯ, а не остаётся в индексе (--no-commit).
# Иначе гейты, считающие дифф по коммитам (`merge-base..HEAD`: delivery_check
# --diff-base, okf_sync_gate --base), видят ПУСТОЙ дифф и пропускают всё:
# HEAD ещё равен $TARGET, а изменения лежат в индексе. Worktree одноразовый,
# коммит в нём никуда не уезжает.
if ! git -C "$WT" merge --no-ff --no-edit "$SOURCE" >/dev/null 2>&1; then
  git -C "$WT" merge --abort >/dev/null 2>&1 || true
  die "конфликт при слиянии $SOURCE в $TARGET — разреши его в ветке и повтори"
fi

# Адаптация проекта: тулчейн (backend/.venv, frontend/node_modules) gitignored,
# поэтому в свежем worktree его нет, и хуки, зовущие `backend/.venv/bin/python`,
# падают по окружению — а не по качеству кода. Симлинкуем тулчейн из основного
# клона: проверяем КОД слитого состояния теми же инструментами, что локально.
# (В CI этого не нужно: там `uv sync` ставит окружение с нуля.)
MAIN_ROOT=$(pwd)
for tool in backend/.venv frontend/node_modules; do
  if [[ -e "$MAIN_ROOT/$tool" && ! -e "$WT/$tool" ]]; then
    mkdir -p "$WT/$(dirname "$tool")"
    ln -s "$MAIN_ROOT/$tool" "$WT/$tool"
  fi
done

# Гейты гоняются в слитом дереве. Каждый — только если он в проекте есть:
# стек разворачивается послойно, и отсутствующий слой не должен ронять мерж.
failed=()
run_gate() {
  local label=$1; shift
  printf '  → %s\n' "$label"
  if ( cd "$WT" && "$@" >/tmp/merge_guard_out 2>&1 ); then
    printf '    %sOK%s\n' "$green" "$reset"
  else
    printf '    %sFAIL%s\n' "$red" "$reset"; sed -n '1,15p' /tmp/merge_guard_out
    failed+=("$label")
  fi
}

command -v pre-commit >/dev/null 2>&1 && [[ -f .pre-commit-config.yaml ]] \
  && run_gate "pre-commit (all files)" pre-commit run --all-files
[[ -f scripts/lint/check_baseline_ratchet.sh ]] \
  && run_gate "baseline ratchet" env BASE="$TARGET" bash scripts/lint/check_baseline_ratchet.sh
[[ -f scripts/delivery_check.py ]] \
  && run_gate "delivery gate + breakers" "$PY" scripts/delivery_check.py --diff-base "$TARGET"
[[ -f scripts/okf_sync_gate.py ]] \
  && run_gate "canon sync" "$PY" scripts/okf_sync_gate.py --base "$TARGET"
[[ -f delivery/evals/smoke/run.sh ]] \
  && run_gate "smoke evals" bash delivery/evals/smoke/run.sh
# Последним — статус неподделываемого прогона. Локальные гейты выше проверяют код
# ЛОКАЛЬНЫМИ версиями инструментов; расхождение с CI-окружением видит только сам
# CI (Delivery §10.4). Гоняется в основном клоне, а не в worktree: ему нужен git
# remote и `gh`, а не слитое дерево.
#
# Проверяем прогон ИСХОДНОЙ ветки, а не целевой: на PR GitHub гоняет workflow на
# merge-состоянии — ровно то, что нужно перед мержем. Проверять target было бы
# вредно: красный main блокировал бы мерж собственного фикса, а следит за main
# отдельный workflow main-guard.
if [[ -f scripts/lint/check_ci_status.sh ]]; then
  printf '  → ci status (%s)\n' "$SOURCE"
  if CI_REF="$SOURCE" bash scripts/lint/check_ci_status.sh >/tmp/merge_guard_ci 2>&1; then
    printf '    %sOK%s\n' "$green" "$reset"; sed -n '1,3p' /tmp/merge_guard_ci
  else
    printf '    %sFAIL%s\n' "$red" "$reset"; sed -n '1,6p' /tmp/merge_guard_ci
    failed+=("ci status")
  fi
fi

if (( ${#failed[@]} )); then
  printf '\n%smerge_guard: МЕРЖ ЗАБЛОКИРОВАН — красные гейты: %s%s\n' "$red" "${failed[*]}" "$reset" >&2
  printf 'Починить в ветке %s и повторить. Не мержить кнопкой в обход.\n' "$SOURCE" >&2
  exit 1
fi

if [[ "$DRY_RUN" == "1" ]]; then
  printf '\n%smerge_guard: всё зелено (DRY_RUN=1, мерж не выполнен)%s\n' "$green" "$reset"
  exit 0
fi

git checkout --quiet "$TARGET"
git merge --no-ff --no-edit "$SOURCE"
printf '\n%smerge_guard: %s слит в %s после зелёных гейтов%s\n' "$green" "$SOURCE" "$TARGET" "$reset"
