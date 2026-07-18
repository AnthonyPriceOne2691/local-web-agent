"""Cookie/consent dismissal — D-11 (doc 22): detect → CSS-hide → CMP-click reject-first.

Детерминированный шаг оркестратора перед скриншотом (не LLM-действие, вне ABC —
doc 13). Default-ступень hide не взаимодействует со страницей: согласие никому
не даётся. Селекторы — данные (`data/navigation/consent_selectors.yaml`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

import yaml

CLICK_TIMEOUT_MS = 2000
_ID_WILDCARD = re.compile(r"#([\w-]+?)_?\*")  # "#sp_message_container_*" → [id^='…']


class ConsentBrowser(Protocol):
    async def eval_js(self, script: str): ...

    async def click_first(self, selectors: list[str], *, timeout_ms: int) -> str | None: ...


class ConsentHandler:
    def __init__(self, spec: dict):
        detect = spec.get("detect") or {}
        self._keywords = [
            str(k).lower()
            for key in ("keywords_en", "keywords_ru", "keywords_other")
            for k in (detect.get(key) or [])
        ]
        self._coverage = float(detect.get("min_viewport_coverage", 0.25))
        self._z_index = int(detect.get("min_z_index", 1000))
        raw_hide = [s for s in (spec.get("hide_selectors") or []) if isinstance(s, str)]
        self._hide_selectors = [_normalize_selector(s) for s in raw_hide]
        clicks = spec.get("click_selectors") or {}
        self._reject = list(clicks.get("reject") or [])
        self._accept = list(clicks.get("accept") or [])

    @classmethod
    def load(cls, navigation_dir: Path) -> ConsentHandler:
        path = navigation_dir / "consent_selectors.yaml"
        spec = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
        return cls(spec or {})

    async def dismiss(
        self,
        browser: ConsentBrowser,
        *,
        mode: str = "auto",              # auto | hide_only | never
        click_mode: str = "reject_first",  # reject_first | accept | never
        site_click_used: bool = False,
    ) -> str:
        """→ none | hidden | clicked_reject | clicked_accept | failed (doc 22)."""
        if mode == "never" or not await self._detected(browser):
            return "none"
        await browser.eval_js(self._hide_script())
        if not await self._detected(browser):
            return "hidden"
        if mode == "hide_only" or click_mode == "never" or site_click_used:
            return "failed"
        selectors = self._accept if click_mode == "accept" else self._reject
        clicked = await browser.click_first(selectors, timeout_ms=CLICK_TIMEOUT_MS)
        if clicked is None:
            return "failed"
        return "clicked_accept" if click_mode == "accept" else "clicked_reject"

    # ------------------------------------------------------------ internals
    async def _detected(self, browser: ConsentBrowser) -> bool:
        return bool(await browser.eval_js(self._detect_script()))

    def _detect_script(self) -> str:
        return f"""
() => {{
  const kws = {json.dumps(self._keywords, ensure_ascii=False)};
  const els = document.querySelectorAll("div,section,aside,dialog");
  const vw = innerWidth || 1, vh = innerHeight || 1;
  let checked = 0;
  for (const el of els) {{
    if (++checked > 400) break;
    const cs = getComputedStyle(el);
    if (cs.display === "none" || !["fixed", "sticky"].includes(cs.position)) continue;
    const z = parseInt(cs.zIndex, 10) || 0;
    if (z < {self._z_index}) continue;
    const r = el.getBoundingClientRect();
    if ((r.width * r.height) / (vw * vh) < {self._coverage}) continue;
    const hay = ((el.innerText || "") + " " + el.id + " " + el.className).toLowerCase();
    if (kws.some(k => hay.includes(k))) return true;
  }}
  return false;
}}"""

    def _hide_script(self) -> str:
        return f"""
() => {{
  const sels = {json.dumps(self._hide_selectors)};
  for (const sel of sels) {{
    try {{
      document.querySelectorAll(sel).forEach(el =>
        el.style.setProperty("display", "none", "important"));
    }} catch (e) {{}}
  }}
  for (const el of [document.documentElement, document.body]) {{
    if (el) {{ el.style.setProperty("overflow", "auto", "important"); }}
  }}
  return true;
}}"""


def _normalize_selector(selector: str) -> str:
    """'#foo_*' (substring-пометка из YAML) → атрибутный CSS [id^='foo_']."""
    return _ID_WILDCARD.sub(lambda m: f"[id^='{m.group(1)}_']", selector)
