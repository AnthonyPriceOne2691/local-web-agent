#!/usr/bin/env python3
"""Сводка прогонов Phase 0 → markdown-таблицы для doc 19.

Читает все JSONL из scripts/spike/results/ и печатает:
  - Part A (crawl): task × mode × model — pages / wall / plan p50/p95 / synth / success
  - Part B (vision): model — rubric auto-pass / valid JSON / p50 / p95

Usage: python3 summarize_results.py [--dir results]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def pctl(vals: list[float], pct: float) -> float:
    if not vals:
        return 0.0
    vals = sorted(vals)
    return vals[min(len(vals) - 1, max(0, round(pct / 100 * (len(vals) - 1))))]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args()

    crawl_rows, vision_rows = [], []
    for f in sorted(args.dir.glob("*.jsonl")):
        for r in load_jsonl(f):
            (vision_rows if "fixture" in r else crawl_rows).append(dict(r, _file=f.name))

    if crawl_rows:
        print("## Part A — crawl\n")
        print("| task | mode | model | pages | wall s | plan p50/p95 | synth s | viol | success | file |")
        print("|------|------|-------|-------|--------|--------------|---------|------|---------|------|")
        for r in crawl_rows:
            ok = {True: "✅", False: "❌", None: "manual"}[r.get("auto_success")]
            print(f"| {r.get('task_id')} | {r.get('mode')} | {r.get('model')} "
                  f"| {r.get('pages_visited')} | {r.get('wall_s')} "
                  f"| {r.get('plan_p50')}/{r.get('plan_p95')} | {r.get('synth_s')} "
                  f"| {r.get('violations')} | {ok} | {r['_file']} |")
        print()

    if vision_rows:
        print("## Part B — vision\n")
        by_model: dict[str, list[dict]] = defaultdict(list)
        for r in vision_rows:
            by_model[r.get("model", "?")].append(r)
        print("| model | calls | valid JSON | rubric auto-pass | p50 s | p95 s |")
        print("|-------|-------|------------|------------------|-------|-------|")
        for model, rows in by_model.items():
            walls = [r["wall_s"] for r in rows if "wall_s" in r and "error" not in r]
            valid = sum(1 for r in rows if isinstance(r.get("insight"), dict)
                        and not r["insight"].get("parse_error"))
            passed = sum(1 for r in rows if r.get("rubric_ok"))
            print(f"| {model} | {len(rows)} | {valid}/{len(rows)} | {passed}/{len(rows)} "
                  f"| {pctl(walls, 50):.1f} | {pctl(walls, 95):.1f} |")
        print()


if __name__ == "__main__":
    main()
