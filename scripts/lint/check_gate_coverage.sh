#!/usr/bin/env bash
# МЕТА-ГЕЙТ: каждый гейт обязан быть ПОДКЛЮЧЁН, а не просто существовать.
#
# Зачем. `pre-commit run --all-files` доказывает исправность хуков, ПЕРЕЧИСЛЕННЫХ
# в конфиге, и молчит о недостающих: невключённый гейт неотличим от проходящего.
# Реальный случай (2026-07-27): скрипт jscpd был извлечён и даже адаптирован под
# язык проекта, но не вписан в .pre-commit-config.yaml — приёмка показала 7/7
# зелёных, потому что проверяла «работает ли подключённое», а не «подключено ли
# всё требуемое». Этот гейт закрывает класс ошибки, а не тот один случай.
#
# Что проверяет (в обе стороны):
#   1. Каждый скрипт в $LINT_DIR упомянут хотя бы в одном месте принуждения
#      (pre-commit / CI-workflow / merge_guard / Makefile / justfile).
#   2. Каждый путь `scripts/...`, упомянутый в конфигах, существует на диске
#      (ловит опечатку и удалённый скрипт — «хук есть, гейта нет»).
#
# Осознанно неподключённые перечисляются в is_exempt() С ПРИЧИНОЙ. Отсутствие
# в конфиге должно быть решением в коде, а не пробелом.
#
# Настройка (env): LINT_DIR (дефолт scripts/lint), STRICT=0 — soft.
#
# Режимы:
#   check_gate_coverage.sh          # проверка; exit 1 при непокрытом гейте
#   STRICT=0 check_gate_coverage.sh # soft (warning, exit 0)

set -uo pipefail

STRICT=${STRICT:-1}
LINT_DIR=${LINT_DIR:-scripts/lint}

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT" || exit 1

red=$(printf '\033[31m'); yellow=$(printf '\033[33m'); green=$(printf '\033[32m'); reset=$(printf '\033[0m')

# Осознанно НЕ подключённые — причина ОБЯЗАТЕЛЬНА и печатается на каждом прогоне.
# Не список имён в комментарии: причина — это состояние проекта, которое меняется
# («тестов нет», «нет TS»), и когда оно изменится, устаревшее исключение должно
# быть видно глазами на каждом прогоне, а не лежать в коде.
# `case`, а не `declare -A`: на macOS системный bash 3.2 без ассоциативных массивов.
#
# Исключение здесь часто означает `*-oracles: weak` в delivery/active/STATUS.md
# (Delivery §3.1) — не забудь отметить там же.
#
# Этот файл в исключения НЕ вносится: мета-гейт, который сам никем не вызывается,
# — ровно та дыра, от которой он защищает, на уровень выше.
not_wired_reason() {
  case "$1" in
    check_diff_coverage.sh)
      echo "ручной DoD-шаг (§3.5): полный сьют — минуты; в CI подключён отдельным шагом" ;;
    *) return 1 ;;
  esac
}

# nullglob убирает нераскрывшиеся ГЛОБЫ, но не литеральные имена: каждый
# фиксированный путь проверяется через [[ -f ]], иначе список «мест принуждения»
# никогда не бывает пустым и проверка ниже становится мёртвым кодом.
shopt -s nullglob
CONFIGS=()
for fixed in .pre-commit-config.yaml .gitlab-ci.yml scripts/merge_guard.sh Makefile justfile; do
  [[ -f "$fixed" ]] && CONFIGS+=("$fixed")
done
CONFIGS+=(.github/workflows/*.yml .github/workflows/*.yaml)

if (( ${#CONFIGS[@]} == 0 )); then
  printf '%sERROR%s: не найдено ни одного места принуждения (.pre-commit-config.yaml / CI).\n' "$red" "$reset" >&2
  printf 'Гейты без подключения не работают — см. §5 шаги 5 и 8.\n' >&2
  exit 1
fi

# git ls-files, а не файловый glob: считаем только ОТСЛЕЖИВАЕМЫЕ файлы — так же,
# как остальные гейты CQG (§4). Локальный черновик в рабочем дереве гейтом не
# является, и ругаться на него — ложное срабатывание.
gates=()
while IFS= read -r p; do
  [[ -n "$p" ]] && gates+=("$p")
done < <(git ls-files "$LINT_DIR/check_*.sh" "$LINT_DIR/check_*.py")

# Ноль гейтов — ОШИБКА, а не «пропуск». Этот скрипт лежит в $LINT_DIR, значит CQG
# разворачивается; пустой список означает «скрипты не закоммичены» или «сломан
# LINT_DIR». Мягкий пропуск здесь был бы тем самым тихо-зелёным проходом, ради
# которого гейт и написан.
if (( ${#gates[@]} == 0 )); then
  printf '%sERROR%s: в %s нет отслеживаемых гейт-скриптов (check_*.sh|py).\n' "$red" "$reset" "$LINT_DIR" >&2
  printf 'Только что создал? `git add %s` — untracked не считается.\n' "$LINT_DIR" >&2
  exit 1
fi

unwired=()
exempted=0
for path in "${gates[@]}"; do
  base=$(basename "$path")
  if reason=$(not_wired_reason "$base"); then
    printf '  ○ %-30s не подключён осознанно: %s\n' "$base" "$reason"
    exempted=$((exempted + 1))
    continue
  fi
  # -F: имя содержит точку, как regex она матчила бы лишний символ.
  if ! grep -qsF -- "$base" "${CONFIGS[@]}"; then
    unwired+=("$base")
  fi
done

# Обратная сторона: конфиг ссылается на скрипт, которого нет.
missing=()
while IFS= read -r ref; do
  [[ -n "$ref" ]] || continue
  [[ -e "$ref" ]] || missing+=("$ref")
done < <(grep -ohsE 'scripts/[A-Za-z0-9_/.-]+\.(sh|py)' "${CONFIGS[@]}" | sort -u)

if (( ${#unwired[@]} == 0 && ${#missing[@]} == 0 )); then
  printf '%sgate-coverage: OK%s — %d гейт(ов), подключено %d, осознанно нет %d (%d конфиг(ов))\n' \
    "$green" "$reset" "${#gates[@]}" "$(( ${#gates[@]} - exempted ))" "$exempted" "${#CONFIGS[@]}"
  exit 0
fi

# Циклы под защитой (( ${#arr[@]} )): в bash 3.2 — штатном на macOS — раскрытие
# пустого массива "${arr[@]}" падает по `set -u`, даже если массив объявлен.
if (( ${#unwired[@]} )); then
  for b in "${unwired[@]}"; do
    printf '%s  ✗  %s: скрипт есть, но НЕ подключён (pre-commit / CI / merge_guard)%s\n' "$red" "$b" "$reset" >&2
  done
fi
if (( ${#missing[@]} )); then
  for m in "${missing[@]}"; do
    printf '%s  ✗  %s: упомянут в конфиге, но файла нет%s\n' "$red" "$m" "$reset" >&2
  done
fi

if [[ "$STRICT" == "0" ]]; then
  printf '%sgate-coverage: WARNING (STRICT=0)%s\n' "$yellow" "$reset" >&2
  exit 0
fi
printf '\n%sERROR%s: гейт без подключения = гейта нет. Впиши его в `.pre-commit-config.yaml`\n' "$red" "$reset" >&2
printf 'или в CI-шаг, либо объяви исключение с причиной в not_wired_reason() этого скрипта.\n' >&2
printf 'Сверься с таблицей §3 построчно — не собирай конфиг «по смыслу».\n' >&2
exit 1
