"""Агент помнит, КУДА ходил, а не только ГДЕ оказался (doc 04 § visited, doc 13 G-H3).

Найдено замером журнала прогонов: в четырёх прогонах агент навигировал на один и тот же
URL по два-три раза, и `contract_violations` при этом **пустые** — G-H3 «уже посещал» не
срабатывал вовсе.

Причина одна на все четыре случая — **редирект**. В `visited` попадает `snapshot.url`,
то есть URL, где агент ОКАЗАЛСЯ; запрошенный URL не попадает туда никогда. Пока сайт
редиректит A → B, ссылка A остаётся «непосещённой»: она проходит G-H3, снова уводит на B,
и цикл повторяется, пока не кончится бюджет шагов.

Записи живых прогонов, по которым написаны кейсы:

| Прогон | Запрошено | Куда увело | Повторов |
|---|---|---|---|
| `1d4e99b6f602` (sports.ru) | `…2648267-princzipy-otvetstvennoj-igry.html` | `…-igry-v-stavkax-na-sport.html` | 3 |
| `3a9ebf25e417` (lenta.ru) | `/archive` | `/2026/08/03` | 2 |

Цена на sports.ru: три шага из восьми ушли на одну и ту же страницу, до целевой статьи
агент не дошёл — при том, что она была в двух хопах.

Второй источник той же дыры — цель, до которой дойти НЕ удалось (`nav_error` после двух
попыток, offsite-редирект, robots): страницы нет, в `visited` не попадает ничего, и
кандидат остаётся в очереди как ни в чём не бывало.
"""

from __future__ import annotations

from app.schemas.run import RunConfig, RunRecord
from tests.conftest import FakeBrowserSession, page_raw
from tests.test_orchestrator import make_orchestrator

SITE = "https://portal.test"
WIKI = f"{SITE}/betting/wiki"
REQUESTED = f"{SITE}/betting/wiki/2648267-princzipy-otvetstvennoj-igry.html"
LANDED = f"{SITE}/betting/wiki/2648267-princzipy-otvetstvennoj-igry-v-stavkax-na-sport.html"

SYNTH = {"summary": "read", "facts": [], "not_found": []}


def _portal() -> FakeBrowserSession:
    """Портал, где ссылка на статью висит и на самой статье (сквозная перелинковка).

    Именно это делает цикл возможным: агент стоит на LANDED и видит в меню REQUESTED —
    для очереди кандидатов это законная непосещённая ссылка.
    """
    article_links = [(REQUESTED, "Принципы ответственной игры"), (f"{SITE}/betting/vidy", "Виды спорта")]
    return FakeBrowserSession(
        pages={
            WIKI: page_raw(title="Ставочная вики", text="Разделы вики " * 40, links=article_links),
            LANDED: page_raw(
                title="Принципы ответственной игры", text="Текст статьи " * 200, links=article_links
            ),
            f"{SITE}/betting/vidy": page_raw(title="Виды спорта", text="Футбол хоккей " * 60),
        },
        redirects={REQUESTED: LANDED},
    )


def _record(**cfg) -> RunRecord:
    return RunRecord(
        id="redirect-run",
        config=RunConfig(start_url=WIKI, task="Найди статью про ставки на футбол", **cfg),
    )


async def test_redirect_target_is_not_offered_twice(tmp_path):
    """Живой кейс sports.ru: модель дважды просит один URL, сайт дважды ведёт на ту же
    страницу. Второй запрос обязан упереться в G-H3, а страница — открыться один раз."""
    browser = _portal()
    orch, _, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "navigate", "url": REQUESTED, "reasoning": "статья про принципы"},
            {"action": "navigate", "url": REQUESTED, "reasoning": "туда же ещё раз"},
            {"action": "navigate", "url": REQUESTED, "reasoning": "и ещё раз"},
            {"action": "stop", "reasoning": "хватит"},
            SYNTH,
        ],
    )
    record = await orch.run(_record())

    assert browser.visited_log.count(LANDED) == 1, "страница прочитана повторно после редиректа"
    # Каким именно правилом отбит повтор — деталь: алиас уходит из очереди кандидатов, и
    # первым срабатывает I-H6 (приоритет 1) раньше G-H3 (5). Тест держит поведение, не код.
    refusals = [v for step in record.steps for v in step.violations if v.severity == "hard"]
    assert refusals, "повтор запрошенного URL должен ловиться контрактом, а не бюджетом шагов"
    assert all(v.proposed_url == REQUESTED for v in refusals)


async def test_alias_does_not_count_as_a_read_page(tmp_path):
    """Кейс lenta.ru (`/archive` → дата дня) и граница правки одновременно.

    Алиас нельзя просто досыпать в `visited`: на этом множестве считается бюджет страниц
    (G-H1, `ctx.pages_visited`), и каждый редирект молча съедал бы страницу из лимита.
    Агент прочитал две страницы — значит и в записи их две, сколько бы алиасов ни было.
    """
    archive, day = f"{SITE}/archive", f"{SITE}/2026/08/03"
    browser = FakeBrowserSession(
        pages={
            WIKI: page_raw(title="Вики", text="Разделы " * 40, links=[(archive, "Архив")]),
            day: page_raw(title="Архив за 3 августа", text="Заметки дня " * 80),
        },
        redirects={archive: day},
    )
    orch, _, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "navigate", "url": archive, "reasoning": "в архив"},
            {"action": "stop", "reasoning": "прочитал"},
            SYNTH,
        ],
    )
    record = await orch.run(_record())

    assert record.pages_visited == 2, "редирект-алиас не должен считаться прочитанной страницей"


async def test_unreachable_target_is_not_retried_forever(tmp_path):
    """Цель, до которой дойти не удалось, тоже запоминается: страницы нет, но ходить
    туда снова незачем. Иначе бюджет шагов сгорает на недостижимой ссылке."""
    dead = f"{SITE}/betting/dead"
    browser = FakeBrowserSession(
        pages={WIKI: page_raw(title="Вики", text="Разделы " * 40, links=[(dead, "Битая ссылка")])}
    )
    orch, _, _ = make_orchestrator(
        tmp_path,
        browser,
        [
            {"action": "navigate", "url": dead, "reasoning": "первая попытка"},
            {"action": "navigate", "url": dead, "reasoning": "вторая попытка"},  # → отказ, replan
            {"action": "stop", "reasoning": "идти больше некуда"},
            SYNTH,
        ],
    )
    record = await orch.run(_record())

    attempts = [s for s in record.steps if s.action == "navigate" and s.target_url == dead]
    assert len(attempts) == 1, "недостижимая цель предлагается повторно"
    assert record.status != "failed" and record.result is not None  # прогон дошёл до синтеза


def test_alias_is_not_reported_as_a_page_we_failed_to_open():
    """Граница знания не должна врать в свою пользу.

    Приписка «не удалось открыть X» (`note_limits`) строится по отклонённым URL. Алиас
    редиректа тоже отклоняется — но страница по нему прочитана, и назвать её недостижимой
    значило бы занизить собственный результат в ответе человеку.
    """
    from app.orchestrator.synthesize import unreached_urls
    from app.schemas.run import CrawlStep, Violation

    record = RunRecord(id="r", config=RunConfig(start_url=WIKI, task="t"))
    record.metadata["redirect_aliases"] = {REQUESTED: LANDED}
    record.steps.append(
        CrawlStep(
            index=1,
            state="ACT",
            violations=[
                Violation(constraint_id="G-H3", proposed_url=REQUESTED, recovered=False),
                Violation(constraint_id="G-H2", proposed_url=f"{SITE}/deep", recovered=False),
            ],
        )
    )
    assert unreached_urls(record) == [f"{SITE}/deep"]


def test_read_page_is_never_reported_as_unreached():
    """Живой прогон магазинов 07.08 (`sparkfun.com`, doc 26 § T-3o).

    Агент прочитал `/returns` вторым шагом, а дальше модель предложила её ещё **шесть раз**.
    Контракт каждый раз отбивал (I-H6: посещённое ушло из очереди кандидатов), но на
    последнем шаге отказы остались `recovered=False` — и страница попала в «не удалось
    открыть». Человеку это сообщается как граница знания: агент занижал собственный
    результат, называя недостижимой страницу, текст которой лежал в синтезе.

    Правило шире, чем прежнее исключение для алиасов: прочитано — значит не «не дошли»,
    независимо от того, почему URL позже отклонили.
    """
    from app.orchestrator.synthesize import unreached_urls
    from app.schemas.run import CrawlStep, Violation
    from app.schemas.snapshot import PageSnapshot

    returns, deep = f"{SITE}/returns", f"{SITE}/deep"
    record = RunRecord(id="r", config=RunConfig(start_url=SITE, task="shipping terms"))
    record.steps.append(
        CrawlStep(
            index=7,
            state="ACT",
            violations=[
                Violation(constraint_id="I-H6", proposed_url=returns, recovered=False),
                Violation(constraint_id="G-H2", proposed_url=deep, recovered=False),
            ],
        )
    )
    snapshots = [PageSnapshot(url=returns, title="Return Policy", main_text="Our return policy…")]

    assert unreached_urls(record, snapshots) == [deep]


def test_rule_sees_attempted_urls():
    """Юнит самого правила: алиас редиректа — это «уже были», а не «ещё не ходили».

    Оркестраторный тест выше проверяет исход, а не механику: там повтор отбивается
    раньше — очередью кандидатов. Правило должно держать свой конец само.
    """
    from app.contracts.context import ActionContext
    from app.contracts.rules.navigation import url_not_visited
    from app.schemas.snapshot import AgentAction

    ctx = ActionContext(origin=SITE, start_url=WIKI, current_url=LANDED, attempted={REQUESTED})
    action = AgentAction(action="navigate", url=REQUESTED, reasoning="ещё раз")

    violation = url_not_visited("G-H3", {}, action, ctx)
    assert violation is not None and violation.proposed_url == REQUESTED
    assert url_not_visited("G-H3", {}, AgentAction(action="navigate", url=WIKI), ctx) is None
