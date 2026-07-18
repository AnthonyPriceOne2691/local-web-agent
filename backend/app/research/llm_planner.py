"""LLM-планнер Phase 4 (doc 24 § Planner, mode `planner: llm`).

Rules-планнер остаётся fast-path (URLs в сообщении → детерминированный план);
LLM подключается для свободного диалога: follow-up вопросы, re-compare,
замена сайта. Пост-валидация — контракты M-H1..M-H3: только известные tools,
crawl_site ≤ max_sites и только по ALLOWED URLS (сообщение + прошлые start_url
сессии), run_id только из runs сессии — выдуманное отбрасывается.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.llm.ollama_client import OllamaClient, supports_think
from app.llm.parsing import extract_json
from app.research.meta_agent import RUBRIC_BY_INTENT, ToolCall, parse_urls
from app.schemas.research import SessionRecord
from app.storage.run_store import RunStore

PLANNER_TOOLS = ("crawl_site", "get_run_result", "compare_results", "list_session_runs")
KNOWN_RUBRICS = tuple(RUBRIC_BY_INTENT.values())
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
        self._system = (prompts / "meta_planner_system.txt").read_text(encoding="utf-8")
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
        decision.plan = self._enforce(decision.plan, session, set(allowed_urls))
        if not decision.plan and not decision.reply.strip():
            decision.reply = FALLBACK_REPLY
        return decision

    # ------------------------------------------------- контракты M-H1..M-H3
    def _enforce(
        self, plan: list[ToolCall], session: SessionRecord, allowed_urls: set[str],
    ) -> list[ToolCall]:
        run_ids = set(session.run_ids)
        kept: list[ToolCall] = []
        crawls = 0
        for call in plan:
            if call.name not in PLANNER_TOOLS:  # M-H1
                continue
            if call.name == "crawl_site":
                url = call.args.get("url")
                if url not in allowed_urls:  # M-H3: только пользовательские URL
                    continue
                crawls += 1
                if crawls > session.config.max_sites:  # M-H2
                    continue
                call.args["max_pages"] = min(int(call.args.get("max_pages") or
                                                 self._s.max_pages), 12)
            elif call.name == "get_run_result":
                if call.args.get("run_id") not in run_ids:  # M-H3
                    continue
            elif call.name == "compare_results":
                ids = [r for r in call.args.get("run_ids") or [] if r in run_ids]
                call.args["run_ids"] = ids
                if call.args.get("rubric") not in KNOWN_RUBRICS:
                    call.args["rubric"] = "generic_merge"
            kept.append(call)
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
