"""Страница «не найдено» — не содержимое (doc 03 § Blockers, doc 26 § Проверка эталона).

Проверка эталонов руками 06.08: записанный в журнале URL статьи на `championat.com` отдаёт
**404-страницу сайта** — с полным меню, футером и 543 символами текста «Запрашиваемая
страница не найдена». Человек это видит мгновенно, агент — нет: для него это обычная
страница, которая идёт в синтез как «содержание сайта» и тратит бюджет.

Тот же симптом был записан ещё в T-3d («хоп в 404-дубль»), но чинился только счётом ссылок.

Признак структурный: **мало текста + маркер «не найдено» в заголовке или тексте**. Толстая
страница с фразой «404» внутри статьи (например, разбор ошибок HTTP) блокером не считается —
тот же thin-guard, что у captcha и login_wall.
"""

from __future__ import annotations

from app.observer.blockers import detect_status

CHAMPIONAT_404 = (
    "ФУТБОЛ ХОККЕЙ ТЕННИС БОКС/ММА БАСКЕТБОЛ АВТО БИАТЛОН ЛЫЖИ ФИГУРНОЕ КАТАНИЕ ВОЛЕЙБОЛ "
    "LIFESTYLE ЕЩЁ Эфир Матч-центр Новости Топ-матчи Видео Рейтинг букмекеров Теперь вы знаете "
    "Запрашиваемая страница не найдена Произошла ошибка. Чтобы найти нужную информацию, "
    "рекомендуем перейти на главную страницу 18+ Правовая информация Контакты Реклама"
)


def test_real_404_page_is_not_content():
    """Настоящая запись живого прогона: заголовок «404 - Чемпионат.com», 543 символа."""
    assert (
        detect_status(
            url="https://www.championat.com/bets/article-3964176-kak-stavit-stavki-na-futbol.html",
            main_text=CHAMPIONAT_404,
            title="404 - Чемпионат.com",
            has_password_field=False,
        )
        == "error"
    )


def test_not_found_wording_without_the_number():
    for title, text in (
        ("Страница не найдена", "К сожалению, такой страницы нет. Вернитесь на главную."),
        ("Page not found", "The page you requested could not be found."),
        ("Ошибка 404", "Нет такой страницы"),
    ):
        assert detect_status(
            url="https://x.test/gone", main_text=text, title=title, has_password_field=False
        ) == ("error"), title


def test_article_about_404_errors_is_still_content():
    """Обратная сторона: толстая статья, где «404» — тема, а не статус страницы."""
    article = "Что означает ошибка 404 и как её чинить. " * 60  # ~2.4 k символов
    assert (
        detect_status(
            url="https://x.test/blog/chto-takoe-404",
            main_text=article,
            title="Что такое ошибка 404: причины и решения",
            has_password_field=False,
        )
        == "ok"
    )


def test_antibot_wording_with_an_article_is_still_a_challenge():
    """Живая страница `thekitchn.com` (снята браузером 07.08): «Please verify you are **a**
    human», 507 символов.

    В словаре сигналов стояло «verify you are human» — без артикля, поэтому подстрока не
    совпадала и заглушка уходила в синтез как содержание сайта. Формулировка не про
    конкретный сайт: так пишут и Cloudflare, и HUMAN/PerimeterX.
    """
    assert (
        detect_status(
            url="https://www.thekitchn.com/",
            main_text=(
                "Please verify you are a human\n\nAccess to this page has been denied because "
                "we believe you are using automation tools to browse the website."
            ),
            title="",
            has_password_field=False,
        )
        == "captcha"
    )


def test_access_denied_page_is_not_content():
    """Отказ в доступе — не содержание, ровно как 404.

    Две живые страницы, снятые браузером 07.08: `seriouseats.com` отдал 316 символов
    «If you are a reader experiencing an access issue…», `povarenok.ru` — заголовок
    «403 Forbidden» и 19 символов текста. Обе шли в синтез со статусом `ok`, то есть
    агент считал их содержанием сайта и тратил на них бюджет.
    """
    for url, text, title in (
        (
            "https://www.seriouseats.com/",
            "If you are a reader experiencing an access issue, please contact support@people.inc.",
            "",
        ),
        ("https://www.povarenok.ru/", "403 Forbidden nginx", "403 Forbidden"),
    ):
        assert detect_status(url=url, main_text=text, title=title, has_password_field=False) == ("error"), url


def test_article_about_403_errors_is_still_content():
    """Обратная сторона того же правила: разбор кодов ответа — это содержание."""
    article = "Ошибка 403 Forbidden означает, что доступ запрещён сервером. Разбираем причины. " * 40
    assert (
        detect_status(
            url="https://x.test/blog/403-forbidden",
            main_text=article,
            title="Что такое 403 Forbidden и как это чинить",
            has_password_field=False,
        )
        == "ok"
    )


def test_page_without_text_and_links_is_not_content():
    """Пустая страница — не содержание (doc 03 § Blockers, doc 26 § T-3p).

    `chefkoch.de` отдаёт ноль текста и ноль ссылок даже после `networkidle`, а скриншот
    **полностью белый** — значит и vision там смотреть нечего. При статусе `ok` такая
    страница шла в синтез как содержание сайта и тратила бюджет.

    Различающий признак дал замер, а не догадка: у живого SPA ссылки есть всегда, пустым
    бывает только текст — `vercel.com` 111 слов при 164 ссылках, `heise.de` 12 слов при 392.
    Поэтому режем по паре «нет текста И нет ссылок», а не по одному тексту: иначе выпал бы
    весь SPA-сценарий, ради которого и делается скриншот под vision.
    """
    from app.observer.snapshot import build_snapshot
    from tests.conftest import page_raw

    dead = build_snapshot(
        page_raw(title="", text="", links=[]), page_url="https://x.test/", origin="https://x.test"
    )
    assert dead.status == "error"

    spa = build_snapshot(
        page_raw(title="Vercel", text="", links=[(f"https://x.test/p{i}", "") for i in range(40)]),
        page_url="https://x.test/spa",
        origin="https://x.test",
    )
    assert spa.status == "ok", "у живого SPA пустой только текст — такую страницу не трогаем"


def test_blockers_take_priority_over_not_found():
    """Порядок признаков: anti-bot заглушка тоже «тонкая», но её проходит человек —
    спутать их значило бы потерять attended-паузу."""
    assert (
        detect_status(
            url="https://x.test/",
            main_text="Checking your browser before accessing the site. Страница не найдена?",
            title="Just a moment...",
            has_password_field=False,
        )
        == "captcha"
    )
