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
    output: Path | None = typer.Option(None, "--output", help="write ExtractionResult JSON to file"),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    api_url: str = typer.Option(API_DEFAULT, "--api-url"),
) -> None:
    console.print(DISCLAIMER, style="dim")
    body = {
        "start_url": url, "task": task, "max_pages": max_pages, "max_depth": max_depth,
        "respect_robots": not no_robots, "capture_screenshots": screenshots,
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
            time.sleep(2)
            record = client.get(f"/runs/{run_id}").json()
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


if __name__ == "__main__":
    sys.exit(app())
