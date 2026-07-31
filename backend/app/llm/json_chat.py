"""Вызов модели с ожиданием JSON и одним повтором (docs 05 § Validation, 16).

Паттерн один и тот же у синтеза и у compare: спросить модель → распарсить JSON →
если не распарсился, переспросить один раз с пометкой. Он жил копией в двух
модулях (и дважды внутри `compare_synthesizer`), и DRY-гейт это поймал, когда
добавление схемы сделало блоки идентичными. Здесь — единственная реализация.
"""

from __future__ import annotations

from typing import Any

from app.llm.ollama_client import OllamaClient
from app.llm.parsing import extract_json


async def chat_json(
    client: OllamaClient,
    *,
    model: str,
    system: str,
    user: str,
    retry_note: str,
    schema: dict[str, Any] | None = None,
    think: bool | None = None,
    temperature: float = 0.2,
    num_ctx: int = 16384,
    max_tokens: int = 4096,
    keep_alive: str | int = 0,  # swap discipline: nav → synth (doc 14)
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    """`(raw, content, stats)`; `raw is None` → JSON не получен и после повтора.

    `content` возвращается всегда: на провале из него собирается partial-ответ, и
    терять текст модели нельзя. `stats` — телеметрия последнего вызова (модель,
    токены, мысли), по ней считаются замеры стадий.
    """
    content, stats = await client.chat(
        model=model,
        system=system,
        user=user,
        schema=schema,
        think=think,
        temperature=temperature,
        num_ctx=num_ctx,
        max_tokens=max_tokens,
        keep_alive=keep_alive,
    )
    raw = extract_json(content)
    if raw is not None:
        return raw, content, stats
    content, stats = await client.chat(
        model=model,
        system=system,
        user=f"{user}\n\n{retry_note}",
        schema=schema,
        think=think,
        temperature=temperature,
        num_ctx=num_ctx,
        max_tokens=max_tokens,
        keep_alive=keep_alive,
    )
    return extract_json(content), content, stats
