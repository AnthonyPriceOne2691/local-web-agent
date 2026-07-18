# Phase 0 spike — benchmark scripts

Спецификация и exit-критерии: [docs/19-phase0-benchmark-results.md](../../docs/19-phase0-benchmark-results.md) · план: [docs/06-mvp-phases.md](../../docs/06-mvp-phases.md).

## Setup (однократно)

```bash
cd local-web-agent
uv venv .venv
uv pip install -p .venv playwright httpx pyyaml tldextract
.venv/bin/playwright install chromium
ollama serve &          # если не запущен
# модели: qwen2.5:14b-instruct, deepseek-r1:14b, qwen2.5vl:7b (см. docs/07)
```

## Part A — crawl (`benchmark_crawl.py`)

```bash
cd scripts/spike

# smoke без LLM (плумбинг: браузер, observer, queue, contract-lite, regex)
../../.venv/bin/python3 benchmark_crawl.py --tasks tasks.yaml --dry-run --rate-limit-ms 100

# полный прогон fixture-задач (hints mode)
../../.venv/bin/python3 benchmark_crawl.py --tasks tasks.yaml --mode hints

# A/B task #7: hints vs llm-only на GEO-слаге (задача 6)
../../.venv/bin/python3 benchmark_crawl.py --tasks tasks.yaml --task-id 6 --mode hints
../../.venv/bin/python3 benchmark_crawl.py --tasks tasks.yaml --task-id 6 --mode llm-only

# A/B task #10: другая nav-модель тем же манифестом
../../.venv/bin/python3 benchmark_crawl.py --tasks tasks.yaml --model qwen3:14b

# реальные сайты (задачи 3–5, сеть)
../../.venv/bin/python3 benchmark_crawl.py --tasks tasks.yaml --include-real --task-id 3

# sustained/thermal (task #11): один и тот же таск 3 раза подряд
for i in 1 2 3; do ../../.venv/bin/python3 benchmark_crawl.py --tasks tasks.yaml --task-id 2; done
```

Результаты — JSONL в `scripts/spike/results/` (шаги, LLM-метрики eval_count/tok_s, авто-success по `expect`).

## Юнит-проверки и сводка (без LLM)

```bash
../../.venv/bin/python3 test_spike_units.py      # 37 проверок чистых функций (URL-нормализация, RU/EN intent, очередь, contract-lite)
../../.venv/bin/python3 summarize_results.py     # все JSONL из results/ → markdown-таблицы для doc 19
```

Доп. флаги краулера: `--screenshots auto|always|never` (auto = SPA fallback capture при пустом DOM),
`--vision` + `--vision-model` (VLM-мерж скриншотов в синтез — task 8b; **поднимает модель**).
Robots.txt + Crawl-delay соблюдаются на real-сайтах автоматически; same-site = registrable domain (tldextract, офлайн PSL).

## Part B — vision (`benchmark_vision.py`)

```bash
# 1) сгенерировать fixture-PNG V1–V5
../../.venv/bin/python3 make_vision_fixtures.py

# 2) прогнать VLM (+ повторы для p50/p95)
../../.venv/bin/python3 benchmark_vision.py --model qwen2.5vl:7b --repeat 3

# кандидаты-фоллбеки (doc 14)
../../.venv/bin/python3 benchmark_vision.py --model gemma3:12b
```

Авто-чек рубрики — подсказка; финальную оценку V1–V5 фиксировать руками в doc 19.

## Fixture-сайты

`fixtures_server.py` поднимает каждый сайт из `tests/fixtures/sites/` на своём порту
(8901+, extensionless-пути → .html). Запускается автоматически из `benchmark_crawl.py --tasks`;
вручную: `python3 fixtures_server.py`.

| Сайт | Для чего |
|------|----------|
| simple_contact | task 1: телефон на /contact |
| pricing | task 2/2b: цена Pro (2b — RU-формулировка, тест intent RU) |
| geo_kontak | task 6: контакт только на **несвязанном** /page/kontak — A/B слаг-словаря |
| spa_price | task 8: цена в CSS `::after` — DOM не видит, скриншот видит |

## Что заполнить в doc 19 после прогонов

- Таблицы Part A (pages/wall/success) + Navigation model A/B + Sustained/thermal
- Part B: модели × (rubric, valid JSON %, p50/p95)
- Latency/Memory (RAM — смотреть `ollama ps` + Activity Monitor в пиках)
- Decisions: D-1..D-3, D-6b/D-6c → закрыть по результатам
