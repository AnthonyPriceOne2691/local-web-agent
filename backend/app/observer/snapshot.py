"""Raw DOM → PageSnapshot: экстракция и truncation (docs 03/20)."""

from __future__ import annotations

from app.observer import blockers, links
from app.schemas.snapshot import Heading, InteractiveElement, Link, PageSnapshot

OBSERVE_JS = """() => {
  const pick = sel => document.querySelector(sel);
  const mainEl = pick('main') || pick('[role=main]') || pick('article') || document.body;
  return {
    title: document.title || '',
    meta_description: (pick('meta[name=description]')?.content || ''),
    headings: [...document.querySelectorAll('h1,h2,h3')].slice(0, 20)
      .map(h => ({level: +h.tagName[1], text: (h.innerText || '').trim()})),
    main_text: (mainEl.innerText || ''),
    links: [...document.querySelectorAll('a[href]')].map(a => ({
      href: a.getAttribute('href') || '', text: (a.innerText || '').trim()
    })),
    interactive: [...document.querySelectorAll(
        'button, input:not([type=hidden]), select, textarea, [role=button], [onclick]'
      )]
      .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
      .slice(0, 60)
      .map(el => {
        const tag = el.tagName.toLowerCase();
        const at = n => el.getAttribute(n) || '';
        const isField = tag === 'input' || tag === 'select' || tag === 'textarea';
        const itype = tag === 'input' ? (at('type') || 'text') : '';
        const kind = tag === 'input' ? itype
          : (tag === 'button' || tag === 'select' || tag === 'textarea') ? tag : 'button';
        const label = (isField
          ? (at('aria-label') || at('placeholder') || el.value || at('name'))
          : (el.innerText || at('aria-label') || at('title'))).trim();
        return {kind, label, input_type: itype, name: at('name'), disabled: !!el.disabled};
      }),
    has_password_field: !!pick('input[type=password]'),
  };
}"""

# Caps — doc 20 / doc 03 таблица Page Observer
TITLE_CAP = 200
META_CAP = 300
HEADING_CAP = 200
MAIN_TEXT_CAP = 8000
LINKS_CAP = 40
INTERACTIVE_CAP = 50  # doc 20 token budget — интерактивных элементов на страницу
INTERACTIVE_LABEL_CAP = 120


def build_snapshot(raw: dict, *, page_url: str, origin: str) -> PageSnapshot:
    main_text = (raw.get("main_text") or "")[:MAIN_TEXT_CAP]
    truncated = len(raw.get("main_text") or "") > MAIN_TEXT_CAP
    headings = [
        Heading(level=h.get("level", 2), text=(h.get("text") or "")[:HEADING_CAP])
        for h in (raw.get("headings") or [])[:20]
        if (h.get("text") or "").strip()
    ]
    link_dicts = links.clean_links(page_url, raw.get("links") or [], origin, cap=LINKS_CAP)
    interactive = [
        InteractiveElement(
            index=i,
            kind=(el.get("kind") or "")[:24],
            label=(el.get("label") or "")[:INTERACTIVE_LABEL_CAP],
            input_type=(el.get("input_type") or "")[:24],
            name=(el.get("name") or "")[:80],
            disabled=bool(el.get("disabled")),
        )
        for i, el in enumerate((raw.get("interactive") or [])[:INTERACTIVE_CAP])
    ]
    status = blockers.detect_status(
        url=page_url,
        main_text=main_text,
        title=raw.get("title") or "",
        has_password_field=bool(raw.get("has_password_field")),
    )
    return PageSnapshot(
        url=links.normalize_url(page_url),
        status=status,
        title=(raw.get("title") or "")[:TITLE_CAP],
        meta_description=(raw.get("meta_description") or "")[:META_CAP],
        headings=headings,
        main_text=main_text,
        links=[Link(**d) for d in link_dicts],
        interactive_elements=interactive,
        truncated=truncated,
    )
