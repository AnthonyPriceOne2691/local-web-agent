#!/usr/bin/env python3
"""Fixture sites server — Phase 0 spike (doc 19).

Каждый сайт из tests/fixtures/sites/ поднимается на СВОЁМ порту (чистый origin
для slug-проб и same-domain правил). Extensionless-пути мапятся на .html:
/page/kontak → page/kontak.html, /contact → contact.html, / → index.html.

Usage:
    python3 fixtures_server.py            # блокирующий запуск, Ctrl+C для остановки
    python3 fixtures_server.py --print    # только вывести карту портов и выйти
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

SITES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sites"
BASE_PORT = 8901
HOST = "127.0.0.1"


class FixtureHandler(SimpleHTTPRequestHandler):
    """Static handler c extensionless-маппингом (как CMS с pretty URLs)."""

    def log_message(self, fmt, *args):  # тихий сервер — не мусорить в вывод бенчмарка
        pass

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0].rstrip("/") or "/"
        root = Path(self.directory)
        if clean == "/":
            return str(root / "index.html")
        rel = clean.lstrip("/")
        candidates = [root / rel, root / f"{rel}.html", root / rel / "index.html"]
        for cand in candidates:
            try:
                cand.relative_to(root)  # no traversal
            except ValueError:
                continue
            if cand.is_file():
                return str(cand)
        return str(root / rel)  # 404 дальше по стандартному пути


def build_port_map() -> dict[str, int]:
    sites = sorted(p.name for p in SITES_DIR.iterdir() if p.is_dir())
    return {site: BASE_PORT + i for i, site in enumerate(sites)}


def serve(port_map: dict[str, int]) -> list[HTTPServer]:
    servers = []
    for site, port in port_map.items():
        handler = partial(FixtureHandler, directory=str(SITES_DIR / site))
        srv = HTTPServer((HOST, port), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
    return servers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", help="print port map as JSON and exit")
    args = parser.parse_args()

    port_map = build_port_map()
    urls = {site: f"http://{HOST}:{port}/" for site, port in port_map.items()}
    print(json.dumps(urls, indent=2))
    if args.print:
        return

    serve(port_map)
    print("Fixture sites up. Ctrl+C to stop.", file=sys.stderr)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
