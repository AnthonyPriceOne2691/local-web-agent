"""Чужая аналитика не загружается (doc 03 § Трекеры, doc 26 § T-3a-1).

Два повода, оба из живого прогона: приватность (обход отмечался в чужой аналитике от
имени этой машины) и скорость (зависший трекер держал DOMContentLoaded 30 s и стоил
2 сайтов из 3). Блокировка **хостовая**: по типу ресурса нельзя — на SPA без своих
скриптов страницы нет вовсе.
"""

from __future__ import annotations

from app.browser.trackers import TrackerBlocklist
from app.config import Settings
from tests.conftest import REPO_ROOT

REAL = TrackerBlocklist.load(Settings(data_dir=REPO_ROOT / "data").data_dir)


def test_list_loads_from_data_not_code():
    assert REAL.size > 10, "словарь живёт в data/, не в коде (DRY, doc 18)"


def test_blocks_the_two_hosts_that_broke_the_live_run():
    assert REAL.blocks("https://static.cloudflareinsights.com/beacon.min.js/v4513226") is True
    assert REAL.blocks("https://cloud.umami.is/script.js") is True


def test_blocks_subdomains_of_listed_host():
    assert REAL.blocks("https://cloud.umami.is/x.js") is True
    assert TrackerBlocklist(["umami.is"]).blocks("https://a.b.umami.is/x.js") is True


def test_does_not_block_lookalike_host():
    """Граница домена проверяется точкой, а не подстрокой."""
    assert TrackerBlocklist(["google-analytics.com"]).blocks("https://notgoogle-analytics.com/x") is False


def test_content_requests_pass():
    assert REAL.blocks("https://simonwillison.net/2026/03/01/post") is False
    assert REAL.blocks("https://cdn.jsdelivr.net/npm/vue/dist/vue.js") is False, (
        "CDN своих скриптов не трогаем — иначе SPA перестанут рендериться"
    )


def test_path_scoped_entry_blocks_only_that_path():
    blocklist = TrackerBlocklist(["facebook.com/tr"])
    assert blocklist.blocks("https://facebook.com/tr?id=1") is True
    assert blocklist.blocks("https://facebook.com/some/page") is False


def test_site_under_crawl_is_never_blocked_by_its_own_entry():
    """Предохранитель: `plausible.io` может быть целью исследования, а не трекером."""
    blocklist = TrackerBlocklist(["plausible.io"])
    assert blocklist.blocks("https://plausible.io/docs", page_host="plausible.io") is False
    assert blocklist.blocks("https://plausible.io/js/script.js", page_host="othersite.com") is True


def test_empty_list_blocks_nothing():
    assert TrackerBlocklist([]).size == 0
    assert TrackerBlocklist([]).blocks("https://google-analytics.com/collect") is False


def test_setting_is_on_by_default():
    assert Settings().block_trackers is True
