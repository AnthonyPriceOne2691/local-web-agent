"""LLM-планнер Phase 4 (doc 24 § Planner, mode `planner: llm`).

Rules-планнер остаётся fast-path (URLs в сообщении → детерминированный план);
LLM подключается для свободного диалога: follow-up вопросы, re-compare,
замена сайта. Пост-валидация — контракты M-H1..M-H3 через Action registry
(doc 25, A-H1): только зарегистрированные действия, пер-action enforce
(URL из ALLOWED URLS, run_id из runs сессии), crawl_site ≤ max_sites.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.llm.ollama_client import OllamaClient, supports_think
from app.llm.parsing import extract_json
from app.research import actions
from app.research.meta_agent import ToolCall, parse_urls
from app.schemas.research import SessionRecord
from app.storage.run_store import RunStore

MAX_HISTORY_MESSAGES = 8
FALLBACK_REPLY = ("Не понял задачу. Пришли URL сайтов и что по ним исследовать — "
                  "или задай вопрос по уже готовым результатам этой сессии.")


class PlannerDecision(BaseModel):
    plan: list[ToolCall] = Field(default_factory=list)
    reply: str = ""


class LlmPlanner:
    def __init__(self, client: OllamaClient, settings: Settings):
        self._client = client
        self._s = settings
        prompts = settings.prompts_dir
        self._system = ((prompts / "meta_planner_system.txt")
                        .read_text(encoding="utf-8")
                        .replace("{TOOLS_BLOCK}", actions.prompt_block(prompts)))
        from jinja2 import Template

        self._user_tpl = Template(
            (prompts / "meta_planner_user.j2").read_text(encoding="utf-8"))

    # --------------------------------------------------------------- plan
    async def plan(
        self, session: SessionRecord, message: str, *, run_store: RunStore,
    ) -> PlannerDecision:
        """Meta-промпт → план; невалидный ответ LLM → пустой план + fallback reply."""
        allowed_urls = self._allowed_urls(session, message)
        user = self._user_tpl.render(
            runs_block=self._runs_block(session, run_store),
            comparison_block=self._comparison_block(session),
            history_block=self._history_block(session),
            allowed_urls_block="\n".join(allowed_urls) or "(none)",
            max_sites=session.config.max_sites,
            message=message,
        )
        content, _stats = await self._client.chat(
            model=self._s.nav_model,
            system=self._system,
            user=user,
            schema=PlannerDecision.model_json_schema(),
            think=False if supports_think(self._s.nav_model) else None,
            temperature=0.2,
            num_ctx=self._s.nav_num_ctx,
            max_tokens=self._s.planner_max_tokens,
        )
        raw = extract_json(content)
        if raw is None:
            return PlannerDecision(reply=FALLBACK_REPLY)
        try:
            decision = PlannerDecision.model_validate(raw)
        except ValidationError:
            return PlannerDecision(reply=FALLBACK_REPLY)
        decision.plan = self._enforce(decision.plan, session, allowed_urls, run_store)
        if not decision.plan and not decision.reply.strip():
            decision.reply = FALLBACK_REPLY
        return decision

    # ------------------------------------------- контракты M-H1..M-H3 / A-H1
    def _enforce(
        self, plan: list[ToolCall], session: SessionRecord,
        allowed_urls: list[str], run_store: RunStore,
    ) -> list[ToolCall]:
        """Membership + пер-action enforce — реестр (doc 25); здесь остаются
        только кросс-плановые правила: M-H2 и «compare один, последним»."""
        ctx = actions.ActionContext(session=session, run_store=run_store,
                                    settings=self._s, allowed_urls=frozenset(allowed_urls))
        kept: list[ToolCall] = []
        crawls = 0
        for call in plan:
            spec = actions.get(call.name)
            if spec is None:  # M-H1/A-H1: не зарегистрировано → отброшено
                continue
            checked = spec.enforce(call, ctx) if spec.enforce else call
            if checked is None:
                continue
            if checked.name == "crawl_site":
                crawls += 1
                if crawls > session.config.max_sites:  # M-H2
                    continue
            kept.append(checked)
        # compare — максимум один и последним (после его crawl-зависимостей)
        compares = [c for c in kept if c.name == "compare_results"]
        if compares:
            kept = [c for c in kept if c.name != "compare_results"] + compares[:1]
        return kept

    # ------------------------------------------------------ prompt context
    @staticmethod
    def _allowed_urls(session: SessionRecord, message: str) -> list[str]:
        urls = parse_urls(message, max_sites=session.config.max_sites)
        for m in session.messages:
            if m.role == "user":
                urls.extend(parse_urls(m.content, max_sites=session.config.max_sites))
        seen: set[str] = set()
        return [u for u in urls if not (u in seen or seen.add(u))]

    @staticmethod
    def _runs_block(session: SessionRecord, run_store: RunStore) -> str:
        lines = []
        for run_id in session.run_ids:
            r = run_store.get(run_id)
            if r is None:
                continue
            summary = (r.result.summary[:100] if r.result else r.error_message[:100]) or "-"
            lines.append(f"{r.id} | {r.config.start_url} | {r.status} | {r.intent} | {summary}")
        return "\n".join(lines) or "(none)"

    @staticmethod
    def _comparison_block(session: SessionRecord) -> str:
        c = session.comparison_result
        if c is None:
            return ""
        parts = [f"rubric={c.rubric}"]
        if c.winner:
            parts.append(f"winner: {c.winner.label or c.winner.start_url} — {c.winner.reason[:120]}")
        for r in c.rankings:
            parts.append(f"{r.url}: {r.score} ({r.summary[:80]})")
        if c.narrative:
            parts.append(f"narrative: {c.narrative[:400]}")
        return "\n".join(parts)

    @staticmethod
    def _history_block(session: SessionRecord) -> str:
        recent = session.messages[-MAX_HISTORY_MESSAGES:]
        return "\n".join(f"{m.role}: {m.content[:300]}" for m in recent) or "(none)"
