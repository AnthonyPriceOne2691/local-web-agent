"""SYNTHESIZE: снапшоты → R1 (think) → ExtractionResult (docs 05/14/16/20)."""

from __future__ import annotations

from jinja2 import Template
from pydantic import ValidationError

from app.config import Settings
from app.llm.ollama_client import OllamaClient, strip_thinking, supports_think
from app.llm.parsing import extract_json
from app.schemas.extraction import ExtractionResult
from app.schemas.snapshot import PageSnapshot

PAGE_TEXT_CAP = 1000  # doc 20 synthesis bundle
PRIORITY_TEXT_CAP = 4000


def build_pages_block(snapshots: list[PageSnapshot]) -> str:
    blocks = []
    for s in snapshots:
        cap = PRIORITY_TEXT_CAP if s.priority else PAGE_TEXT_CAP
        headings = "; ".join(h.text for h in s.headings[:8])
        blocks.append(f"URL: {s.url}\nTITLE: {s.title}\nHEADINGS: {headings}\nTEXT: {s.main_text[:cap]}\n")
    return "\n---\n".join(blocks)


class Synthesizer:
    def __init__(self, client: OllamaClient, settings: Settings):
        self._client = client
        self._s = settings
        prompts = settings.prompts_dir
        self._system = (prompts / "synthesizer_system.txt").read_text(encoding="utf-8")
        self._user_tpl = Template((prompts / "synthesizer_user.j2").read_text(encoding="utf-8"))

    async def synthesize(self, *, task: str, snapshots: list[PageSnapshot]) -> tuple[ExtractionResult, dict]:
        user = self._user_tpl.render(
            task=task, pages_count=len(snapshots), pages_block=build_pages_block(snapshots)
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
        try:
            result = ExtractionResult.model_validate({**raw, "status": raw.get("status", "completed")})
        except ValidationError:
            result = ExtractionResult(status="partial", summary=str(raw.get("summary", ""))[:500])
        return result, stats
