"""CLI (doc 15): thin wrapper над REST. `agent crawl / runs list / runs show`.

Usage:
    python -m cli.main crawl --url https://example.com --task "Find pricing"
    python -m cli.main runs list
    python -m cli.main runs show <id>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(no_args_is_help=True, add_completion=False)
runs_app = typer.Typer(no_args_is_help=True)
app.add_typer(runs_app, name="runs")
console = Console(stderr=True)

API_DEFAULT = "http://127.0.0.1:8001"
DISCLAIMER = ("Local Web Agent — personal research tool.\n"
              "You are responsible for complying with website Terms of Service.\n"
              "robots.txt is respected by default.")


def _client(api_url: str) -> httpx.Client:
    return httpx.Client(base_url=api_url, timeout=30)


@app.command()
def crawl(
    url: str = typer.Option(..., "--url"),
    task: str = typer.Option(..., "--task"),
    max_pages: int = typer.Option(10, "--max-pages"),
    max_depth: int = typer.Option(2, "--max-depth"),
    no_robots: bool = typer.Option(False, "--no-robots"),
    screenshots: str = typer.Option("auto", "--screenshots", help="auto|always|never"),
    sitemap: str = typer.Option("auto", "--sitemap", help="auto|always|never (P2.5, doc 21)"),
    consent: str = typer.Option("auto", "--consent", help="auto|hide_only|never (D-11)"),
    consent_click: str = typer.Option("reject_first", "--consent-click",
                                      help="reject_first|accept|never"),
    vision: str = typer.Option("auto", "--vision", help="auto|always|never (doc 23)"),
    allow_private: bool = typer.Option(False, "--allow-private",
                                       help="разрешить private-network цели (I-H8 override)"),
    attended: bool = typer.Option(False, "--attended",
                                  help="видимый браузер; на anti-bot challenge пауза — "
                                       "пройди проверку сам, затем resume (Phase 5)"),
    output: Path | None = typer.Option(None, "--output", help="write ExtractionResult JSON to file"),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    api_url: str = typer.Option(API_DEFAULT, "--api-url"),
) -> None:
    console.print(DISCLAIMER, style="dim")
    body = {
        "start_url": url, "task": task, "max_pages": max_pages, "max_depth": max_depth,
        "respect_robots": not no_robots, "capture_screenshots": screenshots,
        "use_sitemap": sitemap, "consent_handling": consent, "consent_click": consent_click,
        "vision_enabled": vision, "allow_private": allow_private, "attended": attended,
    }
    with _client(api_url) as client:
        try:
            r = client.post("/runs", json=body)
        except httpx.HTTPError as exc:
            console.print(f"[red]API unreachable:[/red] {exc}")
            raise typer.Exit(3) from exc
        if r.status_code == 409:
            console.print(f"[red]409:[/red] {r.json()['detail']}")
            raise typer.Exit(2)
        r.raise_for_status()
        run_id = r.json()["run_id"]
        console.print(f"Run started: [bold]{run_id}[/bold]")
        if not wait:
            print(run_id)
            return
        status = "running"
        while status == "running":
            try:
                time.sleep(2)
                record = client.get(f"/runs/{run_id}").json()
            except KeyboardInterrupt:  # doc 15: [a]bort on server / [d]etach
                choice = typer.prompt("\n[a]bort run on server / [d]etach (run continues)",
                                      default="d").strip().lower()
                if choice.startswith("a"):
                    client.post(f"/runs/{run_id}/cancel")
                    console.print("Cancel requested — waiting for run to stop…")
                    continue
                console.print(f"Detached. Poll later: agent runs show {run_id}")
                print(run_id)
                return
            status = record["status"]
            console.print(
                f"[{record['pages_visited']}/{max_pages}] {record.get('current_url', '')} · {status}",
                highlight=False,
            )
        result = record.get("result") or {}
        _print_result(result, record)
        if output:
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            console.print(f"Saved: {output}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        code = 0 if status in ("completed", "partial") else 1 if status in ("not_found", "blocked") else 2
        raise typer.Exit(code)


def _print_result(result: dict, record: dict) -> None:
    console.print(f"\n[bold]Status:[/bold] {record['status']} "
                  f"({record['pages_visited']} pages, {result.get('duration_seconds', '?')}s)")
    if result.get("summary"):
        console.print(f"[bold]Summary:[/bold] {result['summary']}")
    for fact in result.get("facts", []):
        console.print(f"  • {fact['key']} ({fact['confidence']}): {fact['value']}")
        for ev in fact.get("evidence", []):
            if ev.get("quote"):
                console.print(f'    "{ev["quote"][:120]}" — {ev["url"]}', style="dim")
    for nf in result.get("not_found", []):
        console.print(f"  ∅ {nf['key']}: {nf.get('reason', '')}", style="yellow")


@runs_app.command("list")
def runs_list(limit: int = 20, api_url: str = typer.Option(API_DEFAULT, "--api-url")) -> None:
    with _client(api_url) as client:
        data = client.get("/runs", params={"limit": limit}).json()
    table = Table("ID", "STATUS", "PAGES", "TASK", "STARTED")
    for r in data["runs"]:
        table.add_row(r["run_id"], r["status"], str(r["pages_visited"]), r["task"][:50], r["started_at"][:19])
    Console().print(table)


@runs_app.command("show")
def runs_show(
    run_id: str,
    steps: bool = typer.Option(False, "--steps"),
    api_url: str = typer.Option(API_DEFAULT, "--api-url"),
) -> None:
    with _client(api_url) as client:
        r = client.get(f"/runs/{run_id}")
    if r.status_code == 404:
        console.print("[red]run not found[/red]")
        raise typer.Exit(1)
    record = r.json()
    if steps:
        for s in record["steps"]:
            line = f"[{s['index']:02d}] {s['state']:10s} {s.get('action', ''):12s} {s.get('url', '')}"
            if s.get("note"):
                line += f"  ({s['note']})"
            Console().print(line, highlight=False)
    else:
        Console().print(json.dumps(record.get("result") or {"status": record["status"]},
                                   ensure_ascii=False, indent=2))


@app.command()
def research(
    urls: str = typer.Option(..., "--urls", help="comma-separated URLs"),
    task: str = typer.Option(..., "--task"),
    rubric: str | None = typer.Option(None, "--rubric",
                                      help="design_diff|content_completeness|generic_merge"),
    output: Path | None = typer.Option(None, "--output", help="ComparisonResult JSON to file"),
    report: Path | None = typer.Option(None, "--report", help="copy comparison_report.md here"),
    api_url: str = typer.Option(API_DEFAULT, "--api-url"),
) -> None:
    """Multi-site research (doc 24): sequential crawls + compare. Один chat-message без UI."""
    console.print(DISCLAIMER, style="dim")
    message = f"{task}\n" + "\n".join(u.strip() for u in urls.split(",") if u.strip())
    with httpx.Client(base_url=api_url, timeout=60) as client:
        try:
            sid = client.post("/sessions", json={"rubric": rubric}).json()["session_id"]
            r = client.post(f"/sessions/{sid}/messages", json={"content": message})
        except httpx.HTTPError as exc:
            console.print(f"[red]API unreachable:[/red] {exc}")
            raise typer.Exit(3) from exc
        if r.status_code == 409:
            console.print(f"[red]409:[/red] {r.json()['detail']}")
            raise typer.Exit(2)
        r.raise_for_status()
        console.print(f"Session started: [bold]{sid}[/bold]")
        seen_msgs = 0
        status = "running_tools"
        while status in ("active", "running_tools", "comparing"):
            time.sleep(3)
            session = client.get(f"/sessions/{sid}").json()
            status = session["status"]
            for msg in session["messages"][seen_msgs:]:
                if msg["role"] in ("tool", "assistant"):
                    console.print(f"[{msg['role']}] {msg['content'][:200]}", highlight=False)
            seen_msgs = len(session["messages"])
        comparison = session.get("comparison_result")
        console.print(f"\n[bold]Session:[/bold] {status} · runs: {len(session['run_ids'])}")
        if comparison:
            print(json.dumps(comparison, ensure_ascii=False, indent=2))
            if output:
                output.write_text(json.dumps(comparison, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
                console.print(f"Saved: {output}")
        src = Path("data/runs/artifacts") / sid / "comparison_report.md"
        if report and src.is_file():  # CLI и сервер локальны (solo tool)
            report.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            console.print(f"Report: {report}")
        elif src.is_file():
            console.print(f"Report: {src}")
        raise typer.Exit(0 if status == "completed" else 2)


@runs_app.command("cancel")
def runs_cancel(
    run_id: str = typer.Argument("", help="run id; пусто — отменить активный"),
    api_url: str = typer.Option(API_DEFAULT, "--api-url"),
) -> None:
    with _client(api_url) as client:
        if not run_id:
            active = client.get("/health").json().get("active_run_id")
            if not active:
                console.print("no active run")
                raise typer.Exit(1)
            run_id = active
        r = client.post(f"/runs/{run_id}/cancel")
    if r.status_code == 404:
        console.print("[red]run not found[/red]")
        raise typer.Exit(1)
    if r.status_code == 409:
        console.print(f"[yellow]run not running:[/yellow] {r.json()['detail']}")
        raise typer.Exit(2)
    console.print(f"Canceling: {run_id}")


@runs_app.command("delete")
def runs_delete(run_id: str, api_url: str = typer.Option(API_DEFAULT, "--api-url")) -> None:
    with _client(api_url) as client:
        r = client.delete(f"/runs/{run_id}")
    if r.status_code == 404:
        console.print("[red]run not found[/red]")
        raise typer.Exit(1)
    if r.status_code == 409:
        console.print("[red]run is active — cancel it first[/red]")
        raise typer.Exit(2)
    console.print(f"Deleted: {run_id}")


if __name__ == "__main__":
    sys.exit(app())
