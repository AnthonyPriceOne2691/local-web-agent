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
  // Ветка комментариев — не текст статьи. Замер трёх живых страниц: у King Arthur
  // `div#block-kaf-nextgenweb-blogcomments` даёт 581 слово из 3771 (15 %), у BBC Good Food
  // `div#commentsFeed` — 60 из 964 (6 %). Эти слова уходили в `word_count`, а он идёт прямо
  // в сравнение полноты статей: сайт с активными читателями выигрывал у сайта с длинным
  // текстом. Правило структурное (id/class), словаря слов не требует и потому переносимо.
  //
  // Вычитаем ТЕКСТ блока, а не удаляем узел: клон вне DOM теряет layout, и `innerText`
  // выродился бы в `textContent` для ВСЕЙ страницы (без переносов, со скрытыми элементами).
  // Порог 200 символов оставляет на месте счётчик «COMMENTS 21» и кнопку «Leave a comment» —
  // они часть карточки статьи, а не обсуждение.
  const commentBlocks = el => {
    const found = [...el.querySelectorAll('[id*="comment" i], [class*="comment" i], [itemprop~="comment"]')];
    return found.filter(n => !found.some(o => o !== n && o.contains(n)));
  };
  let mainText = ((mainEl && mainEl.innerText) || '');
  if (mainEl) {
    for (const node of commentBlocks(mainEl)) {
      const t = ((node.innerText || '')).trim();
      if (t.length >= 200) mainText = mainText.replace(t, '');
    }
  }
  return {
    title: document.title || '',
    meta_description: (pick('meta[name=description]')?.content || ''),
    headings: [...document.querySelectorAll('h1,h2,h3')].slice(0, 20)
      .map(h => ({level: +h.tagName[1], text: (h.innerText || '').trim()})),
    main_text: mainText,
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
    // Только ВИДИМОЕ поле пароля — тот же критерий, что у interactive выше. Скрытое
    // модальное окно логина есть почти на каждом магазине, а у SPA сырой текст короткий,
    // поэтому пара «есть password + страница тонкая» давала ложный login_wall: прогон
    // demoblaze.com вставал на первой странице, SPA-fallback отключался (login_wall
    // пропускает networkidle), каталог не рендерился и ответ заявлял, что цен на сайте
    // нет (doc 26 § T-2b-1).
    has_password_field: [...document.querySelectorAll('input[type=password]')]
      .some(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }),
  };
}"""
)

# Caps — doc 20 / doc 03 таблица Page Observer
TITLE_CAP = 200
META_CAP = 300
HEADING_CAP = 200
MAIN_TEXT_CAP = 8000
# Сколько ссылок страницы доходит до ОЦЕНКИ. Это предохранитель по памяти, а не отбор:
# отбор делает очередь кандидатов по счёту (`navigation/candidate_queue`, top-K в промпт).
#
# Замер T-3d (doc 26) показал, почему позиционный лимит — неверный инструмент. Ссылки
# берутся в порядке DOM, и позиция содержимого у каждого сайта своя:
#   • лимит 40  → у `sports.ru/betting/stavochnaya-wiki` в вход попадали только шапка и
#     меню; 50 из 52 тематических ссылок отбрасывались;
#   • лимит 300 → всё равно мимо: ссылки на статьи вики лежат на позициях #345–#351.
# То есть любое фиксированное N режет контент на каком-нибудь сайте. Поэтому здесь стоит
# большой предохранитель (память/время), а решает счёт.
#
# Стоимость честно: 900 ссылок × строковые операции скоринга — миллисекунды; в промпт
# уходит только top-K очереди (10), синтез и извлечение ссылок снапшота не читают вовсе.
LINKS_CAP = 1200
INTERACTIVE_CAP = 50  # doc 20 token budget — интерактивных элементов на страницу
INTERACTIVE_LABEL_CAP = 120


def build_snapshot(raw: dict[str, Any], *, page_url: str, origin: str) -> PageSnapshot:
    full_text = raw.get("main_text") or ""
    main_text = full_text[:MAIN_TEXT_CAP]
    truncated = len(full_text) > MAIN_TEXT_CAP
    # Длину считаем здесь, по полному тексту: дальше он обрезан, и счёт по обрезку занижал
    # длинные статьи до одного и того же числа — а именно оно уходит в сравнение полноты.
    text_words = len(full_text.split())
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
    # Ни текста, ни ссылок — страница не дала ничего: ни содержания, ни хода. Живой замер
    # (doc 26 § T-3p): `chefkoch.de` отдаёт ноль и ноль даже после `networkidle`, скриншот
    # при этом полностью белый — значит и vision смотреть нечего, а страница шла в синтез
    # как содержание сайта.
    #
    # Режем именно по ПАРЕ признаков: у живого SPA пустым бывает только текст, ссылки есть
    # всегда (`vercel.com` 111 слов при 164 ссылках, `heise.de` 12 при 392). По одному
    # тексту правило выбросило бы весь SPA-сценарий, ради которого делается скриншот.
    if status == "ok" and not main_text.strip() and not link_dicts:
        status = "error"
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
        text_words=text_words,
    )
