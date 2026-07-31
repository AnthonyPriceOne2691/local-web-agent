"""Режим синтеза по интенту: канон на длинных ответах, быстрый путь на извлечении.

Замер 2026-07-31 (doc 16 § Быстрый синтез): на `contact` быстрый путь дал −68 %
выходных токенов при идентичном факте и значении (4 прогона из 4 совпали до
токена), а на `content_search` тот же режим оказался бимодальным — 350 против
1265 токенов при одной конфигурации. Поэтому правило зависит от интента, и тесты
держат именно эту границу.
"""

from __future__ import annotations

from app.config import Settings
from app.llm.synthesizer import Synthesizer
from tests.conftest import REPO_ROOT


def _synth(**kw: object) -> Synthesizer:
    settings = Settings(data_dir=REPO_ROOT / "data", **kw)  # type: ignore[arg-type]
    return Synthesizer(object(), settings)  # type: ignore[arg-type]  # клиент не нужен: проверяем выбор режима


def test_content_search_keeps_canon_reasoning():
    think, schema, cap = _synth()._mode("content_search")
    assert think is True and schema is None and cap == 0


def test_design_audit_keeps_canon_reasoning():
    think, schema, _ = _synth()._mode("design_audit")
    assert think is True and schema is None


def test_extraction_intent_uses_fast_path():
    think, schema, cap = _synth()._mode("contact")
    assert think is False
    assert schema is not None and cap == 500


def test_fast_path_schema_has_only_model_authored_fields():
    _, schema, _ = _synth()._mode("contact")
    assert schema is not None
    props = set(schema["properties"])
    assert {"summary", "facts", "not_found"} <= props
    # Поля, которые заполняет код: отдать их схеме = попросить модель их выдумать.
    assert not props & {"run_id", "task", "start_url", "duration_seconds", "generated_at"}


def test_star_disables_fast_path_everywhere():
    think, schema, cap = _synth(synth_reasoning_intents="*")._mode("contact")
    assert think is True and schema is None and cap == 0


def test_custom_intent_list_is_respected():
    synth = _synth(synth_reasoning_intents="pricing")
    assert synth._mode("pricing")[0] is True
    assert synth._mode("content_search")[0] is False  # список задан явно — канона тут больше нет


def test_zero_cap_renders_no_budget_block():
    """Бюджет 0 = блока OUTPUT BUDGET в промпте нет (канонный путь не меняется)."""
    synth = _synth(synth_summary_cap=0)
    user = synth._user_tpl.render(
        task="T", intent="contact", pages_count=1, pages_block="P", summary_cap=synth._mode("contact")[2]
    )
    assert "OUTPUT BUDGET" not in user


def test_cap_renders_budget_and_named_values_rule():
    synth = _synth()
    user = synth._user_tpl.render(
        task="T", intent="contact", pages_count=1, pages_block="P", summary_cap=synth._mode("contact")[2]
    )
    assert "OUTPUT BUDGET" in user and "EXTRACT NAMED VALUES" in user
