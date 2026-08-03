"""Raw DOM → PageSnapshot: экстракция и truncation (docs 03/20)."""

from __future__ import annotations

from typing import Any

from app.observer import blockers, links
from app.schemas.snapshot import Heading, InteractiveElement, Link, PageSnapshot

# Интерактивные элементы для action-режима (doc 25 Tier 1) — единый источник правды:
# OBSERVE_JS (сбор) и PlaywrightSession.click_element (клик по индексу) используют его.
INTERACTIVE_SELECTOR = "button, input:not([type=hidden]), select, textarea, [role=button], [onclick]"

OBSERVE_JS = (
    """() => {
  const pick = sel => document.querySelector(sel);
  // `document.body` может отсутствовать: документ ещё течёт (readyState 'loading'), и
  // тела в нём пока нет. Живой замер T-3b: у habr.com body появлялся на 32-й секунде,
  // и снапшот падал `TypeError: reading 'innerText' of null`, унося весь run. Пустой
  // снапшот — состояние обрабатываемое (SPA-fallback + ретрай), исключение — нет.
  const mainEl = pick('main') || pick('[role=main]') || pick('article')
    || document.body || document.documentElement;
  return {
    title: document.title || '',
    meta_description: (pick('meta[name=description]')?.content || ''),
    headings: [...document.querySelectorAll('h1,h2,h3')].slice(0, 20)
      .map(h => ({level: +h.tagName[1], text: (h.innerText || '').trim()})),
    main_text: ((mainEl && mainEl.innerText) || ''),
    links: [...document.querySelectorAll('a[href]')].map(a => ({
      href: a.getAttribute('href') || '', text: (a.innerText || '').trim()
    })),
    interactive: [...document.querySelectorAll('"""
    + INTERACTIVE_SELECTOR
    + """')]
      .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
      .slice(0, 60)
      .map(el => {
        const tag = el.tagName.toLowerCase();
        const at = n => el.getAttribute(n) || '';
        const isField = tag === 'input' || tag === 'select' || tag === 'textarea';
        // button submits только если type=submit И внутри формы; иначе это JS-кнопка (safe)
        const submitter = tag === 'button' && el.type === 'submit' && !!el.form;
        const itype = tag === 'input' ? (el.type || 'text')
          : submitter ? 'submit' : (tag === 'button' && el.type === 'reset') ? 'reset'
          : tag === 'button' ? 'button' : '';
        const kind = tag === 'input' ? itype
          : (tag === 'button' || tag === 'select' || tag === 'textarea') ? tag : 'button';
        const label = (isField
          ? (at('aria-label') || at('placeholder') || el.value || at('name'))
          : (el.innerText || at('aria-label') || at('title'))).trim();
        // value нужен агенту, чтобы видеть УЖЕ заполненные поля и не залипать на
        // первом (живой прогон Tier 3: три fill в одно поле). password — никогда.
        const value = (isField && itype !== 'password') ? String(el.value || '').slice(0, 80) : '';
        return {kind, label, input_type: itype, name: at('name'),
                disabled: !!el.disabled, value};
      }),
    has_password_field: !!pick('input[type=password]'),
  };
}"""
)

# Caps — doc 20 / doc 03 таблица Page Observer
TITLE_CAP = 200
META_CAP = 300
HEADING_CAP = 200
MAIN_TEXT_CAP = 8000
LINKS_CAP = 40
INTERACTIVE_CAP = 50  # doc 20 token budget — интерактивных элементов на страницу
INTERACTIVE_LABEL_CAP = 120


def build_snapshot(raw: dict[str, Any], *, page_url: str, origin: str) -> PageSnapshot:
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
            value=(el.get("value") or "")[:80],
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
