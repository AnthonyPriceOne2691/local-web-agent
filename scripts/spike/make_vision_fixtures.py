#!/usr/bin/env python3
"""Рендер fixture-PNG V1–V5 для vision-спайка (doc 19 Part B).

HTML-шаблоны инлайновые (spike), рендер через Playwright → tests/fixtures/screenshots/.
V1 pricing_desktop · V2 spa_empty_dom · V3 cookie_wall · V4 home_mobile · V5 design_home
"""

from __future__ import annotations

import asyncio
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "screenshots"

BASE_CSS = "body{font-family:-apple-system,Helvetica,sans-serif;margin:0;color:#1e293b}"

FIXTURES: dict[str, dict] = {
    "pricing_desktop": {  # V1: 3-tier pricing, Pro price + CTA видимы
        "viewport": (1440, 900),
        "html": f"""<style>{BASE_CSS}
          header{{background:#0f172a;color:#fff;padding:16px 48px;font-weight:700}}
          .tiers{{display:flex;gap:24px;padding:48px}}
          .tier{{flex:1;border:1px solid #e2e8f0;border-radius:16px;padding:32px;text-align:center}}
          .tier.pro{{border:2px solid #2563eb;box-shadow:0 8px 24px rgba(37,99,235,.15)}}
          .price{{font-size:44px;font-weight:800;margin:12px 0}}
          .cta{{background:#2563eb;color:#fff;border:none;border-radius:8px;padding:12px 28px;font-size:16px}}
        </style>
        <header>CloudMetrics</header>
        <h1 style="text-align:center;margin-top:40px">Plans and Pricing</h1>
        <div class="tiers">
          <div class="tier"><h2>Starter</h2><div class="price">$0</div><p>3 dashboards</p></div>
          <div class="tier pro"><h2>Pro</h2><div class="price">$29/mo</div><p>per user</p>
            <button class="cta">Start free trial</button></div>
          <div class="tier"><h2>Enterprise</h2><div class="price">Custom</div><p>Contact sales</p></div>
        </div>""",
    },
    "spa_empty_dom": {  # V2: цена видна на рендере, но её нет в DOM-тексте (CSS content)
        "viewport": (1440, 900),
        "html": f"""<style>{BASE_CSS}
          .card{{margin:120px auto;width:420px;border:1px solid #ddd;border-radius:16px;padding:48px;text-align:center}}
          .plan::after{{content:"FlowDesk Team plan";font-size:22px}}
          .price::after{{content:"$49/mo";font-size:52px;font-weight:800;color:#0f766e;display:block;margin-top:12px}}
        </style>
        <div class="card"><div class="plan"></div><div class="price"></div></div>""",
    },
    "cookie_wall": {  # V3: consent-оверлей закрывает контент — ждём screen_status: obstructed
        "viewport": (1440, 900),
        "html": f"""<style>{BASE_CSS}
          .content{{padding:48px;filter:blur(2px)}}
          .overlay{{position:fixed;inset:0;background:rgba(15,23,42,.65);display:flex;align-items:center;justify-content:center}}
          .modal{{background:#fff;border-radius:16px;padding:40px;width:520px}}
          .btn{{background:#2563eb;color:#fff;border:none;border-radius:8px;padding:12px 24px;margin-right:12px}}
        </style>
        <div class="content"><h1>SuperShop — Deals</h1><p>Today's discounts on electronics…</p></div>
        <div class="overlay"><div class="modal">
          <h2>We value your privacy</h2>
          <p>We use cookies to personalise content and ads. You can accept all cookies or manage preferences.</p>
          <button class="btn">Accept all</button><button class="btn" style="background:#64748b">Reject all</button>
        </div></div>""",
    },
    "home_mobile": {  # V4: мобильный layout — hamburger + одна колонка
        "viewport": (390, 844),
        "html": f"""<style>{BASE_CSS}
          header{{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:#0f172a;color:#fff}}
          .burger{{font-size:24px}}
          .hero{{padding:32px 16px;background:linear-gradient(160deg,#2563eb,#7c3aed);color:#fff}}
          .card{{margin:16px;border:1px solid #e2e8f0;border-radius:12px;padding:20px}}
        </style>
        <header><b>TravelGo</b><span class="burger">☰</span></header>
        <div class="hero"><h1>Find your next trip</h1><p>Compare 500+ airlines</p></div>
        <div class="card"><h3>Bali from $420</h3></div>
        <div class="card"><h3>Tokyo from $610</h3></div>""",
    },
    "design_home": {  # V5: hero + брендовые цвета — ждём ≥2 hex и layout pattern
        "viewport": (1440, 900),
        "html": f"""<style>{BASE_CSS}
          header{{display:flex;justify-content:space-between;padding:20px 64px;background:#fff;border-bottom:1px solid #eee;position:sticky;top:0}}
          nav a{{margin-left:28px;color:#1e293b;text-decoration:none}}
          .hero{{background:#1a1a2e;color:#fff;padding:96px 64px;text-align:center}}
          .hero h1{{font-size:56px;margin:0}}
          .accent{{color:#e94560}}
          .cta{{background:#e94560;color:#fff;border:none;border-radius:10px;padding:16px 40px;font-size:18px;margin-top:28px}}
          .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;padding:48px 64px}}
          .cell{{background:#f8fafc;border-radius:14px;padding:28px}}
        </style>
        <header><b>NovaLabs</b><nav><a href="#">Product</a><a href="#">Pricing</a><a href="#">About</a></nav></header>
        <div class="hero"><h1>Ship <span class="accent">faster</span></h1>
          <p>The developer platform for modern teams</p><button class="cta">Get started</button></div>
        <div class="grid"><div class="cell"><h3>Deploy</h3></div><div class="cell"><h3>Monitor</h3></div>
          <div class="cell"><h3>Scale</h3></div></div>""",
    },
}


async def main() -> None:
    from playwright.async_api import async_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for name, spec in FIXTURES.items():
            w, h = spec["viewport"]
            page = await browser.new_page(viewport={"width": w, "height": h})
            await page.set_content(f"<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
                                   f"<body>{spec['html']}</body></html>")
            await page.wait_for_timeout(300)
            path = OUT / f"{name}.png"
            await page.screenshot(path=str(path))
            print(f"{path.name}: {path.stat().st_size // 1024} KB ({w}x{h})")
            await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
