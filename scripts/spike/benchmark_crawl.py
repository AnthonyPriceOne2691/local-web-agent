#!/usr/bin/env python3
"""Phase 0 spike — Part A: crawl benchmark (doc 19).

Мини-реализация agent loop по дизайну (docs 03/04/13/21), НО в одном файле
(spike-исключение из 500 LOC, doc 06): observe → candidates → LLM top-K →
contract-lite → navigate → synthesis. Меряет: pages, wall time, LLM latency
p50/p95, tokens/s (eval_count/eval_duration из Ollama), auto-success по
ожидаемым подстрокам из tasks.yaml.

Режимы:
  --mode hints     candidate queue P0–P4 + slug-пробы + скоринг (doc 21)
  --mode llm-only  сырые ссылки страницы без словарей/скоринга (A/B task #7)
  --dry-run        без LLM: детерминированный link scorer + regex-извлечение
                   (smoke-тест плумбинга)

Примеры:
  python3 benchmark_crawl.py --tasks tasks.yaml --mode hints
  python3 benchmark_crawl.py --tasks tasks.yaml --mode llm-only --task-id 6
  python3 benchmark_crawl.py --url http://127.0.0.1:8903/ --task "Find contact email" --mode hints
  python3 benchmark_crawl.py --tasks tasks.yaml --model qwen3:14b   # A/B task #10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import httpx
import yaml

try:  # OQ-2: same registrable domain (doc 03); offline PSL snapshot
    import tldextract
    _TLD = tldextract.TLDExtract(suffix_list_urls=())
except ImportError:  # graceful: строгий same-host
    _TLD = None

USER_AGENT = "LocalWebAgent/0.1 (personal research tool; +https://localhost)"

REPO = Path(__file__).resolve().parents[2]
HINTS_FILE = REPO / "data" / "navigation" / "path_hints.yaml"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
OLLAMA = "http://localhost:11434"

TRACKING_PARAMS = ("utm_", "gclid", "fbclid", "yclid", "ref")
FORBIDDEN_SUBSTR = ("/login", "/signin", "/signup", "/register", "/cart", "/checkout", "/wp-admin")
LEGAL_SUBSTR = ("/privacy", "/terms", "/cookie", "/legal")

NAV_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["navigate", "extract_now", "stop"]},
        "url": {"type": "string"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["action", "reasoning"],
}

NAV_SYSTEM = (
    "You are a web navigation agent. You are given a task, the current page snapshot, "
    "and a numbered list of candidate links. Decide ONE action:\n"
    '- {"action":"navigate","url":"<url EXACTLY from candidates>","reasoning":"...","confidence":"high|medium|low"}\n'
    '- {"action":"extract_now","reasoning":"current page likely contains the answer"}\n'
    '- {"action":"stop","reasoning":"enough information collected or nothing left to try"}\n'
    "Rules: url MUST be copied verbatim from the candidate list. Never invent URLs. "
    "Prefer the shortest path to the answer. Respond with JSON only."
)

SYNTH_SYSTEM = (
    "You extract structured findings from crawled web pages. Given a task and page snapshots, "
    "return JSON exactly in this shape:\n"
    '{"summary":"one-paragraph answer to the task",'
    '"facts":[{"key":"snake_case","label":"...","value":"...","confidence":"high|medium|low",'
    '"evidence":{"url":"...","quote":"verbatim quote from a snapshot"}}],'
    '"not_found":[{"key":"...","reason":"..."}]}\n'
    "Rules: every high-confidence fact needs a verbatim quote that appears in the snapshots. "
    "If the task asks for something absent, add it to not_found instead of guessing. JSON only."
)


# ---------------------------------------------------------------- utilities

def normalize_url(url: str) -> str:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    port = f":{p.port}" if p.port and p.port not in (80, 443) else ""
    query = urlencode([(k, v) for k, v in parse_qsl(p.query)
                       if not any(k.lower().startswith(t) or k.lower() == t for t in TRACKING_PARAMS)])
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), host + port, path, "", query, ""))


def registrable_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if _TLD and not re.fullmatch(r"[\d.]+|localhost", host):
        ext = _TLD(host)
        reg = getattr(ext, "top_domain_under_public_suffix", "") or getattr(ext, "registered_domain", "")
        return reg or host
    return host  # IP / localhost / нет tldextract → строгое сравнение хоста


def same_site(url: str, origin: str) -> bool:
    """OQ-2 closed: same registrable domain (www/blog/docs субдомены — свои)."""
    a, b = registrable_domain(url), registrable_domain(origin)
    if (urlparse(origin).hostname or "") in ("127.0.0.1", "localhost"):
        # fixtures: каждый сайт на своём порту — порт входит в сравнение
        return (urlparse(url).netloc or "").lower() == (urlparse(origin).netloc or "").lower()
    return bool(a) and a == b


def is_allowed_target(url: str, origin: str) -> bool:
    """Contract-lite I-H1 + I-H8: same site; чужие private-хосты отсекаются same-site правилом."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    return same_site(url, origin)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round(pct / 100 * (len(values) - 1))))
    return values[idx]


# ---------------------------------------------------------------- hints / intent

def load_hints() -> dict:
    return yaml.safe_load(HINTS_FILE.read_text(encoding="utf-8"))


def classify_intent(task: str, hints: dict) -> str:
    text = task.casefold()
    best, best_hits = "generic", 0
    for intent, keywords in hints.get("intent_keywords", {}).items():
        hits = sum(1 for kw in keywords if str(kw).casefold() in text)
        if hits > best_hits:
            best, best_hits = intent, hits
    return best


def score_link(link: dict, intent: str, hints: dict, task: str, on_homepage: bool) -> tuple[int, str]:
    href, text = link["href"].casefold(), (link.get("text") or "").casefold()
    reasons, score = [], 0
    kw = [str(k).casefold() for k in hints.get("intent_keywords", {}).get(intent, [])]
    slugs = [str(s).casefold() for s in hints.get(intent, [])]
    if on_homepage and any(k in text or k in href for k in kw):
        score += 15; reasons.append("homepage+intent")
    if any(s in href for s in slugs):
        score += 12; reasons.append("slug")
    if any(w in text for w in task.casefold().split() if len(w) > 3):
        score += 10; reasons.append("task-kw")
    if intent == "contact" and any(s.casefold() in href for s in hints.get("contact_legal", [])):
        score += 8; reasons.append("legal-contact")
    depth = urlparse(link["href"]).path.rstrip("/").count("/")
    if depth <= 1:
        score += 3; reasons.append("shallow")
    if any(s in href for s in LEGAL_SUBSTR) and intent != "contact":
        score -= 8; reasons.append("legal-avoid")
    if any(s in href for s in FORBIDDEN_SUBSTR):
        score -= 10; reasons.append("forbidden")
    return score, "+".join(reasons) or "plain"


async def probe_slugs(client: httpx.AsyncClient, origin: str, slugs: list[str],
                      cache: dict[str, bool]) -> list[str]:
    """F1-lite (doc 21 two-tier fetch): дешёвый HTTP-фильтр slug-проб.

    Урок первого же dry-run'а: без фильтра пробы жгут page budget на 404-х
    (/contact, /contact-us, ... — а /page/kontak стоит 14-м в словаре и в
    top-10 не попадает). SEOLB решал это HTTP-tier'ом — здесь его мини-версия:
    в очередь идут только живые (2xx/3xx) пробы.
    """
    alive = []
    for slug in slugs:
        url = origin.rstrip("/") + str(slug)
        if url not in cache:
            try:
                r = await client.head(url, timeout=4, follow_redirects=True)
                if r.status_code == 405:
                    r = await client.get(url, timeout=4, follow_redirects=True)
                cache[url] = r.status_code < 400
            except httpx.HTTPError:
                cache[url] = False
        if cache[url]:
            alive.append(url)
    return alive


def build_candidates(mode: str, snapshot: dict, homepage: dict | None, intent: str,
                     hints: dict, task: str, origin: str, visited: set[str],
                     alive_probes: list[str], legal_probes: list[str]) -> list[dict]:
    """CandidateQueue P0–P4 (doc 21) в hints-режиме; сырые ссылки в llm-only."""
    def usable(links):
        return [l for l in links
                if is_allowed_target(l["href"], origin) and normalize_url(l["href"]) not in visited]

    if mode == "llm-only":
        return [dict(l, score=0, reason="raw") for l in usable(snapshot["links"])][:40]

    is_home = urlparse(snapshot["url"]).path.rstrip("/") in ("", "/")
    buckets: list[list[dict]] = [[], [], [], [], []]
    for l in usable(snapshot["links"]):
        s, r = score_link(l, intent, hints, task, on_homepage=is_home)
        item = dict(l, score=s, reason=r)
        buckets[0 if ("slug" in r or "task-kw" in r or "homepage+intent" in r) else 4].append(item)
    if homepage and homepage["url"] != snapshot["url"]:
        for l in usable(homepage["links"]):
            s, r = score_link(l, intent, hints, task, on_homepage=True)
            if s > 0:
                buckets[1].append(dict(l, score=s, reason="home:" + r))
    for url in alive_probes:
        if normalize_url(url) not in visited:
            buckets[2].append({"href": url, "text": "(slug probe, HTTP-alive)", "score": 12, "reason": "probe"})
    for url in legal_probes:
        if normalize_url(url) not in visited:
            buckets[3].append({"href": url, "text": "(legal probe, HTTP-alive)", "score": 8, "reason": "legal-probe"})

    seen, queue = set(), []
    for bucket in buckets:
        for item in sorted(bucket, key=lambda x: -x["score"]):
            n = normalize_url(item["href"])
            if n not in seen:
                seen.add(n)
                queue.append(item)
    return queue[:10]


# ---------------------------------------------------------------- browser

OBSERVE_JS = """() => {
  const pick = sel => document.querySelector(sel);
  const mainEl = pick('main') || pick('[role=main]') || pick('article') || document.body;
  const headings = [...document.querySelectorAll('h1,h2,h3')].slice(0, 20)
    .map(h => ({level: +h.tagName[1], text: h.innerText.trim().slice(0, 200)}));
  const links = [...document.querySelectorAll('a[href]')].map(a => ({
    href: a.href, text: (a.innerText || '').trim().slice(0, 120)
  }));
  return {
    title: document.title.slice(0, 200),
    meta: (pick('meta[name=description]')?.content || '').slice(0, 300),
    headings,
    main_text: (mainEl.innerText || '').slice(0, 8000),
    links
  };
}"""


async def observe(page) -> dict:
    raw = await page.evaluate(OBSERVE_JS)
    links, seen = [], set()
    for l in raw["links"]:
        href = l["href"]
        if href.startswith(("mailto:", "tel:", "javascript:")) or href.endswith("#"):
            continue
        n = normalize_url(urljoin(page.url, href))
        if n not in seen:
            seen.add(n)
            links.append({"href": n, "text": l["text"]})
    return {
        "url": normalize_url(page.url), "title": raw["title"], "meta": raw["meta"],
        "headings": raw["headings"], "main_text": raw["main_text"],
        "links": links[:40], "priority": False,
    }


# ---------------------------------------------------------------- ollama

@dataclass
class LlmStats:
    calls: list[dict] = field(default_factory=list)

    def add(self, kind: str, wall: float, resp: dict | None):
        entry = {"kind": kind, "wall_s": round(wall, 2)}
        if resp:
            for k in ("eval_count", "prompt_eval_count", "eval_duration", "total_duration"):
                if k in resp:
                    entry[k] = resp[k]
            if resp.get("eval_count") and resp.get("eval_duration"):
                entry["tok_s"] = round(resp["eval_count"] / (resp["eval_duration"] / 1e9), 1)
        self.calls.append(entry)

    def walls(self, kind: str) -> list[float]:
        return [c["wall_s"] for c in self.calls if c["kind"] == kind]


async def ollama_chat(client: httpx.AsyncClient, model: str, system: str, user: str, *,
                      fmt=None, think: bool | None = None, num_ctx: int = 8192,
                      temperature: float = 0.4, max_tokens: int = 600, images: list[str] | None = None,
                      keep_alive: str | int = "10m") -> tuple[str, dict]:
    body = {
        "model": model, "stream": False, "keep_alive": keep_alive,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user, **({"images": images} if images else {})}],
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": max_tokens},
    }
    if fmt is not None:
        body["format"] = fmt
    if think is not None:
        body["think"] = think
    r = await client.post(f"{OLLAMA}/api/chat", json=body, timeout=300)
    if r.status_code == 400 and think is not None:  # старый Ollama без think — fallback
        body.pop("think")
        r = await client.post(f"{OLLAMA}/api/chat", json=body, timeout=300)
    r.raise_for_status()
    data = r.json()
    return data.get("message", {}).get("content", ""), data


async def ollama_unload(client: httpx.AsyncClient, model: str):
    try:
        await client.post(f"{OLLAMA}/api/generate", json={"model": model, "keep_alive": 0}, timeout=30)
    except httpx.HTTPError:
        pass


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def extract_json(text: str) -> dict | None:
    """Первый валидный JSON-объект из текста (raw_decode — устойчив к `{` внутри строк)."""
    text = strip_thinking(text)
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx >= 0:
        try:
            obj, _ = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)
    return None


def load_robots(origin: str) -> tuple[urllib.robotparser.RobotFileParser | None, float]:
    """robots.txt для real-сайтов (doc 03): 4xx → allow; 5xx/сбой → allow + log (spike).

    Возвращает (parser | None, crawl_delay_s). Для localhost-фикстур — (None, 0).
    """
    host = (urlparse(origin).hostname or "").lower()
    if host in ("127.0.0.1", "localhost"):
        return None, 0.0
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(origin.rstrip("/") + "/robots.txt")
    try:
        rp.read()
    except OSError as exc:
        print(f"    robots.txt fetch failed ({exc}) — proceed + log", file=sys.stderr)
        return None, 0.0
    delay = 0.0
    for agent in (USER_AGENT, "*"):
        d = rp.crawl_delay(agent)
        if d:
            delay = max(delay, min(float(d), 10.0))  # cap 10 s (FR-1.4)
    return rp, delay


def robots_allowed(rp: urllib.robotparser.RobotFileParser | None, url: str) -> bool:
    if rp is None:
        return True
    return rp.can_fetch(USER_AGENT, url) and rp.can_fetch("*", url)


# ---------------------------------------------------------------- crawl loop

async def crawl(task_cfg: dict, args, hints: dict, client: httpx.AsyncClient) -> dict:
    from playwright.async_api import async_playwright

    task, start_url = task_cfg["task"], task_cfg["url"]
    origin = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    intent = classify_intent(task, hints)
    stats, steps = LlmStats(), []
    visited: set[str] = set()
    hops: dict[str, int] = {normalize_url(start_url): 0}
    snapshots: list[dict] = []
    homepage: dict | None = None
    violations = 0
    t0 = time.perf_counter()

    probe_cache: dict[str, bool] = {}
    alive_probes: list[str] = []
    legal_probes: list[str] = []
    if args.mode == "hints":
        alive_probes = await probe_slugs(client, origin, hints.get(intent, []), probe_cache)
        if intent == "contact":
            legal_probes = await probe_slugs(client, origin, hints.get("contact_legal", []), probe_cache)

    rp, crawl_delay = load_robots(origin)  # G-H5 + Crawl-delay (real sites; фикстуры → None)
    rate_ms = max(args.rate_limit_ms, int(crawl_delay * 1000))
    screens_dir = RESULTS_DIR / "screens"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        current, next_url = None, start_url
        extract_now_streak = 0

        for step in range(args.max_pages * 2):  # PLAN-итерации; страницы ограничены visited/G-H1
            if next_url is not None:  # navigate + observe
                if not robots_allowed(rp, next_url):  # G-H5
                    steps.append({"step": step, "url": next_url, "note": "robots_disallow — skipped"})
                    visited.add(normalize_url(next_url))
                    next_url = None
                    if current is None:
                        break
                    continue
                t_nav = time.perf_counter()
                nav_err = None
                for _attempt in (1, 2):  # retry 1× после 2 s (doc 03: transient ≠ missing)
                    try:
                        await page.goto(next_url, wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(1000)
                        nav_err = None
                        break
                    except Exception as exc:  # noqa: BLE001 (spike)
                        nav_err = str(exc)[:200]
                        await page.wait_for_timeout(2000)
                if nav_err:
                    steps.append({"step": step, "url": next_url, "error": nav_err})
                    visited.add(normalize_url(next_url))  # не предлагать этот URL снова
                    next_url = None
                    if current is None:
                        break  # стартовая страница недоступна — делать нечего
                    continue  # PLAN выберет следующего кандидата
                current = await observe(page)
                if len(current["main_text"]) < 200:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:  # noqa: BLE001
                        pass
                    current = await observe(page)
                if not is_allowed_target(current["url"], origin):  # I-H9 post-redirect
                    steps.append({"step": step, "url": next_url, "note": "redirect_offsite — discarded"})
                    next_url = None
                    if current is None or not visited:
                        break
                    continue
                # SPA fallback capture (docs 03/22) + --screenshots always: вход для vision (task 8b)
                if args.screenshots == "always" or (args.screenshots == "auto"
                                                    and len(current["main_text"]) < 200):
                    screens_dir.mkdir(parents=True, exist_ok=True)
                    shot = screens_dir / f"{task_cfg.get('id', 'x')}_{step:02d}.png"
                    try:
                        await page.screenshot(path=str(shot))
                        current["screenshot_path"] = str(shot)
                    except Exception:  # noqa: BLE001
                        pass
                visited.add(current["url"])
                snapshots.append(current)
                if homepage is None:
                    homepage = current
                steps.append({"step": step, "url": current["url"],
                              "load_s": round(time.perf_counter() - t_nav, 2)})
                next_url = None

            candidates = build_candidates(args.mode, current, homepage, intent, hints,
                                          task, origin, visited, alive_probes, legal_probes)
            budget_left = args.max_pages - len(visited)

            if args.dry_run:
                action = ({"action": "navigate", "url": candidates[0]["href"], "reasoning": "dry-run top"}
                          if candidates and budget_left > 0 and len(visited) < 3
                          else {"action": "stop", "reasoning": "dry-run budget"})
            else:
                cand_lines = "\n".join(f"{i+1}. {c['href']}  [{c['text'][:60]}] (score {c['score']}, {c['reason']})"
                                       for i, c in enumerate(candidates)) or "(none)"
                user = (f"TASK: {task}\nINTENT: {intent}\nPAGES LEFT: {budget_left}\n\n"
                        f"CURRENT PAGE: {current['url']}\nTITLE: {current['title']}\n"
                        f"HEADINGS: {json.dumps(current['headings'][:10], ensure_ascii=False)}\n"
                        f"TEXT (truncated): {current['main_text'][:3000]}\n\n"
                        f"VISITED: {json.dumps(sorted(visited), ensure_ascii=False)}\n\n"
                        f"CANDIDATE LINKS:\n{cand_lines}")
                # thinking-модели (qwen3 и т.п.) в nav-роли — think OFF: JSON сразу, без размышлений
                think_plan = False if any(m in args.model for m in ("qwen3", "r1", "gpt-oss", "magistral")) else None
                t_llm = time.perf_counter()
                content, resp = await ollama_chat(client, args.model, NAV_SYSTEM, user,
                                                  fmt=NAV_SCHEMA, temperature=0.4, max_tokens=400,
                                                  think=think_plan)
                stats.add("plan", time.perf_counter() - t_llm, resp)
                action = extract_json(content) or {"action": "stop", "reasoning": "unparseable"}

            # -------- contract-lite VALIDATE (I-H6 / I-H1 / G-H2 hop / G-H3)
            act = action.get("action")
            if act == "navigate":
                target = normalize_url(action.get("url", ""))
                cand_urls = {normalize_url(c["href"]) for c in candidates}
                parent_hops = hops.get(current["url"], 0)
                reject = (target not in cand_urls and "I-H6"
                          ) or (not is_allowed_target(target, origin) and "I-H1/H8"
                          ) or (target in visited and "G-H3"
                          ) or (parent_hops + 1 > args.max_depth and "G-H2"
                          ) or (len(visited) >= args.max_pages and "G-H1")
                if reject == "G-H1":  # бюджет страниц исчерпан — форс stop, не replan
                    steps.append({"step": step, "note": "G-H1 page budget → stop"})
                    break
                if reject:
                    violations += 1
                    steps.append({"step": step, "violation": reject, "proposed": action.get("url")})
                    if candidates:  # recovery: link scorer fallback
                        target = normalize_url(candidates[0]["href"])
                    else:
                        act = "stop"
                if act == "navigate":
                    hops[target] = min(hops.get(target, 99), hops.get(current["url"], 0) + 1)
                    next_url = target
                    extract_now_streak = 0
                    await page.wait_for_timeout(rate_ms)
                    continue
            if act == "extract_now":
                current["priority"] = True
                extract_now_streak += 1
                steps.append({"step": step, "action": "extract_now"})
                if extract_now_streak >= 2 or budget_left <= 0:  # loop guard (policy #11)
                    break
                continue
            steps.append({"step": step, "action": "stop", "reasoning": action.get("reasoning", "")[:200]})
            break

        await browser.close()

    # -------- optional VISION merge (код для task 8b; выполняется ТОЛЬКО с --vision)
    if args.vision and not args.dry_run:
        shots = [s for s in snapshots if s.get("screenshot_path")][:3]
        if shots:
            import base64  # noqa: PLC0415
            from benchmark_vision import VISION_SCHEMA, VISION_SYSTEM  # noqa: PLC0415
            await ollama_unload(client, args.model)  # swap: nav → VLM (doc 14)
            for s in shots:
                b64 = base64.b64encode(Path(s["screenshot_path"]).read_bytes()).decode()
                t_v = time.perf_counter()
                content, resp = await ollama_chat(
                    client, args.vision_model, VISION_SYSTEM, f"TASK: {task}",
                    fmt=VISION_SCHEMA, temperature=0.2, max_tokens=1200,
                    images=[b64], keep_alive="5m")
                stats.add("vision", time.perf_counter() - t_v, resp)
                s["vision_insight"] = extract_json(content) or {"parse_error": True}
            await ollama_unload(client, args.vision_model)  # swap: VLM → R1

    # -------- SYNTHESIZE
    result_json: dict = {}
    if args.dry_run:
        blob = "\n".join(s["main_text"] for s in snapshots)
        found = {
            "phones": re.findall(r"\+\d[\d\s()\-]{7,}", blob)[:3],
            "emails": re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", blob)[:3],
            "prices": re.findall(r"\$\d+[^\s]*", blob)[:3],
        }
        result_json = {"summary": f"dry-run regex: {found}", "facts": [], "not_found": [],
                       "screenshots_captured": [s.get("screenshot_path") for s in snapshots
                                                if s.get("screenshot_path")]}
    elif snapshots:
        await ollama_unload(client, args.model)  # swap: nav → synth (doc 14)
        bundle = []
        for s in snapshots:
            cap = 4000 if s["priority"] else 1000
            block = (f"URL: {s['url']}\nTITLE: {s['title']}\n"
                     f"HEADINGS: {json.dumps(s['headings'][:8], ensure_ascii=False)}\n"
                     f"TEXT: {s['main_text'][:cap]}\n")
            if s.get("vision_insight"):  # doc 23: R1 получает ТЕКСТ vision_insights, не PNG
                block += ("VISION (screenshot analysis, source=vision): "
                          f"{json.dumps(s['vision_insight'], ensure_ascii=False)[:800]}\n")
            bundle.append(block)
        t_syn = time.perf_counter()
        content, resp = await ollama_chat(
            client, args.synth_model, SYNTH_SYSTEM,
            f"TASK: {task}\n\nPAGES ({len(bundle)}):\n\n" + "\n---\n".join(bundle),
            think=True, temperature=0.2, num_ctx=16384, max_tokens=4096, keep_alive=0)
        stats.add("synthesize", time.perf_counter() - t_syn, resp)
        result_json = extract_json(content) or {"summary": strip_thinking(content)[:500],
                                                "facts": [], "not_found": [], "parse_error": True}

    wall = time.perf_counter() - t0
    expect = task_cfg.get("expect", [])
    hit = [e for e in expect if e.casefold() in json.dumps(result_json, ensure_ascii=False).casefold()]
    return {
        "task_id": task_cfg.get("id"), "task": task, "url": start_url, "mode": args.mode,
        "model": args.model if not args.dry_run else "dry-run", "synth_model": args.synth_model,
        "intent": intent, "pages_visited": len(visited), "wall_s": round(wall, 1),
        "plan_p50": percentile(stats.walls("plan"), 50), "plan_p95": percentile(stats.walls("plan"), 95),
        "synth_s": (stats.walls("synthesize") or [0])[0], "violations": violations,
        "rate_ms_effective": rate_ms,
        "screenshots": [s["screenshot_path"] for s in snapshots if s.get("screenshot_path")],
        "expect": expect, "expect_hit": hit, "auto_success": bool(hit) if expect else None,
        "visited": sorted(visited), "steps": steps, "llm_calls": stats.calls, "result": result_json,
    }


# ---------------------------------------------------------------- runner

async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, help="tasks.yaml manifest")
    parser.add_argument("--task-id", action="append", help="run only these task ids (repeatable)")
    parser.add_argument("--url"); parser.add_argument("--task")
    parser.add_argument("--mode", choices=["hints", "llm-only"], default="hints")
    parser.add_argument("--model", default="qwen2.5:14b-instruct")
    parser.add_argument("--synth-model", default="deepseek-r1:14b")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--rate-limit-ms", type=int, default=1000)
    parser.add_argument("--screenshots", choices=["auto", "always", "never"], default="auto",
                        help="auto = SPA fallback capture при main_text<200 (docs 03/22)")
    parser.add_argument("--vision", action="store_true",
                        help="VLM-анализ снятых скриншотов + мерж в синтез (task 8b; поднимает модель!)")
    parser.add_argument("--vision-model", default="qwen2.5vl:7b")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-real", action="store_true", help="include tasks marked real: true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    hints = load_hints()
    RESULTS_DIR.mkdir(exist_ok=True)
    out = args.out or RESULTS_DIR / f"crawl_{time.strftime('%Y%m%d_%H%M%S')}_{args.mode}{'_dry' if args.dry_run else ''}.jsonl"

    task_list: list[dict] = []
    if args.tasks:
        manifest = yaml.safe_load(args.tasks.read_text(encoding="utf-8"))
        from fixtures_server import build_port_map, serve  # noqa: PLC0415
        port_map = build_port_map()
        serve(port_map)
        for t in manifest["tasks"]:
            if t.get("real") and not args.include_real:
                continue
            if args.task_id and str(t["id"]) not in args.task_id:
                continue
            if "site" in t:
                t["url"] = f"http://127.0.0.1:{port_map[t['site']]}/"
            task_list.append(t)
    elif args.url and args.task:
        task_list = [{"id": "adhoc", "task": args.task, "url": args.url}]
    else:
        parser.error("either --tasks or (--url and --task)")

    async with httpx.AsyncClient() as client:
        for t in task_list:
            label = f"[{t.get('id')}] {t['task'][:60]}"
            print(f"\n=== {label} · mode={args.mode} · model={'dry-run' if args.dry_run else args.model}",
                  file=sys.stderr)
            res = await crawl(t, args, hints, client)
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            ok = {True: "✅", False: "❌", None: "· manual"}[res["auto_success"]]
            print(f"    pages={res['pages_visited']} wall={res['wall_s']}s "
                  f"plan p50/p95={res['plan_p50']}/{res['plan_p95']}s synth={res['synth_s']}s "
                  f"violations={res['violations']} success={ok}", file=sys.stderr)
            print(f"    summary: {str(res['result'].get('summary'))[:160]}", file=sys.stderr)

    print(f"\nResults → {out}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
