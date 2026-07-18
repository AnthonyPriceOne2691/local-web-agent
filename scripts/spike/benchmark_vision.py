#!/usr/bin/env python3
"""Phase 0 spike — Part B: vision benchmark (doc 19, doc 23).

Fixture PNG → Ollama VLM → VisionInsight-lite JSON. Меряет latency p50/p95,
valid-JSON rate, и печатает чеклист рубрики V1–V5 для ручной оценки.

Примеры:
  python3 benchmark_vision.py                          # qwen2.5vl:7b, все фикстуры
  python3 benchmark_vision.py --model gemma3:12b       # кандидат-сравнение
  python3 benchmark_vision.py --repeat 3               # для p50/p95
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
PNG_DIR = REPO / "tests" / "fixtures" / "screenshots"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
OLLAMA = "http://localhost:11434"

VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "screen_status": {"type": "string", "enum": ["ok", "blank", "obstructed", "error_page", "unknown"]},
        "extracted": {"type": "array", "items": {
            "type": "object",
            "properties": {"key": {"type": "string"}, "value": {"type": "string"},
                           "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
            "required": ["key", "value"]}},
        "design": {"type": "object", "properties": {
            "colors_approx": {"type": "array", "items": {"type": "string"}},
            "layout": {"type": "string"},
            "responsive_note": {"type": "string"}}},
    },
    "required": ["description", "screen_status", "extracted"],
}

VISION_SYSTEM = (
    "You analyse a webpage screenshot. Return JSON: description (1-2 sentences), "
    "screen_status (ok | blank | obstructed — if a cookie/consent overlay or modal blocks the page | error_page | unknown), "
    "extracted (task-relevant facts VISIBLE in the image: prices, button labels, contacts; [] if none), "
    "design {colors_approx: 2-4 hex estimates, layout: short pattern description, responsive_note}. "
    "Never invent text that is not visible. If the page is obstructed, do not report business facts. JSON only."
)

# Рубрика doc 19 Part B: что обязано быть в ответе (авто-подсказки; финальная оценка ручная)
RUBRIC: dict[str, dict] = {
    "pricing_desktop": {"task": "What is the price of the Pro plan and the CTA label?",
                        "must_contain": ["29", "trial"], "status": "ok"},
    "spa_empty_dom":   {"task": "What plan and monthly price are shown?",
                        "must_contain": ["49"], "status": "ok"},
    "cookie_wall":     {"task": "What products and prices are on this page?",
                        "must_contain": [], "status": "obstructed",
                        "must_not_invent": ["$", "price"]},
    "home_mobile":     {"task": "Describe the mobile layout and navigation of this page",
                        "must_contain": ["hamburger|menu|☰|burger"], "status": "ok"},
    "design_home":     {"task": "Describe the design: brand colors, hero, layout pattern",
                        "must_contain": ["#", "hero|grid|column"], "status": "ok"},
}


def check_rubric(name: str, insight: dict) -> tuple[bool, list[str]]:
    """Автопроверка-подсказка; spec doc 19 требует и ручного взгляда."""
    spec = RUBRIC[name]
    notes, ok = [], True
    blob = json.dumps(insight, ensure_ascii=False).casefold()
    if insight.get("screen_status") != spec["status"]:
        ok = False
        notes.append(f"status={insight.get('screen_status')} (want {spec['status']})")
    for pattern in spec["must_contain"]:
        if not re.search(pattern.casefold(), blob):
            ok = False
            notes.append(f"missing: {pattern}")
    if spec.get("must_not_invent") and insight.get("screen_status") == "obstructed":
        invented = [f["value"] for f in insight.get("extracted", [])
                    if any(m in str(f.get("value", "")).casefold() for m in spec["must_not_invent"])]
        if invented:
            ok = False
            notes.append(f"invented business facts on obstructed page: {invented}")
    return ok, notes


def percentile(vals: list[float], pct: float) -> float:
    if not vals:
        return 0.0
    vals = sorted(vals)
    return vals[min(len(vals) - 1, max(0, round(pct / 100 * (len(vals) - 1))))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5vl:7b")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--fixture", action="append", help="only these fixtures (repeatable)")
    args = parser.parse_args()

    pngs = sorted(PNG_DIR.glob("*.png"))
    if args.fixture:
        pngs = [p for p in pngs if p.stem in args.fixture]
    if not pngs:
        sys.exit(f"No PNGs in {PNG_DIR} — run make_vision_fixtures.py first")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"vision_{time.strftime('%Y%m%d_%H%M%S')}_{args.model.replace(':', '_').replace('/', '_')}.jsonl"
    latencies, valid, passed = [], 0, 0
    total = 0

    with httpx.Client(timeout=180) as client:
        for png in pngs:
            spec = RUBRIC.get(png.stem, {"task": "Describe this page", "must_contain": [], "status": "ok"})
            b64 = base64.b64encode(png.read_bytes()).decode()
            for i in range(args.repeat):
                total += 1
                t0 = time.perf_counter()
                try:
                    r = client.post(f"{OLLAMA}/api/chat", json={
                        "model": args.model, "stream": False, "format": VISION_SCHEMA,
                        "keep_alive": "10m",
                        "messages": [{"role": "system", "content": VISION_SYSTEM},
                                     {"role": "user", "content": f"TASK: {spec['task']}", "images": [b64]}],
                        "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1200},
                    })
                    r.raise_for_status()
                    data = r.json()
                    wall = time.perf_counter() - t0
                    latencies.append(wall)
                    try:
                        insight = json.loads(data["message"]["content"])
                        valid += 1
                    except (json.JSONDecodeError, KeyError):
                        insight = {"parse_error": True, "raw": data.get("message", {}).get("content", "")[:400]}
                    ok, notes = check_rubric(png.stem, insight) if png.stem in RUBRIC else (None, [])
                    passed += bool(ok)
                    rec = {"fixture": png.stem, "run": i, "model": args.model, "wall_s": round(wall, 2),
                           "eval_count": data.get("eval_count"),
                           "tok_s": round(data["eval_count"] / (data["eval_duration"] / 1e9), 1)
                                    if data.get("eval_duration") else None,
                           "rubric_ok": ok, "rubric_notes": notes, "insight": insight}
                except httpx.HTTPError as exc:
                    wall = time.perf_counter() - t0
                    rec = {"fixture": png.stem, "run": i, "model": args.model,
                           "wall_s": round(wall, 2), "error": str(exc)[:300]}
                with out.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                mark = {True: "✅", False: "❌", None: "·"}[rec.get("rubric_ok")]
                print(f"{mark} {png.stem:<18} run{i} {rec['wall_s']:>6}s  "
                      f"{'; '.join(rec.get('rubric_notes', []))[:90]}", file=sys.stderr)

    n_fixtures = len({p.stem for p in pngs})
    print(f"\nmodel={args.model}  fixtures={n_fixtures}  calls={total}", file=sys.stderr)
    print(f"valid JSON: {valid}/{total}  rubric auto-pass: {passed}/{total}", file=sys.stderr)
    print(f"latency p50={percentile(latencies, 50):.1f}s p95={percentile(latencies, 95):.1f}s "
          f"(targets doc 19: p95 ≤ 20 s, valid ≥ 95%, rubric ≥ 4/5)", file=sys.stderr)
    print(f"Results → {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
