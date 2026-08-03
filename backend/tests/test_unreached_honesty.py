"""Исчерпание бюджета ≠ отсутствие содержания (doc 26 § T-3a-2).

Находка живого прогона T-3a: на всех трёх реальных сайтах агент выбирал страницу глубже
`max_depth: 2`, получал hard-reject G-H2 (три раза, `recovered: false`), останавливался — и
синтез заявлял с `confidence: high`, что «на сайте нет подробного разбора темы». Для блога
Rust, где анонсы релизов — основной жанр, это просто неверно: статья лежала на третьем
хопе. Ошибка опасна именно уверенностью: пользователь не может отличить «нет» от «не дошёл».
"""

from __future__ import annotations

from app.orchestrator.synthesize import unreached_urls
from app.schemas.run import CrawlStep, RunRecord, Violation
from tests.test_orchestrator import record_for


def _record(*steps: CrawlStep) -> RunRecord:
    record = record_for("https://blog.rust-lang.org/", task="releases", allow_private=True)
    record.steps.extend(steps)
    return record


def _step(*violations: Violation) -> CrawlStep:
    return CrawlStep(index=1, state="ACT", violations=list(violations))


def _depth_reject(url: str, *, recovered: bool = False) -> Violation:
    return Violation(
        constraint_id="G-H2",
        message="hop depth exceeded",
        proposed_url=url,
        recovered=recovered,
        severity="hard",
    )


def test_blocked_page_is_reported_as_unreached():
    record = _record(_step(_depth_reject("https://blog.rust-lang.org/releases/latest")))
    assert unreached_urls(record) == ["https://blog.rust-lang.org/releases/latest"]


def test_same_url_rejected_repeatedly_is_listed_once():
    """Живой прогон предлагал один URL трижды — в промпт он должен попасть один раз."""
    url = "https://martinfowler.com/microservices"
    record = _record(_step(_depth_reject(url)), _step(_depth_reject(url)), _step(_depth_reject(url)))
    assert unreached_urls(record) == [url]


def test_recovered_rejection_is_not_unreached():
    """Обошли и всё-таки прочитали — жаловаться не на что."""
    record = _record(_step(_depth_reject("https://x.test/deep", recovered=True)))
    assert unreached_urls(record) == []


def test_soft_violation_is_not_unreached():
    record = _record(
        _step(
            Violation(
                constraint_id="I-H6",
                message="too many candidates",
                proposed_url="https://x.test/soft",
                recovered=False,
                severity="soft",
            )
        )
    )
    assert unreached_urls(record) == []


def test_clean_run_has_nothing_unreached():
    assert unreached_urls(_record(_step())) == []


def test_prompt_forbids_claiming_absence_when_pages_were_missed():
    """Слова в промпте — часть поведения: без запрета модель заявляла отсутствие."""
    from pathlib import Path

    from jinja2 import Template

    tpl_path = Path(__file__).resolve().parents[2] / "data" / "prompts" / "synthesizer_user.j2"
    rendered = Template(tpl_path.read_text(encoding="utf-8")).render(
        task="releases",
        intent="content_search",
        pages_count=1,
        pages_block="PAGE 1",
        summary_cap=0,
        unreached=["https://blog.rust-lang.org/releases/latest"],
    )
    assert "NOT REACHED" in rendered
    assert "https://blog.rust-lang.org/releases/latest" in rendered
    assert "not evidence of absence" in rendered

    without = Template(tpl_path.read_text(encoding="utf-8")).render(
        task="releases",
        intent="content_search",
        pages_count=1,
        pages_block="PAGE 1",
        summary_cap=0,
        unreached=[],
    )
    assert "NOT REACHED" not in without, "чистый прогон не должен получать лишний блок"


# --- гарантия кодом: промпт слушается через раз, приписка не зависит от модели ---


def test_summary_always_says_what_was_not_reached():
    """Живой замер: запрет в промпте сработал на 1 сайте из 2 — поэтому приписка кодом."""
    from app.orchestrator.synthesize import note_unreached
    from app.schemas.extraction import ExtractionResult

    result = ExtractionResult(
        status="completed",
        summary="The site does not explain how releases are handled.",
    )
    noted = note_unreached(result, ["https://blog.rust-lang.org/releases/latest"])

    assert "Not reached" in noted.summary
    assert "https://blog.rust-lang.org/releases/latest" in noted.summary
    assert "not absent from the site" in noted.summary
    assert result.summary in noted.summary, "ответ модели сохраняется, приписка добавляется"


def test_clean_result_is_untouched():
    from app.orchestrator.synthesize import note_unreached
    from app.schemas.extraction import ExtractionResult

    result = ExtractionResult(status="completed", summary="All good.")
    assert note_unreached(result, []) is result


def test_long_unreached_list_is_capped_in_the_note():
    from app.orchestrator.synthesize import note_unreached
    from app.schemas.extraction import ExtractionResult

    urls = [f"https://x.test/{i}" for i in range(8)]
    noted = note_unreached(ExtractionResult(status="completed", summary="s"), urls)

    assert "https://x.test/4" in noted.summary
    assert "https://x.test/5" not in noted.summary, "длинный список режется"
    assert "(+3)" in noted.summary, "но количество отброшенных названо"
