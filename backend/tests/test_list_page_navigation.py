"""Оценка ссылок на страницах-списках (doc 21 § Записи против разделов, doc 26 § T-3d).

Находка живого прогона T-3d: три реальных портала со статьями про ставки на футбол,
агент прошёл раздел → раздел → раздел и **не открыл ни одной статьи**, после чего
заявил, что статей на сайтах нет. Статьи там есть — их URL взяты из выдачи и стоят в
этом тесте как эталон.

Причина была в весах формулы: `slug` (+12) и `shallow` (+3) достаются страницам-спискам
(`/news`, `/betting`), а ссылка на статью получала 0 — заголовок не совпадал с текстом
задачи буквально, путь не совпадал ни с одним слугом. Агент шёл туда, где счёт выше.

Признаки в тестах **структурные** (форма URL записи, длина заголовка), а не под эти три
сайта: иначе правка была бы подгонкой под результат.
"""

from __future__ import annotations

from app.navigation.candidate_queue import RELEVANT_TAGS, SIGNAL_TAGS, build_candidates
from app.navigation.link_scorer import score_link
from app.navigation.path_hints import PathHints
from tests.conftest import REPO_ROOT
from tests.test_snapshot_and_queue import ORIGIN, snap

HINTS = PathHints.load(REPO_ROOT / "data" / "navigation")
TASK = "Найди статью о том, как делать ставки на футбол, и сравни, где тема раскрыта полнее"

# Эталон: настоящие статьи с трёх сайтов (из выдачи, проверены HTTP-пробой).
REAL_ARTICLES = (
    "https://legalbet.ru/shkola-bettinga/stavki-na-futbol/",
    "https://www.sports.ru/betting/stavochnaya-wiki/3067963-kak-pravilno-delat-stavki-na-futbol.html",
    "https://www.championat.com/bets/article-3964176-kak-stavit-stavki-na-futbol-sekrety.html",
)
# Разделы, по которым агент ходил вместо статей.
SECTION_PAGES = (
    "https://legalbet.ru/news",
    "https://www.sports.ru/betting",
    "https://www.sports.ru/football",
    "https://www.championat.com/bets",
)


def scored(href: str, text: str = "", *, on_homepage: bool = False, intent: str = "content_search"):
    return score_link(
        {"href": href, "text": text}, intent=intent, task=TASK, hints=HINTS, on_homepage=on_homepage
    )


# --- запись против раздела ---


def test_real_article_links_score_above_section_links():
    """Главный критерий правки: статья должна побеждать раздел, а не наоборот."""
    worst_article = min(scored(url, "Как правильно делать ставки на футбол")[0] for url in REAL_ARTICLES)
    best_section = max(scored(url, "Ставки")[0] for url in SECTION_PAGES)
    assert worst_article > best_section, (
        f"статья {worst_article} должна быть выше раздела {best_section} — иначе агент снова "
        "пойдёт по списку списков"
    )


def test_entry_shapes_recognized():
    for url in (
        "https://x.test/2026/03/20/rust-challenges",  # дата в пути
        "https://x.test/wiki/3067963-kak-delat-stavki",  # числовой id
        "https://x.test/bets/article-3964176-kak-stavit",  # id внутри слуга
        "https://x.test/blog/kak-delat-stavki-na-futbol",  # длинный слуг из 3+ слов
        "https://x.test/news/post.html",  # .html
    ):
        _score, reason = scored(url)
        assert "entry" in reason, url


def test_section_pages_are_not_entries():
    for url in SECTION_PAGES:
        _score, reason = scored(url)
        assert "entry" not in reason, url


# --- контекст: где стоит агент ---


def test_section_slug_helps_only_from_the_homepage():
    """Словарь слугов нужен, чтобы ВОЙТИ в раздел; внутри он уводил в соседний раздел
    (news → бонусы → букмекеры на живом прогоне)."""
    from_home = scored("https://legalbet.ru/news", "Новости", on_homepage=True)[1]
    from_inside = scored("https://legalbet.ru/news", "Новости", on_homepage=False)[1]
    assert "slug" in from_home
    assert "slug" not in from_inside


def test_shallow_bonus_is_off_while_hunting_an_article():
    """Малая глубина тянет назад к спискам, когда ищем статью."""
    assert "shallow" not in scored("https://x.test/news", intent="content_search")[1]
    assert "shallow" in scored("https://x.test/contact", intent="contact")[1]


# --- заголовок против навигационной подписи ---


def test_headline_text_counts_only_for_article_hunt():
    long_title = "Как правильно делать ставки на футбол: стратегии и ошибки"
    assert "headline" in scored("https://x.test/a/b/c-d-e", long_title)[1]
    assert "headline" not in scored("https://x.test/a/b/c-d-e", "Новости")[1]
    assert "headline" not in scored("https://x.test/a/b/c-d-e", long_title, intent="contact")[1]


def test_task_word_matches_by_prefix_not_substring():
    """«ставки» в задаче должно ловить «ставках» в заголовке, но не совпадать внутри слова."""
    assert "task-kw" in scored("https://x.test/p", "Всё о ставках на футбол")[1]
    assert "task-kw" not in scored("https://x.test/p", "Обзор новинок кино")[1]


# --- очередь и early stop ---


def test_entry_is_a_signal_tag_for_both_queue_and_early_stop():
    """Тег обязан быть в обоих списках: иначе статья либо не попадёт в P0, либо
    не посчитается «новой релевантной ссылкой» и агент остановится на списке."""
    assert "entry" in SIGNAL_TAGS
    assert "entry" in RELEVANT_TAGS


def test_article_links_reach_the_queue_from_a_list_page():
    """Список из десятков записей: статьи должны попасть в очередь, а не выпасть за top_k."""
    entries = [
        (
            f"{ORIGIN}/betting/wiki/{3067963 + i}-kak-delat-stavki-na-futbol",
            f"Как делать ставки на футбол — часть {i} подробно",
        )
        for i in range(12)
    ]
    nav = [(f"{ORIGIN}/{slug}", slug) for slug in ("news", "football", "hockey", "about")]
    snapshot = snap(f"{ORIGIN}/betting", title="Ставки", text="лента " * 50, links=nav + entries)

    queue = build_candidates(
        snapshot=snapshot,
        homepage=None,
        intent="content_search",
        task=TASK,
        hints=HINTS,
        origin=ORIGIN,
        visited=set(),
        alive_probes=[],
        legal_probes=[],
    )

    hrefs = [c.href for c in queue]
    assert any("/wiki/" in h for h in hrefs), "ни одной записи не попало в очередь"
    # Записи должны стоять раньше навигации — очередь и есть политика приоритетов.
    first_entry = next(i for i, h in enumerate(hrefs) if "/wiki/" in h)
    nav_positions = [i for i, h in enumerate(hrefs) if h.rstrip("/").endswith(("news", "hockey", "about"))]
    assert not nav_positions or first_entry < max(nav_positions)


# --- штрафы: признак ищется в пути, а не во всём URL (T-3e) ---


def test_penalties_do_not_fire_on_the_host_name():
    """Найдено офлайн-оракулом на корне `legalbet.ru`: штраф `legal-avoid` (−8) стоял у
    **каждой** ссылки сайта, потому что подстрока `/legal` совпадает внутри `//legalbet`.

    Тот же класс ошибки, что `ui` внутри `g-ui-de` (T-3a): признак сравнивался с целым
    URL вместо пути. Здесь он бьёт по любому сайту, чьё имя начинается со слова из
    словаря, — а имена букмекерских обзорников как раз такие.
    """
    for href in (
        "https://legalbet.ru/shkola-bettinga/stavki-na-futbol",  # /legal в имени хоста
        "https://cartier.com/watches/santos-de-cartier-2026",  # /cart в имени хоста
        "https://logincorp.example/blog/kak-delat-stavki-na-futbol",  # /login в имени хоста
        "https://terms-of-sport.example/wiki/3067963-kak-delat-stavki",  # /terms в имени хоста
    ):
        _score, reason = scored(href, "Как делать ставки на футбол: разбор")
        assert "legal-avoid" not in reason, href
        assert "forbidden" not in reason, href


def test_penalties_still_fire_on_the_real_path():
    """Обратная сторона: настоящие юридические и служебные страницы штраф получают."""
    assert "legal-avoid" in scored("https://x.test/privacy-policy", "Privacy")[1]
    assert "legal-avoid" in scored("https://x.test/terms", "Terms")[1]
    assert "forbidden" in scored("https://x.test/cart", "Корзина")[1]
    assert "forbidden" in scored("https://x.test/account/login", "Войти")[1]
    # У интента contact юридические страницы — цель, а не помеха (прежнее поведение).
    assert "legal-avoid" not in scored("https://x.test/privacy", "Privacy", intent="contact")[1]


# --- лимит ссылок: он скрывал от агента содержимое страницы (T-3d) ---


def test_topical_links_survive_the_cap_on_a_portal_sized_page():
    """Замер T-3d: у реальных порталов 420–879 ссылок, и 98–99.5 % тематических лежали
    за прежним лимитом 40 — а ссылки берутся в порядке DOM, где первыми идут шапка и
    меню. Формула оценки не получала шанса: она работала по навигации."""
    from app.observer.links import clean_links
    from app.observer.snapshot import LINKS_CAP

    nav = [{"href": f"{ORIGIN}/section-{i}", "text": f"Раздел {i}"} for i in range(40)]
    articles = [
        {
            "href": f"{ORIGIN}/betting/wiki/{3067963 + i}-kak-delat-stavki-na-futbol",
            "text": f"Как делать ставки на футбол — разбор {i}",
        }
        for i in range(10)
    ]

    cleaned = clean_links(f"{ORIGIN}/betting", nav + articles, ORIGIN, cap=LINKS_CAP)

    assert any("/wiki/" in link["href"] for link in cleaned), (
        "статьи снова обрезаны меню — агент не увидит содержимого страницы"
    )
    assert LINKS_CAP >= 900, (
        "позиция контента у каждого сайта своя: на sports.ru статьи вики лежат на #345+, "
        "поэтому лимит — предохранитель по памяти, а отбирает счёт"
    )


def test_content_link_survives_even_deep_in_dom_order():
    """Главный урок T-3d: позиционный лимит режет контент, потому что позиция у каждого
    сайта своя. Отбор — по счёту в очереди, а не по месту в DOM."""
    from app.observer.links import clean_links
    from app.observer.snapshot import LINKS_CAP

    filler = [{"href": f"{ORIGIN}/menu/{i}", "text": f"Пункт {i}"} for i in range(900)]
    deep_article = {
        "href": f"{ORIGIN}/betting/stavochnaya-wiki/3268942-chto-takoe-fora-v-stavkax.html",
        "text": "Что такое фора (-2) в ставках на спорт",
    }

    cleaned = clean_links(f"{ORIGIN}/betting", [*filler, deep_article], ORIGIN, cap=LINKS_CAP)
    assert any("3268942" in link["href"] for link in cleaned)

    queue = build_candidates(
        snapshot=snap(
            f"{ORIGIN}/betting",
            title="Вики",
            text="w " * 60,
            links=[(link["href"], link["text"]) for link in cleaned],
        ),
        homepage=None,
        intent="content_search",
        task=TASK,
        hints=HINTS,
        origin=ORIGIN,
        visited=set(),
        alive_probes=[],
        legal_probes=[],
    )
    assert any("3268942" in c.href for c in queue), "статья с позиции #900 обязана дойти до очереди"


def test_cap_still_bounds_pathological_pages():
    """Лимит остаётся: он защищает память и время, просто больше не режет содержимое."""
    from app.observer.links import clean_links
    from app.observer.snapshot import LINKS_CAP

    many = [{"href": f"{ORIGIN}/p/{i}", "text": f"link {i}"} for i in range(LINKS_CAP * 3)]
    assert len(clean_links(f"{ORIGIN}/", many, ORIGIN, cap=LINKS_CAP)) == LINKS_CAP
