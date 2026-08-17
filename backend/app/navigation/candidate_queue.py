"""CandidateQueue P0–P4 (doc 21): порядок фиксирован до budget-cut (урок SEOLB §9).

Каждое ведро наполняет свой источник — ссылки текущей страницы, кэшированная
homepage, ссылки F1-проб, живые slug-пробы, sitemap, legal-пробы. Порядок вёдер и
есть политика приоритетов, поэтому сборка каждого источника вынесена отдельно, а
слияние с дедупликацией — одно на всех.
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.navigation.link_scorer import looks_like_entry, score_link
from app.navigation.path_hints import PathHints
from app.observer.links import normalize_url, same_site
from app.schemas.snapshot import Candidate, PageSnapshot

# Индексы вёдер: P0 · P1 · P2 probes · P2.5 sitemap · P3 legal · P4 rest (doc 21)
P0_PAGE_SIGNAL = 0
P1_HOMEPAGE_AND_PROBE_LINKS = 1
P2_ALIVE_PROBES = 2
P25_SITEMAP = 3
P3_LEGAL = 4
P4_REST = 5
BUCKET_COUNT = 6

# Причины, по которым ссылка считается «со смыслом» и уходит в P0, а не в хвост.
# `entry`/`headline` добавлены после T-3d (doc 26): без них ссылки на сами статьи
# оказывались в хвосте P4 и вылетали за top_k, поэтому агент ходил только по разделам,
# а модель предлагала URL вне очереди (I-H6).
SIGNAL_TAGS = ("slug", "task-kw", "homepage+intent", "entry", "headline")

# Релевантный кандидат для G-S1 (early stop) — сигнальный тег ИЛИ источник-проба.
# Живёт рядом с SIGNAL_TAGS, а не в orchestrator: это один словарь причин, и раньше
# два кортежа расходились — тег `entry` пришлось бы добавлять в двух местах.
RELEVANT_TAGS = (*SIGNAL_TAGS, "probe", "sitemap", "legal-contact")

# Подразделы текущей страницы (ход вглубь) **добавляются** к top-K, а не вытесняют записи.
# Замер (doc 26 § Проверка эталона): человек дошёл до статьи ходом вики → «Виды спорта» →
# статья, а у агента ссылка на подраздел стояла #33 из 374 — очками ей с записями страницы
# не тягаться (нет ни формы записи, ни заголовка).
#
# Предел 4 выбран замером, а не на глаз: на восьми снятых страницах подразделов 0 · 3 · 6 · 17,
# и нужный лежал в первых трёх. Меньше четырёх — выбор за агента делает произвольный порядок
# DOM (на хабе вики шесть равных по счёту подразделов), больше — растёт промпт там, где у
# раздела два десятка детей.
SUBSECTION_SLOTS = 4

# Разделы, которых в окне нет вовсе, дописываются в хвост очереди. Модель должна видеть,
# что вообще предлагает страница, а не десять образцов с одной полки: на корне
# `legalbet.ru` девять из десяти мест занимали почти одинаковые рекламные страницы.
#
# Пробовался и **отклонён замером** более сильный вариант — обход по кругу разделам: ширина
# получалась ценой тематичности (на `championat.com/bets/` доля тематических в top-10 падала
# 10/10 → 4/10, нужная ссылка вылетала). Поэтому правило добавляющее, как и слоты
# подразделов: окно по счёту не трогаем, дописываем максимум две ссылки.
#
# Знать слово «бонус» для этого не нужно — правило работает на магазине и новостях так же.
BREADTH_SLOTS = 2


def _fresh_links(links: list[dict[str, str]], origin: str, visited: set[str]) -> list[dict[str, str]]:
    """Свои и ещё не посещённые. visited отсекается у каждого источника."""
    return [
        link
        for link in links
        if same_site(link["href"], origin) and normalize_url(link["href"]) not in visited
    ]


def _page_links(snapshot: PageSnapshot) -> list[dict[str, str]]:
    return [{"href": ln.href, "text": ln.text} for ln in snapshot.links]


def _scored(
    links: list[dict[str, str]],
    *,
    intent: str,
    task: str,
    hints: PathHints,
    on_homepage: bool,
    prefix: str = "",
    positive_only: bool = False,
    page_context: str = "",
) -> list[Candidate]:
    """Ссылки → кандидаты со счётом. `prefix` в reason сохраняет источник ссылки:
    без него нельзя отличить ссылку с текущей страницы от homepage или F1-пробы.

    `page_context` — где стоит агент (URL + заголовок текущей страницы). Он нужен правилу
    «различает то слово задачи, которого в контексте нет» (doc 21 § Выбор внутри раздела) и
    передаётся только ссылкам **текущей** страницы: у кэша homepage и проб контекст другой.
    """
    out: list[Candidate] = []
    for link in links:
        score, reason = score_link(
            link,
            intent=intent,
            task=task,
            hints=hints,
            on_homepage=on_homepage,
            page_context=page_context,
        )
        if positive_only and score <= 0:
            continue
        out.append(Candidate(href=link["href"], text=link["text"], score=score, reason=prefix + reason))
    return out


def _from_urls(urls: list[str], visited: set[str], *, text: str, score: int, reason: str) -> list[Candidate]:
    """Пробы, sitemap и legal приходят голыми URL — счёт у них фиксированный (doc 21)."""
    return [
        Candidate(href=url, text=text, score=score, reason=reason)
        for url in urls
        if normalize_url(url) not in visited
    ]


def _subsections(candidates: list[Candidate], page_path: str) -> list[Candidate]:
    """Подразделы текущей страницы: путь глубже её собственного и это не запись.

    Именно этот ход делает человек на странице-хабе («Ставочная вики» → «Виды спорта» →
    статья), и именно он был закрыт агенту: подраздел не имеет ни формы записи, ни
    заголовка, поэтому по счёту всегда проигрывает записям самой страницы.
    """
    base = page_path.rstrip("/")
    if not base:  # на главной «подраздел» — это любой раздел сайта, резервировать нечего
        return []
    deeper = []
    for cand in candidates:
        path = urlparse(cand.href).path.rstrip("/")
        if path.startswith(f"{base}/") and not looks_like_entry(path):
            deeper.append(cand)
    return sorted(deeper, key=lambda c: -c.score)


def _with_subsections(queue: list[Candidate], subsections: list[Candidate]) -> list[Candidate]:
    """Добавить ходы вглубь к top-K, не вытесняя записи страницы.

    Именно добавить: записи — это возможный ответ, а подраздел — путь к ответу, и менять
    одно на другое значило бы чинить один провал ценой другого. Цена честная и маленькая:
    промпт растёт максимум на четыре строки, и только на страницах-хабах.
    """
    seen = {normalize_url(c.href) for c in queue}
    return queue + [c for c in subsections if normalize_url(c.href) not in seen][:SUBSECTION_SLOTS]


def _with_unseen_sections(queue: list[Candidate], page_scored: list[Candidate]) -> list[Candidate]:
    """Дописать в хвост лучшие ссылки разделов, которых в окне нет вообще.

    Именно дописать, а не потеснить: окно по счёту — это возможный ответ, а незнакомый
    раздел — подсказка, что на странице есть ещё что-то. Замер отверг более сильный вариант
    (обход по кругу): он давал ширину ценой тематичности.
    """
    if not queue:
        return queue
    known = {_section_key(c.href) for c in queue}
    seen_urls = {normalize_url(c.href) for c in queue}
    extra: list[Candidate] = []
    for cand in sorted(page_scored, key=lambda c: -c.score):
        key = _section_key(cand.href)
        if key in known or normalize_url(cand.href) in seen_urls:
            continue
        known.add(key)
        extra.append(cand)
        if len(extra) >= BREADTH_SLOTS:
            break
    return queue + extra


def _section_key(href: str) -> str:
    """Раздел ссылки — первый сегмент пути: `/bonus/x` и `/bonus/y` — одна полка."""
    parts = [p for p in urlparse(href).path.split("/") if p]
    return parts[0] if parts else ""


def _merge(buckets: list[list[Candidate]], top_k: int) -> list[Candidate]:
    """Вёдра по порядку, внутри ведра — по убыванию счёта; дубли между источниками
    отбрасываются: побеждает более раннее ведро. Окно по счёту — и ничего сверх него:
    за разнообразие отвечает `_with_unseen_sections`, дописывающий хвост.
    """
    seen: set[str] = set()
    queue: list[Candidate] = []
    for bucket in buckets:
        for cand in sorted(bucket, key=lambda c: -c.score):
            n = normalize_url(cand.href)
            if n not in seen:
                seen.add(n)
                queue.append(cand)
    return queue[:top_k]


def build_candidates(
    *,
    snapshot: PageSnapshot,
    homepage: PageSnapshot | None,
    intent: str,
    task: str,
    hints: PathHints,
    origin: str,
    visited: set[str],
    alive_probes: list[str],
    legal_probes: list[str],
    sitemap_urls: list[str] | None = None,
    probe_links: list[dict[str, str]] | None = None,
    top_k: int = 10,
) -> list[Candidate]:
    is_home = urlparse(snapshot.url).path.rstrip("/") in ("", "/")
    buckets: list[list[Candidate]] = [[] for _ in range(BUCKET_COUNT)]

    # P0: ссылки текущей страницы с intent/task-сигналом; P4: остальные
    page_scored = _scored(
        _fresh_links(_page_links(snapshot), origin, visited),
        intent=intent,
        task=task,
        hints=hints,
        on_homepage=is_home,
        page_context=f"{snapshot.url} {snapshot.title or ''}",
    )
    for cand in page_scored:
        tier = P0_PAGE_SIGNAL if any(tag in cand.reason for tag in SIGNAL_TAGS) else P4_REST
        buckets[tier].append(cand)

    # P1: ссылки с закэшированной homepage + ссылки с F1-проб (doc 03) — s > 0
    if homepage is not None and homepage.url != snapshot.url:
        buckets[P1_HOMEPAGE_AND_PROBE_LINKS] += _scored(
            _fresh_links(_page_links(homepage), origin, visited),
            intent=intent,
            task=task,
            hints=hints,
            on_homepage=True,
            prefix="home:",
            positive_only=True,
        )
    buckets[P1_HOMEPAGE_AND_PROBE_LINKS] += _scored(
        _fresh_links(probe_links or [], origin, visited),
        intent=intent,
        task=task,
        hints=hints,
        on_homepage=False,
        prefix="f1:",
        positive_only=True,
    )

    # P2: живые slug-пробы (HTTP-alive, doc 19 lesson); P2.5 sitemap; P3 legal (contact)
    buckets[P2_ALIVE_PROBES] = _from_urls(
        alive_probes, visited, text="(slug probe)", score=12, reason="probe"
    )
    buckets[P25_SITEMAP] = _from_urls(
        sitemap_urls or [], visited, text="(sitemap)", score=10, reason="sitemap"
    )
    buckets[P3_LEGAL] = _from_urls(legal_probes, visited, text="(legal probe)", score=8, reason="legal-probe")

    # Ход вглубь текущей страницы получает свои слоты: очками подраздел с записями
    # страницы не тягается, а без него агент не мог дойти до статьи вовсе (doc 26).
    subsections = _subsections(page_scored, urlparse(snapshot.url).path)
    for cand in subsections:
        cand.reason = f"{cand.reason}+subsection" if "subsection" not in cand.reason else cand.reason
    queue = _with_subsections(_merge(buckets, top_k), subsections)
    return _with_unseen_sections(queue, page_scored)
