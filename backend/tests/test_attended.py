"""Attended-режим (Phase 5, doc 24): пауза на anti-bot challenge → человек проходит →
повторный OBSERVE. Реального браузера нет — FakeBrowser отдаёт captcha, затем контент."""

from __future__ import annotations

import asyncio

from app.observer.blockers import detect_status
from app.orchestrator.attended import EventAttendedGate
from app.schemas.research import SessionRecord
from app.schemas.run import RunConfig, RunRecord
from tests.conftest import FakeBrowserSession, page_raw
from tests.test_api_and_store import api_client  # noqa: F401 — fixture reuse
from tests.test_orchestrator import make_orchestrator, record_for
from tests.test_sse_and_ui_endpoints import _collect_events, _fast_sse

CHALLENGE = page_raw(title="Just a moment", text="Checking your browser cloudflare " * 5)


class ChallengeBrowser(FakeBrowserSession):
    """Первый OBSERVE challenge_url → captcha-заглушка; после resume re-observe
    (без нового goto) → реальный контент. Challenge держится до прохождения."""

    def __init__(self, pages: dict, *, challenge_url: str):
        super().__init__(pages)
        self._challenge_url = challenge_url
        self._served_challenge = False

    async def raw_snapshot(self) -> dict:
        if self.current_url == self._challenge_url and not self._served_challenge:
            self._served_challenge = True
            return CHALLENGE
        return self.pages[self.current_url]


LOGIN_PAGE = page_raw(title="Sign in", text="Please log in to continue", password=True)


class LoginBrowser(FakeBrowserSession):
    """login_url → login_wall-заглушка (password-поле, тонкая); после resume
    re-observe → контент под логином. Tier 2 (doc 25): человек логинится сам."""

    def __init__(self, pages: dict, *, login_url: str):
        super().__init__(pages)
        self._login_url = login_url
        self._served_login = False

    async def raw_snapshot(self) -> dict:
        if self.current_url == self._login_url and not self._served_login:
            self._served_login = True
            return LOGIN_PAGE
        return self.pages[self.current_url]


async def _wait_status(record: RunRecord, status: str, *, tries: int = 300) -> bool:
    for _ in range(tries):
        if record.status == status:
            return True
        await asyncio.sleep(0.01)
    return False


# ------------------------------------------------------- captcha detect
def test_detect_status_recognizes_modern_cloudflare():
    """Актуальные формулировки CF managed challenge (2026) → captcha (не 'ok')."""
    for title, text in [
        ("Just a moment...", "Enable JavaScript and cookies to continue"),
        ("", "Verifying you are human. This may take a few seconds."),
        ("Attention Required! | Cloudflare", "needs to review the security of your connection"),
    ]:
        assert detect_status(url="https://x.test/", main_text=text, title=title,
                             has_password_field=False) == "captcha", title
    # обычная страница не ловится как captcha
    assert detect_status(url="https://x.test/", main_text="Наша команда и контакты",
                         title="О компании", has_password_field=False) == "ok"


def test_detect_status_ignores_embedded_widget_on_real_page():
    """Толстая контентная страница со встроенным Turnstile-текстом → ok, не captcha.

    Регрессия: расширенные сигналы ложно ловили виджет 'verifying you are human'
    на реальной странице (форма регистрации) → бесконечная attended-пауза."""
    real = "Melhores casas de apostas online no Brasil em 2026. " * 40  # >800 симв
    real += " Registre-se: verifying you are human."  # встроенный Turnstile-виджет
    assert detect_status(url="https://bet.test/apostas", main_text=real,
                         title="Casas de Apostas 2026", has_password_field=False) == "ok"


def test_login_wall_thin_guard_ignores_widget_on_fat_page():
    """password-поле на толстой контентной странице (login-виджет) → ok, не login_wall."""
    fat = "Real article content here. " * 60  # >800 симв
    assert detect_status(url="https://x.test/article", main_text=fat, title="Article",
                         has_password_field=True) == "ok"
    # тонкая страница с password → login_wall; login-URL → login_wall независимо от текста
    assert detect_status(url="https://x.test/acct", main_text="Sign in", title="Login",
                         has_password_field=True) == "login_wall"
    assert detect_status(url="https://x.test/login", main_text="x" * 2000, title="",
                         has_password_field=False) == "login_wall"


# ---------------------------------------------------------- orchestrator
async def test_attended_pause_resume_then_observe(tmp_path):
    origin = "http://127.0.0.1:8911"
    browser = ChallengeBrowser(
        {f"{origin}/": page_raw(title="Home", text="Real page content here " * 40)},
        challenge_url=f"{origin}/")
    orch, store, _llm = make_orchestrator(tmp_path, browser, [
        {"action": "stop", "reasoning": "content is here"},
        {"summary": "Home read after challenge", "facts": [], "not_found": []},
    ])
    resume = asyncio.Event()
    gate = EventAttendedGate(resume, store, timeout_s=5.0)
    record = record_for(f"{origin}/", task="read page", attended=True,
                        respect_robots=False, vision_enabled="never",
                        capture_screenshots="never")

    task = asyncio.create_task(orch.run(record, attended_gate=gate))
    assert await _wait_status(record, "waiting_user"), "run не встал на паузу"
    assert record.metadata["challenge"]["kind"] == "captcha"
    assert record.metadata["challenge"]["url"] == f"{origin}/"
    resume.set()  # человек прошёл проверку
    result = await task

    assert result.metadata.get("blocked_by") is None       # не заблокирован
    assert result.metadata.get("challenge_cleared") == 1
    assert result.metadata.get("challenge") is None         # снят
    # goto был ОДИН раз (challenge); после resume — re-observe без нового goto,
    # иначе CF показал бы проверку повторно (баг двух галочек)
    assert browser.visited_log.count(f"{origin}/") == 1
    assert result.status in ("completed", "partial", "not_found")


async def test_attended_login_wall_pause_resume(tmp_path):
    """Tier 2 (doc 25): login_wall + attended → пауза (человек логинится сам) →
    resume → re-observe контента под логином. Паролей агент не хранит и не видит."""
    origin = "http://127.0.0.1:8914"
    browser = LoginBrowser(
        {f"{origin}/": page_raw(title="Dashboard", text="Logged-in content here " * 40)},
        login_url=f"{origin}/")
    orch, store, _llm = make_orchestrator(tmp_path, browser, [
        {"action": "stop", "reasoning": "content visible"},
        {"summary": "read after login", "facts": [], "not_found": []},
    ])
    resume = asyncio.Event()
    gate = EventAttendedGate(resume, store, timeout_s=5.0)
    record = record_for(f"{origin}/", task="read dashboard", attended=True,
                        respect_robots=False, vision_enabled="never",
                        capture_screenshots="never")

    task = asyncio.create_task(orch.run(record, attended_gate=gate))
    assert await _wait_status(record, "waiting_user"), "login не встал на паузу"
    assert record.metadata["challenge"]["kind"] == "login_wall"
    resume.set()  # человек залогинился в видимом браузере
    result = await task

    assert result.metadata.get("blocked_by") is None
    assert result.metadata.get("challenge_cleared") == 1
    assert result.status in ("completed", "partial", "not_found")


async def test_attended_timeout_blocks(tmp_path):
    origin = "http://127.0.0.1:8912"
    browser = ChallengeBrowser(
        {f"{origin}/": page_raw(title="Home", text="content " * 40)},
        challenge_url=f"{origin}/")
    orch, _store2, _llm = make_orchestrator(tmp_path, browser, [
        {"summary": "unused", "facts": [], "not_found": []},
    ])
    resume = asyncio.Event()  # никто не пройдёт проверку
    gate = EventAttendedGate(resume, _store2, timeout_s=0.05)
    record = record_for(f"{origin}/", task="read", attended=True,
                        respect_robots=False, vision_enabled="never",
                        capture_screenshots="never")

    result = await orch.run(record, attended_gate=gate)
    assert result.status == "blocked"
    assert result.metadata["blocked_by"] == "captcha"
    assert result.metadata.get("challenge_timeout") is True


async def test_captcha_without_attended_still_blocks(tmp_path):
    """Без attended-gate поведение прежнее: captcha → blocked сразу (регрессия Phase 2)."""
    origin = "http://127.0.0.1:8913"
    browser = ChallengeBrowser(
        {f"{origin}/": page_raw(title="Home", text="content " * 40)},
        challenge_url=f"{origin}/")
    orch, _store3, _llm = make_orchestrator(tmp_path, browser, [
        {"summary": "x", "facts": [], "not_found": []}])
    record = record_for(f"{origin}/", task="read", respect_robots=False,
                        vision_enabled="never", capture_screenshots="never")

    result = await orch.run(record)  # attended_gate=None
    assert result.status == "blocked"
    assert result.metadata["blocked_by"] == "captcha"
    assert browser.visited_log.count(f"{origin}/") == 1  # без повторного захода


# ------------------------------------------------------------- SSE + API
async def test_sse_emits_challenge_wait(api_client):  # noqa: F811
    client, app = api_client
    _fast_sse(app)
    sessions, runs = app.state.session_store, app.state.run_store
    sessions.save(SessionRecord(id="chsse", status="running_tools", created_at="t"))
    run = RunRecord(id="runwait", status="waiting_user", session_id="chsse", started_at="t",
                    config=RunConfig(start_url="http://site.test/x", task="t", attended=True),
                    metadata={"challenge": {"url": "http://site.test/x", "kind": "captcha",
                                            "action": "оплата заказа"}})
    runs.save(run)

    async def _advance() -> None:
        await asyncio.sleep(0.05)
        run.status = "completed"
        runs.save(run)
        sessions.save(SessionRecord(id="chsse", status="completed", created_at="t"))

    task = asyncio.create_task(_advance())
    events = await _collect_events(client, "/sessions/chsse/events")
    await task

    challenge = [d for n, d in events if n == "challenge_wait"]
    assert challenge, "нет события challenge_wait"
    assert challenge[0]["kind"] == "captcha"
    assert challenge[0]["url"] == "http://site.test/x"
    assert challenge[0]["run_id"] == "runwait"
    assert challenge[0]["action"] == "оплата заказа"  # Tier 2/3: что подготовлено (doc 15 v0.8)


async def test_resume_run_endpoint_guards(api_client):  # noqa: F811
    client, app = api_client
    runs = app.state.run_store
    assert (await client.post("/runs/nope/resume")).status_code == 404
    runs.save(RunRecord(id="rdone", status="completed", started_at="t",
                        config=RunConfig(start_url="http://a", task="t")))
    r = await client.post("/runs/rdone/resume")  # не в waiting_user
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "not_waiting"


async def test_resume_session_endpoint_sets_event(api_client):  # noqa: F811
    client, app = api_client
    sessions, runs = app.state.session_store, app.state.run_store
    sessions.save(SessionRecord(id="srez", status="running_tools", created_at="t"))
    runs.save(RunRecord(id="ractive", status="waiting_user", session_id="srez", started_at="t",
                        config=RunConfig(start_url="http://a", task="t", attended=True)))
    event = asyncio.Event()
    app.state.session_resume_events["srez"] = event

    r = await client.post("/sessions/srez/resume")
    assert r.status_code == 202
    assert event.is_set()  # resume проброшен в активный crawl

    # active_run_id считает waiting_user занятым → D-12 lock держится
    assert app.state.run_store.active_run_id() == "ractive"
