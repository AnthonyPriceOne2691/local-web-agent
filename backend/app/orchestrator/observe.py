"""NAVIGATE + OBSERVE: переход, guard-проверки и снятие снапшота.

Вынесено из `loop.py` (≤500 LOC, doc 18) — шестой вынос после attended /
interaction / capture / discovery / decide / finalize. Тема модуля: **как из URL
получается снапшот** — robots, retry, off-domain redirect, SPA-fallback, скриншот.
Сама машина состояний осталась в loop.py.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from app.browser.base import BrowserSession
from app.contracts import guards
from app.contracts.enforcer import ContractEnforcer
from app.observer.blockers import looks_like_challenge
from app.observer.snapshot import build_snapshot
from app.orchestrator.capture import SPA_TEXT_THRESHOLD, maybe_screenshot
from app.orchestrator.robots import RobotsPolicy
from app.orchestrator.run_state import RunState, StepOutcome
from app.orchestrator.states import State
from app.schemas.run import CrawlStep, RunRecord
from app.schemas.snapshot import PageSnapshot
from app.storage.run_store import RunStore

logger = logging.getLogger(__name__)

ConsentDismisser = Callable[[RunRecord, str], Awaitable[None]]


async def navigate_and_observe(
    browser: BrowserSession,
    record: RunRecord,
    url: str,
    origin: str,
    robots: RobotsPolicy,
    *,
    first: bool,
    step_index: int,
    store: RunStore,
    enforcer: ContractEnforcer,
    page_timeout_ms: int,
    dismiss_consent: ConsentDismisser,
) -> tuple[PageSnapshot, str] | None:
    """Снапшот и (возможно новый) origin, либо None — шаг пропущен.

    Пропуск не ошибка: robots запретил, переход не удался дважды, редирект увёл с
    домена. Во всех случаях причина остаётся шагом в записи прогона — иначе
    пропуск неотличим от «страницы не было».
    """
    if not robots.allowed(url):  # G-H5
        record.steps.append(
            CrawlStep(index=step_index, state=State.OBSERVE, url=url, note="robots_disallow — skipped")
        )
        return None

    t_nav = time.perf_counter()
    final_url = await _goto_with_retry(browser, record, url, step_index, enforcer, page_timeout_ms)
    if final_url is None:
        return None

    ok, new_origin = guards.check_redirect(final_url, origin, first_navigation=first)  # I-H9
    if not ok:
        record.steps.append(
            CrawlStep(index=step_index, state=State.OBSERVE, url=url, note="redirect_offsite — discarded")
        )
        return None
    if new_origin != origin:
        record.metadata["landing_domain_adopted"] = new_origin

    raw = await _raw_with_spa_fallback(browser, final_url)
    snapshot = build_snapshot(raw, page_url=final_url, origin=new_origin)
    await maybe_screenshot(browser, store, dismiss_consent, record, snapshot, step_index)
    record.steps.append(
        CrawlStep(
            index=step_index,
            state=State.OBSERVE,
            url=snapshot.url,
            duration_ms=int((time.perf_counter() - t_nav) * 1000),
            screenshot_paths={s.profile: s.relative_path for s in snapshot.screenshots},
        )
    )
    return snapshot, new_origin


async def _goto_with_retry(
    browser: BrowserSession,
    record: RunRecord,
    url: str,
    step_index: int,
    enforcer: ContractEnforcer,
    page_timeout_ms: int,
) -> str | None:
    """Переход с одним ретраем (doc 03). None = не дошли, причина записана шагом."""
    timeout_ms = enforcer.effective_timeout_ms(page_timeout_ms)  # G-H6
    for attempt in (1, 2):
        try:
            return await browser.goto(url, timeout_ms=timeout_ms)
        except Exception as exc:
            if attempt == 2:
                logger.warning("goto %s failed twice (%s: %s)", url, type(exc).__name__, str(exc)[:150])
                record.steps.append(
                    CrawlStep(
                        index=step_index,
                        state=State.OBSERVE,
                        url=url,
                        note=f"nav_error: {str(exc)[:150]}",
                    )
                )
                return None
            logger.debug("goto %s failed, retrying (%s)", url, type(exc).__name__)
            await browser.wait(2000)
    return None  # недостижимо: обе ветки цикла возвращают значение


async def _raw_with_spa_fallback(browser: BrowserSession, final_url: str) -> dict[str, object]:
    """Пустой DOM у SPA — ждём networkidle и снимаем снова.

    На challenge-странице fallback пропускается: его ожидание даёт anti-bot
    проверке пройти и проскочить attended-паузу (doc 24).
    """
    raw = await browser.raw_snapshot()
    if len(raw.get("main_text") or "") >= SPA_TEXT_THRESHOLD or looks_like_challenge(raw):
        return raw
    try:
        await browser.wait_networkidle(10000)
    except Exception as exc:
        # Штатный best-effort: у SPA networkidle может не наступить вовсе,
        # снапшот всё равно снимаем. Уровень debug, а не warning.
        logger.debug("networkidle wait skipped for %s (%s)", final_url, type(exc).__name__)
    return await browser.raw_snapshot()


def drop_dead_page(record: RunRecord, st: RunState, store: RunStore) -> StepOutcome:
    """404 не идёт ни в синтез, ни в PLAN: её ссылки — шаблон сайта, а не содержание.

    Найдено проверкой эталонов руками (doc 26 § Проверка эталона): по записанному в журнале
    URL статьи лежала 404-страница с меню и футером, и агент читал её как содержание сайта.
    Ход тот же, что при неудачной навигации: страница остаётся посещённой (второй раз туда
    не пойдём и бюджет она потратила честно), а PLAN продолжается с прежней страницы.
    """
    dead = st.snapshots.pop()  # remember() добавил её строкой выше
    record.steps.append(
        CrawlStep(
            index=st.step_index,
            state=State.OBSERVE,
            url=dead.url,
            note="not_found: страница не найдена, в содержание не берём",
        )
    )
    st.current = st.snapshots[-1] if st.snapshots else None
    record.pages_visited = len(st.visited)
    store.save(record)
    return StepOutcome.CONTINUE if st.current is not None else StepOutcome.STOP
