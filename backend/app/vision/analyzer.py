"""VisionAnalyzer (doc 23): PNG base64 → qwen2.5vl → VisionInsight.

Structured outputs (schema:VisionInsight, doc 16); invalid JSON → 1 retry
с «fix JSON» → degraded; HTTP/timeout → 1 retry → failed. Vision не валит run.
"""

from __future__ import annotations

import logging

from jinja2 import Template
from pydantic import ValidationError

from app.config import Settings
from app.llm.ollama_client import OllamaClient
from app.llm.parsing import extract_json
from app.schemas.snapshot import ViewportProfile
from app.vision.schemas import VisionInsight

logger = logging.getLogger(__name__)


class VisionAnalyzer:
    def __init__(self, client: OllamaClient, settings: Settings):
        self._client = client
        self._s = settings
        prompts = settings.prompts_dir
        self._system = (prompts / "vision_system.txt").read_text(encoding="utf-8")
        self._user_tpl = Template((prompts / "vision_user.j2").read_text(encoding="utf-8"))

    async def analyze(
        self,
        *,
        image_base64: str,
        task: str,
        url: str,
        profile: ViewportProfile,
        dom_excerpt: str | None = None,
    ) -> VisionInsight:
        user = self._user_tpl.render(
            task=task, url=url, profile=profile, dom_excerpt=(dom_excerpt or "")[:1500]
        )
        insight, raw_error = await self._call(user, image_base64, retry_note="")
        if insight is None:  # 1 retry: почини JSON (doc 23 § Error handling)
            insight, raw_error = await self._call(
                user, image_base64,
                retry_note="\nYour previous reply was not valid JSON. "
                           "Respond with the VisionInsight JSON object only.",
            )
        if insight is None:
            status = "failed" if raw_error else "degraded"
            return VisionInsight(profile=profile, url=url, status=status,
                                 confidence="low", error=raw_error or "invalid JSON after retry")
        insight.profile = profile  # поля источника — истина оркестратора
        insight.url = url
        insight.status = "ok"
        return insight

    async def _call(
        self, user: str, image_base64: str, *, retry_note: str
    ) -> tuple[VisionInsight | None, str | None]:
        try:
            content, _ = await self._client.chat(
                model=self._s.vision_model,
                system=self._system,
                user=user + retry_note,
                schema=VisionInsight.model_json_schema(),
                temperature=0.2,
                num_ctx=self._s.vision_num_ctx,
                max_tokens=self._s.vision_max_tokens,
                keep_alive="5m",
                images=[image_base64],
            )
        except Exception as exc:
            # Vision не валит run (doc 23): причина уезжает вызывающему строкой,
            # но без лога в vision_errors теряется класс сбоя (таймаут vs OOM).
            logger.warning("vision call failed (%s): %s", type(exc).__name__, str(exc)[:200])
            return None, str(exc)[:200]
        raw = extract_json(content)
        if raw is None:
            return None, None
        try:
            return VisionInsight.model_validate(raw), None
        except ValidationError:
            return None, None
