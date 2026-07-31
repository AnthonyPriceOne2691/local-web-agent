"""Ollama HTTP client (doc 16): structured outputs, think-param с fallback,
eval-телеметрия, keep_alive для model swap (doc 14)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

THINK_MODEL_HINTS = ("qwen3", "r1", "gpt-oss", "magistral")
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


logger = logging.getLogger(__name__)


def supports_think(model: str) -> bool:
    return any(h in model for h in THINK_MODEL_HINTS)


def strip_thinking(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


class OllamaClient:
    def __init__(self, base_url: str, timeout_s: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def chat(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        think: bool | None = None,
        temperature: float = 0.2,
        num_ctx: int = 8192,
        max_tokens: int = 1024,
        keep_alive: str | int = "10m",
        images: list[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        user_msg: dict[str, Any] = {"role": "user", "content": user}
        if images:  # multimodal (doc 23): base64 PNG в images[]
            user_msg["images"] = images
        body: dict[str, Any] = {
            "model": model,
            "stream": False,
            "keep_alive": keep_alive,
            "messages": [
                {"role": "system", "content": system},
                user_msg,
            ],
            "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": max_tokens},
        }
        if schema is not None:
            body["format"] = schema
        if think is not None and supports_think(model):
            body["think"] = think
        r = await self._client.post(f"{self.base_url}/api/chat", json=body)
        if r.status_code == 400 and "think" in body:  # старый Ollama / модель без think
            body.pop("think")
            r = await self._client.post(f"{self.base_url}/api/chat", json=body)
        r.raise_for_status()
        data = r.json()
        message = data.get("message", {})
        content = message.get("content", "")
        stats: dict[str, Any] = {
            k: data[k]
            for k in ("eval_count", "prompt_eval_count", "eval_duration", "total_duration")
            if k in data
        }
        # 87–97 % времени синтеза уходит на генерацию (замер 2026-07-31), а при
        # think:true бо́льшая часть выхода — рассуждение, которое в ответ не попадает.
        # Без этих двух чисел не видно, что именно резать: мысли или сам ответ.
        stats["thinking_chars"] = len(message.get("thinking") or "")
        stats["content_chars"] = len(content)
        # Модель — часть телеметрии шага: с маршрутизацией лёгкая/тяжёлая (doc 16)
        # иначе не видно, кто принял решение, и замер нечем подтвердить.
        stats["model"] = model
        return content, stats

    async def warmup(self, model: str, keep_alive: str | int = "10m") -> None:
        """Загрузить модель в память заранее (пустой prompt = только load).

        Первое решение агента иначе оплачивает загрузку весов: замер живого
        прогона — 8.7 s против 3.6 s у последующих. Греем параллельно с robots и
        slug-пробами, чтобы к открытию браузера модель уже была готова.
        """
        try:
            await self._client.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": "", "keep_alive": keep_alive},
            )
        except httpx.HTTPError as exc:  # прогрев — best-effort, run не зависит от него
            logger.debug("warmup of %s skipped (%s)", model, type(exc).__name__)

    async def unload_many(self, *models: str) -> None:
        """Выгрузить несколько моделей (пустые и дубли пропускаются).

        Нужно на swap nav → synth: с маршрутизацией (doc 16) в памяти могут
        оказаться обе nav-модели, и лёгкая держала бы свои ~5 GB, пока синтез
        работает на 16K ctx. Дисциплина RAM на 32 GB это не прощает.
        """
        for model in dict.fromkeys(m for m in models if m):
            await self.unload(model)

    async def unload(self, model: str) -> None:
        try:
            await self._client.post(f"{self.base_url}/api/generate", json={"model": model, "keep_alive": 0})
        except httpx.HTTPError:
            pass

    async def health(self) -> dict[str, Any]:
        try:
            version = (await self._client.get(f"{self.base_url}/api/version", timeout=3)).json()
            tags = (await self._client.get(f"{self.base_url}/api/tags", timeout=3)).json()
            return {
                "reachable": True,
                "version": version.get("version", ""),
                "models": [m["name"] for m in tags.get("models", [])],
            }
        except httpx.HTTPError:
            return {"reachable": False, "version": "", "models": []}

    async def aclose(self) -> None:
        await self._client.aclose()
