"""Robust JSON extraction из LLM-ответов (raw_decode — устойчив к { в строках)."""

from __future__ import annotations

import json

from app.llm.ollama_client import strip_thinking


def extract_json(text: str) -> dict | None:
    text = strip_thinking(text)
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx >= 0:
        try:
            obj, _ = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)
    return None
