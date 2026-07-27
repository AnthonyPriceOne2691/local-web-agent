# Durable smoke oracles

Repo-level проверки «система жива» (product oracles, Delivery §6.1). Гоняются
через `run.sh`; **без локальных LLM** — инференс сюда не тянем (32 GB RAM,
модель поднимается только по явному согласию человека).

| ID | Command | Expected | Timeout |
|---|---|---|---|
| S1 | `cd backend && .venv/bin/python -m pytest -q` | exit 0 (191 тест) | 300s |
| S2 | `backend/.venv/bin/python scripts/check_module_size.py` | exit 0, «all modules ≤ 500 LOC» | 30s |
| S3 | API поднимается на 127.0.0.1 и `GET /health` → 200 (`app.main:app`, uvicorn) | HTTP 200 | 60s |
| S4 | `cd frontend && npm run build` | exit 0 (tsc + vite) | 180s |
| S5 | fixtures-сервер поднимается, `GET http://127.0.0.1:8908/` → 200 (фикстура Tier 3) | HTTP 200 | 60s |

S3/S5 поднимают процессы на localhost и гасят их за собой. S4 требует
установленных node_modules — при их отсутствии шаг помечается SKIP (не FAIL):
отсутствующая сборка фронта — не признак сломанной системы в backend-поставке.
