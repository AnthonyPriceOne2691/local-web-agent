#!/usr/bin/env bash
# Durable smoke oracles (Delivery §6.1). Без локальных LLM: инференс поднимается
# только по явному согласию человека, поэтому smoke проверяет «система жива»,
# а не качество ответов агента.
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PY="backend/.venv/bin/python"
API_PORT="${SMOKE_API_PORT:-8011}"   # не 8001: не мешаем рабочему серверу
FIXTURE_PORT=8908                    # store_checkout (Tier 3 handoff)
failed=0
pids=()

cleanup() {
  for pid in "${pids[@]:-}"; do
    [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

report() {  # id, status, note
  printf '%-4s %-5s %s\n' "$1" "$2" "${3:-}"
  [[ "$2" == "FAIL" ]] && failed=1
  return 0
}

wait_http() {  # url, tries
  for _ in $(seq 1 "${2:-40}"); do
    curl -sf -o /dev/null "$1" && return 0
    sleep 0.5
  done
  return 1
}

if [[ ! -x "$PY" ]]; then
  report S0 FAIL "no $PY — run: cd backend && uv sync --extra dev"
  exit 1
fi

# --- S1 behavior: полный сьют
if (cd backend && .venv/bin/python -m pytest -q >/tmp/smoke_pytest.log 2>&1); then
  report S1 PASS "$(tail -1 /tmp/smoke_pytest.log)"
else
  report S1 FAIL "see /tmp/smoke_pytest.log: $(tail -1 /tmp/smoke_pytest.log)"
fi

# --- S2 shape: гейт размера модулей (проектный инвариант, doc 18)
if out="$("$PY" scripts/check_module_size.py 2>&1)"; then
  report S2 PASS "$out"
else
  report S2 FAIL "$out"
fi

# --- S3 product: API поднимается и отвечает /health
if curl -sf -o /dev/null "http://127.0.0.1:${API_PORT}/health"; then
  report S3 PASS "already up on ${API_PORT}"
else
  (cd backend && exec ../"$PY" -m uvicorn app.main:app \
      --host 127.0.0.1 --port "$API_PORT" >/tmp/smoke_api.log 2>&1) &
  pids+=("$!")
  if wait_http "http://127.0.0.1:${API_PORT}/health"; then
    report S3 PASS "GET /health 200 on ${API_PORT}"
  else
    report S3 FAIL "API did not answer on ${API_PORT}; see /tmp/smoke_api.log"
  fi
fi

# --- S4 shape/build: фронт собирается (SKIP без node_modules — не признак поломки)
if [[ ! -d frontend/node_modules ]]; then
  report S4 SKIP "frontend/node_modules absent (npm install)"
elif (cd frontend && npm run build >/tmp/smoke_front.log 2>&1); then
  report S4 PASS "vite build ok"
else
  report S4 FAIL "see /tmp/smoke_front.log"
fi

# --- S5 product: фикстура Tier 3 (store_checkout) отдаётся
if curl -sf -o /dev/null "http://127.0.0.1:${FIXTURE_PORT}/"; then
  report S5 PASS "fixtures already up on ${FIXTURE_PORT}"
else
  "$PY" scripts/spike/fixtures_server.py >/tmp/smoke_fixtures.log 2>&1 &
  pids+=("$!")
  if wait_http "http://127.0.0.1:${FIXTURE_PORT}/"; then
    report S5 PASS "store_checkout served on ${FIXTURE_PORT}"
  else
    report S5 FAIL "fixture port ${FIXTURE_PORT} silent; see /tmp/smoke_fixtures.log"
  fi
fi

echo "smoke: $([[ $failed -eq 0 ]] && echo 'all green' || echo 'FAILURES above')"
exit "$failed"
