#!/usr/bin/env bash
# stop-on-red (Delivery §10.1 / A.11): агент не завершает ход на красных гейтах.
#
# Быстрые проверки (секунды) — фазовая дисциплина и полнота набора гейтов.
# Тяжёлое (pytest, pre-commit --all-files, smoke) сюда не тянем: это делает
# Verifier перед handoff и CI, иначе каждый Stop стоил бы минуту.
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || exit 0

PY="backend/.venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3 || command -v python)"
rc=0

if [[ -f scripts/delivery_check.py ]]; then
  "$PY" scripts/delivery_check.py >/tmp/hook_delivery.log 2>&1 || {
    echo "delivery_check failed — нельзя объявлять done:" >&2
    tail -5 /tmp/hook_delivery.log >&2
    rc=1
  }
fi

if [[ -f scripts/lint/check_gate_coverage.sh ]]; then
  bash scripts/lint/check_gate_coverage.sh >/tmp/hook_gates.log 2>&1 || {
    echo "gate-coverage failed — есть гейт без подключения:" >&2
    tail -5 /tmp/hook_gates.log >&2
    rc=1
  }
fi

exit "$rc"
