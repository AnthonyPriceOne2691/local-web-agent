"""SYNTHESIZE: снапшоты → R1 (think) → ExtractionResult (docs 05/14/16/20)."""

from __future__ import annotations

import json

from jinja2 import Template
from pydantic import ValidationError

from app.config import Settings
from app.llm.ollama_client import OllamaClient, strip_thinking, supports_think
from app.llm.parsing import extract_json
from app.schemas.extraction import ExtractionResult
from app.schemas.snapshot import PageSnapshot

PAGE_TEXT_CAP = 1000  # doc 20 synthesis bundle
PRIORITY_TEXT_CAP = 4000
ARTICLE_TEXT_CAP = 12000  # content_search: полный excerpt для compare (doc 20)
VISION_DESC_CAP = 400


def build_pages_block(snapshots: list[PageSnapshot], intent: str = "generic") -> str:
    blocks = []
    for s in snapshots:
        if s.priority:
            cap = ARTICLE_TEXT_CAP if intent == "content_search" else PRIORITY_TEXT_CAP
        else:
            cap = PAGE_TEXT_CAP
        headings = "; ".join(h.text for h in s.headings[:8])
        block = f"URL: {s.url}\nTITLE: {s.title}\nHEADINGS: {headings}\nTEXT: {s.main_text[:cap]}\n"
        block += _vision_block(s)
        blocks.append(block)
    return "\n---\n".join(blocks)


def _vision_block(s: PageSnapshot) -> str:
    """Vision insights текстом для R1 (doc 23 § Integration): без raw PNG."""
    lines = []
    for ins in s.vision_insights:
        if ins.get("status") != "ok":
            continue
        parts = [f"VISION ({ins.get('profile', '?')}): {ins.get('description', '')[:VISION_DESC_CAP]}"]
        if ins.get("extracted"):
            parts.append("extracted: " + json.dumps(ins["extracted"], ensure_ascii=False))
        if ins.get("design"):
            parts.append("design: " + json.dumps(ins["design"], ensure_ascii=False)[:300])
        if ins.get("text_not_in_dom"):
            parts.append("text_not_in_dom: " + json.dumps(ins["text_not_in_dom"], ensure_ascii=False))
        lines.append(" | ".join(parts))
    return ("\n".join(lines) + "\n") if lines else ""


class Synthesizer:
    def __init__(self, client: OllamaClient, settings: Settings):
        self._client = client
        self._s = settings
        prompts = settings.prompts_dir
        self._system = (prompts / "synthesizer_system.txt").read_text(encoding="utf-8")
        self._user_tpl = Template((prompts / "synthesizer_user.j2").read_text(encoding="utf-8"))

    async def synthesize(
        self, *, task: str, snapshots: list[PageSnapshot], intent: str = "generic"
    ) -> tuple[ExtractionResult, dict]:
        user = self._user_tpl.render(
            task=task, intent=intent, pages_count=len(snapshots),
            pages_block=build_pages_block(snapshots, intent),
        )
        content, stats = await self._client.chat(
            model=self._s.synth_model,
            system=self._system,
            user=user,
            think=True if supports_think(self._s.synth_model) else None,
            temperature=0.2,
            num_ctx=self._s.synth_num_ctx,
            max_tokens=self._s.synth_max_tokens,
            keep_alive=0,  # swap discipline (doc 14)
        )
        raw = extract_json(content)
        if raw is None:  # recovery: 1 retry (doc 05 § Validation)
            content, stats2 = await self._client.chat(
                model=self._s.synth_model,
                system=self._system,
                user=user + "\n\nYour previous reply was not valid JSON. Respond with the JSON object only.",
                think=True if supports_think(self._s.synth_model) else None,
                temperature=0.2,
                num_ctx=self._s.synth_num_ctx,
                max_tokens=self._s.synth_max_tokens,
                keep_alive=0,
            )
            stats = stats2
            raw = extract_json(content)
        if raw is None:
            return (
                ExtractionResult(status="partial", summary=strip_thinking(content)[:500]),
                stats,
            )
        payload = {**raw, "status": raw.get("status", "completed")}
        try:
            result = ExtractionResult.model_validate(payload)
        except ValidationError:
            # чаще всего валидацию валят опциональные блоки (article/design) —
            # отбросить их и сохранить факты, а не ронять весь результат в пустой partial
            for key in ("article", "article_candidates_considered", "design_tokens"):
                payload.pop(key, None)
            try:
                result = ExtractionResult.model_validate(payload)
            except ValidationError:
                result = ExtractionResult(status="partial",
                                          summary=str(raw.get("summary", ""))[:500])
        return result, stats
