"""Скрытое модальное окно логина — не login_wall (doc 03 § Blockers, doc 26 § T-2b-1).

Находка живого прогона T-2b на `demoblaze.com`: страница полностью публичная, но помечена
`blocked_by: login_wall`, прогон встал на первой странице, и ответ заявил «цены не
указаны» — хотя каталог с ценами приходит JS'ом.

Одна причина, три симптома: признак «есть поле пароля» собирался **без проверки
видимости**, а у SPA сырой текст короткий (673 символа < порога «тонкой» страницы). Пара
«password + тонкая» дала login_wall; login_wall по устройству **отключает SPA-fallback**
(иначе блокер проскочит attended-паузу), поэтому каталог не отрендерился вовсе.

Скрытое модальное окно логина есть почти на каждом магазине — то есть дефект бил бы по
всему типу «магазин», а не по одному сайту.
"""

from __future__ import annotations

from app.observer.blockers import detect_status, looks_like_challenge
from app.observer.snapshot import OBSERVE_JS

SPA_TEXT = "Home Phones Laptops Monitors Contact About us Cart Log in Sign up"  # ~65 симв.


def test_thin_spa_without_visible_password_is_ok():
    status = detect_status(
        url="https://www.demoblaze.com/",
        main_text=SPA_TEXT,
        title="STORE",
        has_password_field=False,  # модальное окно скрыто → поля не видно
    )
    assert status == "ok"


def test_spa_fallback_is_not_skipped_for_such_a_page():
    """Главный симптом: из-за ложного login_wall не срабатывал повторный снапшот."""
    raw = {"main_text": SPA_TEXT, "title": "STORE", "has_password_field": False}
    assert looks_like_challenge(raw) is False


def test_real_login_wall_still_detected():
    """Негативный контроль: видимое поле пароля на тонкой странице — по-прежнему блокер."""
    status = detect_status(
        url="https://example.com/account",
        main_text="Sign in to continue",
        title="Sign in",
        has_password_field=True,
    )
    assert status == "login_wall"


def test_login_url_still_detected_without_any_password_field():
    assert (
        detect_status(
            url="https://example.com/login", main_text="x" * 5000, title="Account", has_password_field=False
        )
        == "login_wall"
    )


def test_observe_js_requires_the_password_field_to_be_visible():
    assert "!!pick('input[type=password]')" not in OBSERVE_JS, (
        "сбор без проверки видимости вернулся — это и был ложный login_wall"
    )
    assert "input[type=password]" in OBSERVE_JS
    assert OBSERVE_JS.count("getBoundingClientRect") >= 2, (
        "видимость проверяется и у интерактивных элементов, и у поля пароля"
    )
