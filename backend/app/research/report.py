"""Comparison report markdown (doc 05 § Comparison report template)."""

from __future__ import annotations

from app.schemas.research import ComparisonResult, SessionRecord
from app.schemas.run import RunRecord


def build_comparison_report(
    session: SessionRecord, comparison: ComparisonResult, runs: list[RunRecord]
) -> str:
    lines = [
        "# Comparison Report",
        "",
        f"**Task:** {comparison.comparison_task} · **Sites:** {len(runs)} · "
        f"**Rubric:** {comparison.rubric}",
        "",
        "## Conclusion",
        "",
        comparison.narrative or "(no narrative)",
        "",
    ]
    if comparison.winner:
        lines += ["## Winner", "",
                  f"**{comparison.winner.label}**: {comparison.winner.reason}", ""]
    if comparison.rankings:
        lines += ["## Rankings", "", "| Site | Score | Summary |", "|------|-------|---------|"]
        lines += [f"| {r.url} | {r.score} | {r.summary} |" for r in comparison.rankings]
        lines.append("")
    if comparison.dimensions:
        sites = sorted({site for d in comparison.dimensions for site in d.scores})
        header = "| Dimension | " + " | ".join(sites) + " |"
        sep = "|" + "---|" * (len(sites) + 1)
        lines += ["## Dimensions", "", header, sep]
        for d in comparison.dimensions:
            row = " | ".join(str(d.scores.get(site, "—")) for site in sites)
            lines.append(f"| {d.name} | {row} |")
        lines.append("")
    if comparison.excluded:
        lines += ["## Excluded sites", ""]
        lines += [f"- {e.start_url} — {e.reason}" for e in comparison.excluded]
        lines.append("")
    lines += ["## Per-site details", ""]
    for run in runs:
        summary = (run.result.summary if run.result else run.status) or run.status
        lines.append(f"- **{run.config.start_url}** (run `{run.id}`, {run.status}, "
                     f"{run.pages_visited} pages): {summary[:300]} — "
                     f"[report](../{run.id}/report.md)")
    lines.append("")
    return "\n".join(lines)
