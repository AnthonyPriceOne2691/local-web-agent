"""Ollama HTTP client (doc 16): structured outputs, think-param с fallback,
eval-телеметрия, keep_alive для model swap (doc 14)."""

from __future__ import annotations

import re

import httpx

THINK_MODEL_HINTS = ("qwen3", "r1", "gpt-oss", "magistral")
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


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
        schema: dict | None = None,
        think: bool | None = None,
        temperature: float = 0.2,
        num_ctx: int = 8192,
        max_tokens: int = 1024,
        keep_alive: str | int = "10m",
        images: list[str] | None = None,
    ) -> tuple[str, dict]:
        user_msg: dict = {"role": "user", "content": user}
        if images:  # multimodal (doc 23): base64 PNG в images[]
            user_msg["images"] = images
        body: dict = {
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
        content = data.get("message", {}).get("content", "")
        stats = {
            k: data[k]
            for k in ("eval_count", "prompt_eval_count", "eval_duration", "total_duration")
            if k in data
        }
        return content, stats

    async def unload(self, model: str) -> None:
        try:
            await self._client.post(f"{self.base_url}/api/generate", json={"model": model, "keep_alive": 0})
        except httpx.HTTPError:
            pass

    async def health(self) -> dict:
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
