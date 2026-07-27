"""PLAN step: prompt из data/prompts → Qwen → AgentAction (docs 04/16)."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Template
from pydantic import ValidationError

from app.config import Settings
from app.llm.ollama_client import OllamaClient, supports_think
from app.llm.parsing import extract_json
from app.schemas.snapshot import AgentAction, Candidate, PageSnapshot


def _interactive_block(snapshot: PageSnapshot, cap: int = 30) -> str:
    """Нумерованные интерактивные элементы для click (doc 25 Tier 1). submit/password/
    disabled помечены небезопасными — enforcer их всё равно заблокирует (I-H10)."""
    lines = []
    for el in snapshot.interactive_elements[:cap]:
        unsafe = el.kind in ("submit", "password") or el.input_type in ("submit", "password") or el.disabled
        tag = "  ⚠ do NOT click (submit/login/disabled)" if unsafe else ""
        lines.append(f"{el.index}. [{el.kind}] {el.label[:50]}{tag}")
    return "\n".join(lines) or "(none)"


class Navigator:
    def __init__(self, client: OllamaClient, settings: Settings):
        self._client = client
        self._s = settings
        prompts: Path = settings.prompts_dir
        self._system = (prompts / "navigator_system.txt").read_text(encoding="utf-8")
        self._user_tpl = Template((prompts / "navigator_user.j2").read_text(encoding="utf-8"))

    async def propose(
        self,
        *,
        task: str,
        intent: str,
        snapshot: PageSnapshot,
        candidates: list[Candidate],
        visited: set[str],
        pages_left: int,
        retry_note: str = "",
        temperature: float = 0.4,
    ) -> tuple[AgentAction | None, dict]:
        cand_block = (
            "\n".join(
                f"{i + 1}. {c.href}  [{c.text[:60]}] (score {c.score}, {c.reason})"
                for i, c in enumerate(candidates)
            )
            or "(none)"
        )
        user = self._user_tpl.render(
            task=task,
            intent=intent,
            pages_left=pages_left,
            snapshot=snapshot,
            headings_json=json.dumps([h.model_dump() for h in snapshot.headings[:10]], ensure_ascii=False),
            main_text=snapshot.main_text[:3000],
            visited_json=json.dumps(sorted(visited), ensure_ascii=False),
            candidates_block=cand_block,
            interactive_block=_interactive_block(snapshot),
        )
        if retry_note:
            user += f"\n\nPREVIOUS ATTEMPT REJECTED: {retry_note}. Choose strictly from the candidate list."
        content, stats = await self._client.chat(
            model=self._s.nav_model,
            system=self._system,
            user=user,
            schema=AgentAction.model_json_schema(),
            think=False if supports_think(self._s.nav_model) else None,
            temperature=temperature,  # 0.4; drift auto-tighten → 0.2 (doc 13)
            num_ctx=self._s.nav_num_ctx,
            max_tokens=self._s.nav_max_tokens,
        )
        raw = extract_json(content)
        if raw is None:
            return None, stats
        try:
            return AgentAction.model_validate(raw), stats
        except ValidationError:
            return None, stats
