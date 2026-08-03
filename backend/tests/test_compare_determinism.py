"""Сравнение конкурентов обязано быть воспроизводимым на одинаковом входе.

Находка живого прогона: оценки плавали между сессиями (Hugo 90 → 70, Eleventy
60 → 85). Замер на **одних и тех же** прочитанных сайтах (обход исключён) показал,
что виновата не навигация, а сэмплинг стадии `compare`: при температуре 0.2 два
прогона подряд дали 90/80/60 и 82/78/65, при 0.0 — побитово одинаковый ответ.

Здесь проверяется контракт: стадия зовёт модель с нулевой температурой, и это
значение приходит из настроек, а не зашито в вызове.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.research.compare_synthesizer import CompareSynthesizer
from app.schemas.extraction import ExtractionResult

COMPARE_REPLY = {
    "winner": {"url": "http://a.test", "reason": "полнее"},
    "rankings": [
        {"url": "http://a.test", "score": 80, "summary": "полное руководство"},
        {"url": "http://b.test", "score": 60, "summary": "короткое"},
    ],
    "dimensions": [{"name": "coverage", "scores": {"a.test": 8, "b.test": 6}}],
    "narrative": "A полнее B",
}


class RecordingClient:
    """Фейковый LLM: запоминает параметры вызова и отдаёт готовый ответ."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        self.calls.append(kwargs)
        import json

        return json.dumps(COMPARE_REPLY), {"eval_count": 10}


def inputs_for() -> list[tuple[str, ExtractionResult]]:
    return [
        ("run-a", ExtractionResult(start_url="http://a.test", summary="A", facts=[], not_found=[])),
        ("run-b", ExtractionResult(start_url="http://b.test", summary="B", facts=[], not_found=[])),
    ]


async def test_compare_uses_zero_temperature_from_settings() -> None:
    client = RecordingClient()
    settings = Settings()
    compare = CompareSynthesizer(client, settings)  # type: ignore[arg-type]

    await compare.compare(task="чья статья полнее", rubric_id="content_completeness", inputs=inputs_for())

    assert client.calls, "стадия compare обязана позвать модель"
    assert client.calls[0]["temperature"] == 0.0, (
        "сравнение должно быть воспроизводимым: одинаковый вход — одинаковый ответ"
    )
    assert settings.compare_temperature == 0.0, "дефолт настройки — детерминированный"


async def test_temperature_is_configurable_not_hardcoded() -> None:
    """Значение берётся из настроек: замер можно повторить, не трогая код."""
    client = RecordingClient()
    compare = CompareSynthesizer(client, Settings(compare_temperature=0.7))  # type: ignore[arg-type]

    await compare.compare(task="чья статья полнее", rubric_id="content_completeness", inputs=inputs_for())

    assert client.calls[0]["temperature"] == 0.7
