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


def scored(
    href: str,
    text: str = "",
    *,
    on_homepage: bool = False,
    intent: str = "content_search",
    page_context: str = "",
):
    return score_link(
        {"href": href, "text": text},
        intent=intent,
        task=TASK,
        hints=HINTS,
        on_homepage=on_homepage,
        page_context=page_context,
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


# --- тема в транслитерированном пути (hop-1: узкое место первого хопа) ---


def test_task_topic_matches_a_transliterated_path():
    """Дыра правки T-3d: она учила искать тему **в словах пути**, но у русских сайтов путь
    записан латиницей, а задача приходит по-русски — и `task-kw` не срабатывал вообще.

    Замер: `sports.ru/betting/stavochnaya-wiki` (эталонная вики про ставки) стояла #134 из
    731 со счётом 11, потому что текст ссылки пуст, а путь латинский. 10-е место на том же
    корне стоило 37 — то есть в промпт она не попадала никогда.
    """
    for href in (
        "https://www.sports.ru/betting/stavochnaya-wiki",  # ставки → stav|ochnaya
        "https://legalbet.ru/shkola-bettinga/stavki-na-futbol",  # ставки + футбол
        "https://www.championat.com/bets/article-3964176-kak-stavit-stavki-na-futbol",
    ):
        _score, reason = scored(href)  # текст ссылки пустой — судить можно только по пути
        assert "task-kw" in reason, href


def test_service_words_of_the_task_are_not_a_topic_signal():
    """Обратная сторона транслитерации: служебные слова задачи («найди», «статью», «сайте»)
    иначе начинают ловить чужие пути — `статью` → `stat` совпало бы с `/stat/football`,
    то есть страница статистики стала бы «по теме». Словарь стоп-слов уже был в
    sitemap-фильтре; теперь он один на двух потребителей."""
    for href in (
        "https://www.championat.com/stat/football",  # статью → stat
        "https://www.sports.ru/football/team/spartak-moskva",  # ни одного слова задачи
        "https://legalbet.ru/sajt-obzor",  # сайте → sajt
    ):
        _score, reason = scored(href)
        assert "task-kw" not in reason, href


def test_prefix_matching_admits_its_false_positives():
    """Граница метода, названная честно: тема ищется префиксом от 4 символов и правую
    границу слова не проверяет — поэтому «ставки» совпадает и с «Ставрополем». Это
    **уже** так для кириллицы (`matching`: половина словаря — стемы), транслитерация
    новый класс ошибки не вносит. Тест держит это как известное свойство, а не как баг:
    если кто-то решит ужесточить, он увидит, что цена — `stavochnaya` (эталонная вики
    `sports.ru`), которая по полному слову не совпадёт.
    """
    assert "task-kw" in scored("https://www.sports.ru/football/team/stavropol")[1]
    assert "task-kw" in scored("https://x.test/p", "Ставрополь — трансферы")[1]


def test_cyrillic_link_text_still_matches_without_translit():
    """Транслитерация — добавка, а не замена: русский текст ссылки должен ловиться как был."""
    assert "task-kw" in scored("https://x.test/p/1", "Всё о ставках на футбол")[1]


# --- подраздел текущей страницы: ход вглубь, который делает человек ---


def test_subsection_of_the_current_page_reaches_the_queue():
    """Проверка эталона руками (doc 26): я дошёл до статьи ходом корень → «Ставочная вики»
    → **«Виды спорта»** → статья. У агента ссылка на подраздел стояла **#33 из 374** — за
    пределами top-10, а `I-H6` дальше очереди не пускает, поэтому этот ход был ему закрыт.

    Страница-хаб забита записями с высоким счётом (все со статьями «Стратегии ставок на …»),
    и подраздел по счёту с ними не тягается: у него нет ни формы записи, ни заголовка. Значит
    место в очереди ему надо **резервировать**, а не добирать очками — иначе агент видит
    только соседние статьи и вглубь не идёт никогда.
    """
    entries = [
        (f"{ORIGIN}/betting/wiki/{3128156 + i}-luchshie-strategii-stavok-na-total", f"Стратегии ставок {i}")
        for i in range(20)
    ]
    subsections = [
        (f"{ORIGIN}/betting/wiki/vidy-sporta", "Виды спорта"),
        (f"{ORIGIN}/betting/wiki/vidy-stavok", "Виды ставок"),
    ]
    snapshot = snap(
        f"{ORIGIN}/betting/wiki",
        title="Ставочная вики: как делать ставки",
        text="Обширный источник знаний о ставках " * 20,
        links=entries + subsections,
    )
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
    assert any("vidy-" in h for h in hrefs), f"подраздела нет в очереди: {hrefs}"
    # Записи страницы при этом остаются: слот резервируется, а не отдаётся весь список.
    assert sum(1 for h in hrefs if "-luchshie-" in h) >= 7


def test_entry_is_not_mistaken_for_a_subsection():
    """Статья по пути тоже «глубже» текущей страницы — но это запись, а не подраздел, и
    резервировать под неё слот не нужно: она попадает в очередь по счёту."""
    from app.navigation.link_scorer import looks_like_entry

    assert looks_like_entry("/betting/wiki/3128156-luchshie-strategii-stavok")
    assert not looks_like_entry("/betting/wiki/vidy-sporta")


def test_homepage_has_no_subsections_to_reserve():
    """На главной «подраздел» — это любой раздел сайта, и резервировать было бы нечего:
    правило про ход **вглубь текущей** страницы."""
    links = [(f"{ORIGIN}/betting", "Ставки"), (f"{ORIGIN}/football", "Футбол")]
    queue = build_candidates(
        snapshot=snap(f"{ORIGIN}/", title="Главная", text="site " * 40, links=links),
        homepage=None,
        intent="content_search",
        task=TASK,
        hints=HINTS,
        origin=ORIGIN,
        visited=set(),
        alive_probes=[],
        legal_probes=[],
    )
    assert [c.href for c in queue]  # очередь есть
    assert not any("subsection" in c.reason for c in queue)


# --- выбор ВНУТРИ раздела: различает то, чего нет в контексте страницы ---


def test_subject_not_in_page_context_breaks_the_tie_inside_a_section():
    """Замер на хабе `legalbet.ru/shkola-bettinga/`: эталонная статья про футбол стояла #26
    из 212, а top-12 занимали «Как делать ставки в БК X» — все со счётом 44 против 38.
    Признаки совпадали полностью (тема, жанр, форма записи), слов задачи совпало столько же
    (2 против 2), и единственное различие работало **против** ответа: у эталона короткая
    точная подпись «Ставки на футбол», поэтому он не получал `headline`.

    Разделяющее правило нашлось без параметров: стоя в разделе «Школа ставок: обучение как
    делать ставки», слова «делать» и «ставки» знают **все** ссылки раздела — они уже в
    контексте самой страницы. Различает то слово задачи, которого в контексте нет.
    """
    hub = "https://legalbet.ru/shkola-bettinga/ Школа ставок на спорт: обучение как делать ставки"
    etalon = scored(
        "https://legalbet.ru/shkola-bettinga/stavki-na-futbol", "Ставки на футбол", page_context=hub
    )
    neighbour = scored(
        "https://legalbet.ru/shkola-bettinga/kak-delat-stavki-v-bk-leon-instruktciya",
        "Как делать ставки в БК «Леон»",
        page_context=hub,
    )
    assert "subject" in etalon[1], etalon
    assert "subject" not in neighbour[1], neighbour
    assert etalon[0] > neighbour[0], (
        f"эталон {etalon[0]} обязан обойти соседа {neighbour[0]}: он про футбол, а тот про БК"
    )


def test_without_page_context_scoring_is_unchanged():
    """Негативный контроль: без контекста страницы признак не начисляется вовсе — иначе
    правка меняла бы счёт везде, включая первый шаг с корня."""
    assert "subject" not in scored("https://x.test/a/stavki-na-futbol", "Ставки на футбол")[1]


def test_word_already_in_page_context_stops_discriminating():
    """Обратная сторона правила: если слово задачи есть в контексте страницы, оно ничего не
    различает и бонуса не даёт — иначе бонус получили бы **все** ссылки раздела."""
    ctx = "https://x.test/football/ Футбол: новости"
    assert "subject" not in scored("https://x.test/football/match-1", "Футбол: матч", page_context=ctx)[1]


# --- обучающий жанр против промо (hop-1) ---


def test_learning_genre_is_recognized():
    """Замер hop-1: обучающий раздел — это то, что задача «как делать ставки» и просит, но
    формула его ничем не отличала от новости. Признак структурный (жанр раздела), а не
    список этих трёх сайтов: `wiki`, `school`, `academy`, `guide` встречаются у всех."""
    for href in (
        "https://legalbet.ru/shkola-bettinga",
        "https://www.sports.ru/betting/stavochnaya-wiki",
        "https://www.championat.com/bets/_study.html",
        "https://x.test/academy/betting-basics",
        "https://x.test/ru/obuchenie/stavki",
    ):
        assert "learn" in scored(href)[1], href


def test_learning_genre_reinforces_the_topic_but_does_not_replace_it():
    """Найдено замером сразу после первой версии правки: при безусловном весе жанра
    `championat.com/guide/lifestyle` (жанр есть, темы нет, текст пуст) поднялся на #9 корня
    и вытеснил статью про ставки. Это ровно ошибка T-3d «форма выше темы», повторённая на
    другом признаке, поэтому вес жанра двойной — как у формы записи."""
    on_topic = scored("https://legalbet.ru/shkola-bettinga/stavki-na-futbol")[0]
    off_topic = scored("https://www.championat.com/guide/lifestyle")[0]
    assert on_topic > off_topic
    # Жанр без темы даёт мало, но не ноль: хаб может называться `/school` без слов задачи.
    assert scored("https://x.test/school/x")[0] > scored("https://x.test/section/x")[0]


def test_learning_genre_only_while_hunting_an_article():
    """У контактной задачи жанр ни при чём — иначе он начнёт двигать очередь там, где
    ищут телефон."""
    assert "learn" not in scored("https://x.test/wiki/page", intent="contact")[1]


def test_promo_pages_are_penalized_but_not_when_the_task_asks_for_them():
    """На корне `legalbet.ru` девять из top-10 были бонусные промо («розыгрыш 200000 рублей
    фрибетами за ставки на теннис»): у них есть и тема, и форма записи, и длинный заголовок,
    поэтому они обходили обучающий раздел.

    Штраф обязан выключаться, когда промо и есть запрос: «найди бонусы букмекеров» —
    законный сценарий, и ломать его нельзя.
    """
    promo = "https://legalbet.ru/bonus/liga-stavok-rozigrish-200000-rublej-fribetami"
    assert "promo" in scored(promo, "Бонус Лиги Ставок: розыгрыш фрибетов за ставки")[1]

    for_bonus_task = score_link(
        {"href": promo, "text": "Бонус Лиги Ставок: розыгрыш фрибетов"},
        intent="content_search",
        task="Найди бонусы букмекеров и сравни, где фрибет выгоднее",
        hints=HINTS,
        on_homepage=True,
    )[1]
    assert "promo" not in for_bonus_task


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
