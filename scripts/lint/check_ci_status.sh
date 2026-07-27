#!/usr/bin/env bash
# ГЕЙТ СТАТУСА CI: «done закрывается зелёным CI-прогоном» (Delivery §10.4) —
# механически, а не на доверии.
#
# Зачем. Локальные гейты и merge_guard проверяют код ЛОКАЛЬНЫМИ инструментами и
# локальной версией Python. Расхождение с CI-окружением они не видят по
# построению — именно так две поставки были закрыты как done, пока все шесть
# прогонов CI были красными (mypy падал только на Python 3.12). Ни один гейт из
# scripts/lint не отвечал на вопрос «а что сказал неподделываемый прогон?».
#
# Что проверяет: у коммита, который сейчас в HEAD целевой ветки (или у HEAD
# текущей ветки, если она уже на remote), последний прогон workflow $CI_WORKFLOW
# завершился успешно.
#
# Настройка (env):
#   CI_WORKFLOW  — имя workflow (дефолт: quality)
#   CI_REF       — ветка/ref для проверки (дефолт: текущая ветка)
#   STRICT=0     — soft (warning, exit 0)
#
# Режимы:
#   check_ci_status.sh            # проверка; exit 1 если последний прогон красный
#   CI_REF=main check_ci_status.sh
#
# Границы: `gh` нет / не авторизован / прогонов ещё нет → это НЕ «зелено».
# Печатаем явный WARNING и выходим 0: гейт не может подтвердить, но и врать,
# что подтвердил, не должен. Внутри самого CI гейт себя не гоняет (GITHUB_ACTIONS).

set -uo pipefail

STRICT=${STRICT:-1}
CI_WORKFLOW=${CI_WORKFLOW:-quality}

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT" || exit 1

red=$(printf '\033[31m'); yellow=$(printf '\033[33m'); green=$(printf '\033[32m'); reset=$(printf '\033[0m')

if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
  echo "ci-status: пропущено внутри CI (это и есть тот самый прогон)"
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  printf '%sci-status: WARNING%s — нет `gh`, статус CI не проверен (не путать с «зелено»)\n' \
    "$yellow" "$reset" >&2
  exit 0
fi
if ! gh auth status >/dev/null 2>&1; then
  printf '%sci-status: WARNING%s — `gh` не авторизован (`gh auth login`), статус CI не проверен\n' \
    "$yellow" "$reset" >&2
  exit 0
fi

CI_REF=${CI_REF:-$(git rev-parse --abbrev-ref HEAD)}

read -r conclusion status sha url < <(
  gh run list --workflow "$CI_WORKFLOW" --branch "$CI_REF" --limit 1 \
    --json conclusion,status,headSha,url \
    -q '.[0] | "\(.conclusion // "none") \(.status // "none") \(.headSha // "none") \(.url // "none")"' \
    2>/dev/null
) || true
conclusion=${conclusion:-none}

case "$conclusion" in
  success)
    printf '%sci-status: OK%s — %s на %s зелёный (%s)\n' \
      "$green" "$reset" "$CI_WORKFLOW" "$CI_REF" "${sha:0:8}"
    exit 0
    ;;
  none)
    printf '%sci-status: WARNING%s — прогонов %s для %s не найдено; запушь ветку и дай CI отработать\n' \
      "$yellow" "$reset" "$CI_WORKFLOW" "$CI_REF" >&2
    exit 0
    ;;
esac

if [[ "$status" != "completed" ]]; then
  printf '%sci-status: WARNING%s — %s на %s ещё идёт (%s); дождись результата\n' \
    "$yellow" "$reset" "$CI_WORKFLOW" "$CI_REF" "$status" >&2
  exit 0
fi

printf '%sci-status: FAIL%s — последний %s на %s: %s\n' "$red" "$reset" "$CI_WORKFLOW" "$CI_REF" "$conclusion" >&2
printf '  %s\n' "$url" >&2
printf 'Красный CI = stop-gate (Delivery §3.3/§10.4): не мержить и не объявлять done.\n' >&2
[[ "$STRICT" == "0" ]] && exit 0
exit 1
