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
