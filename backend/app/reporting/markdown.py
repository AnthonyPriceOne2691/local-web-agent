"""Markdown report — single-site (doc 05 § Markdown report template).

Findings / Design (если vision) / Not found / Appendix (vision diagnostics).
PNG — относительные пути внутри artifacts/{run_id}/ (report.md лежит там же).
"""

from __future__ import annotations

from app.schemas.run import RunRecord
from app.schemas.snapshot import PageSnapshot

VISION_SNIPPET_CAP = 120


def build_report(record: RunRecord, snapshots: list[PageSnapshot]) -> str:
    meta = record.metadata
    result = record.result
    lines: list[str] = [f"# Crawl Report: {record.config.task}", ""]
    vision_note = ""
    if meta.get("vision_calls_total"):
        vision_note = (
            f" · **Vision:** {meta.get('vision_pages_analyzed', 0)} pages"
            f"/{meta.get('vision_calls_total', 0)} calls"
        )
    lines.append(
        f"**URL:** {record.config.start_url} · **Status:** {record.status} · "
        f"**Pages:** {record.pages_visited}{vision_note}"
    )
    lines.append("")

    if result is None or record.status in ("blocked", "failed"):
        reason = meta.get("blocked_by") or record.error_message or "no result"
        lines += ["## Summary", "", f"Run ended without findings: {reason}", ""]
        return "\n".join(lines)

    lines += ["## Summary", "", result.summary or "(no summary)", ""]

    if result.facts:
        lines += ["## Findings", ""]
        for fact in result.facts:
            sources = {ev.source for ev in fact.evidence} or {"dom"}
            src = "both" if {"dom", "vision"} <= sources or "both" in sources else next(iter(sources))
            lines.append(f"### {fact.label or fact.key} ({fact.confidence}) · source: {src}")
            lines.append(fact.value)
            for ev in fact.evidence:
                if ev.quote.strip():
                    lines.append(f'> "{ev.quote}" — [{ev.url}]({ev.url})')
            snippet = _vision_snippet(fact, snapshots)
            if snippet:
                lines.append(f"> _{snippet}_")
            lines.append("")

    design = _design_section(record, snapshots)
    if design:
        lines += design

    if result.not_found:
        lines += ["## Not found", ""]
        lines += [f"- {nf.key}: {nf.reason or 'not present on visited pages'}" for nf in result.not_found]
        lines.append("")

    appendix = _vision_appendix(meta, snapshots)
    if appendix:
        lines += appendix

    lines.append(
        f"_Screenshots are relative to `artifacts/{record.id}/`. "
        f"Open report from that folder for images to render._"
    )
    return "\n".join(lines) + "\n"


def _vision_snippet(fact, snapshots: list[PageSnapshot]) -> str:
    vision_urls = {ev.url for ev in fact.evidence if ev.source in ("vision", "both")}
    if not vision_urls:
        return ""
    for snap in snapshots:
        if snap.url in vision_urls:
            for ins in snap.vision_insights:
                if ins.get("status") == "ok" and ins.get("description"):
                    return f"Vision ({ins.get('profile', '?')}): {ins['description'][:VISION_SNIPPET_CAP]}"
    return ""


def _design_section(record: RunRecord, snapshots: list[PageSnapshot]) -> list[str]:
    designs = [
        (s, ins)
        for s in snapshots
        for ins in s.vision_insights
        if ins.get("status") == "ok" and ins.get("design")
    ]
    if not designs and record.intent != "design_audit":
        return []
    lines = ["## Design analysis", ""]
    colors: list[str] = []
    layouts: list[str] = []
    responsive: list[str] = []
    for _, ins in designs:
        d = ins["design"]
        colors += [c for c in d.get("colors_approx", []) if c not in colors]
        if d.get("layout"):
            layouts.append(d["layout"])
        if d.get("responsive_note"):
            responsive.append(d["responsive_note"])
    if colors:
        lines.append(f"**Colors:** {', '.join(colors[:8])}  ")
    if layouts:
        lines.append(f"**Layout:** {layouts[0]}  ")
    if responsive:
        lines.append(f"**Responsive:** {responsive[0]}  ")
    shots = [(ref.profile.capitalize(), ref.relative_path) for s in snapshots for ref in s.screenshots][:6]
    if shots:
        lines += ["", "| Viewport | Screenshot |", "|----------|------------|"]
        lines += [f"| {profile} | ![{profile.lower()}]({path}) |" for profile, path in shots]
    lines.append("")
    return lines


def _vision_appendix(meta: dict, snapshots: list[PageSnapshot]) -> list[str]:
    if not (meta.get("vision_failures") or meta.get("vision_skipped_pages")):
        return []
    lines = [
        "## Appendix: vision diagnostics",
        "",
        "| URL | Profile | Status | Note |",
        "|-----|---------|--------|------|",
    ]
    for snap in snapshots:
        for ins in snap.vision_insights:
            note = ins.get("error") or "—"
            lines.append(f"| {snap.url} | {ins.get('profile', '?')} | {ins.get('status', '?')} | {note} |")
    for url in meta.get("vision_skipped_pages", []):
        lines.append(f"| {url} | — | skipped | page cap |")
    lines.append("")
    return lines
