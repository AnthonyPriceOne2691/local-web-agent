"""Compare Synthesizer (doc 24): N × ExtractionResult → R1 → ComparisonResult.

Рубрики — данные (`data/prompts/rubrics/*.txt`). num_ctx 24576 при N > 3 (doc 16/20).
run_id в rankings/winner проставляется кодом по url — LLM оперирует только url/label.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from jinja2 import Template
from pydantic import ValidationError

from app.config import Settings
from app.llm.json_chat import chat_json
from app.llm.ollama_client import OllamaClient, strip_thinking, supports_think
from app.llm.synthesizer import ARTICLE_TEXT_CAP
from app.schemas.extraction import ExtractionResult
from app.schemas.research import ComparisonOutput, ComparisonResult

SITE_SUMMARY_CAP = 1200
ARTICLE_EXCERPT_CAP = ARTICLE_TEXT_CAP  # ровно столько, сколько хранит снапшот (doc 20)
FACTS_PER_SITE = 12
WIDE_NUM_CTX = 24576  # N > 3 (doc 16)


def _host(url: str) -> str:
    """Метка сайта: netloc С портом — фикстуры на 127.0.0.1:* различимы только им."""
    return (urlparse(url).netloc or url).lower().removeprefix("www.")


def build_sites_block(inputs: list[tuple[str, ExtractionResult]]) -> str:
    blocks = []
    for run_id, res in inputs:
        label = _host(res.start_url)
        lines = [
            f"SITE: {label}",
            f"URL: {res.start_url}",
            f"RUN: {run_id}",
            f"SUMMARY: {res.summary[:SITE_SUMMARY_CAP]}",
        ]
        for fact in res.facts[:FACTS_PER_SITE]:
            lines.append(f"FACT {fact.key} ({fact.confidence}): {fact.value[:300]}")
        if res.design_tokens:
            import json

            lines.append("DESIGN_TOKENS: " + json.dumps(res.design_tokens, ensure_ascii=False)[:800])
        if res.article:
            a = res.article
            lines.append(
                f"ARTICLE: {a.title} | {a.url} | words={a.word_count} | headings={'; '.join(a.headings[:12])}"
            )
            lines.append(f"ARTICLE_EXCERPT: {a.main_text_excerpt[:ARTICLE_EXCERPT_CAP]}")
        if res.not_found:
            lines.append("NOT_FOUND: " + "; ".join(nf.key for nf in res.not_found[:6]))
        blocks.append("\n".join(lines))
    return "\n\n=====\n\n".join(blocks)


class CompareSynthesizer:
    def __init__(self, client: OllamaClient, settings: Settings):
        self._client = client
        self._s = settings
        prompts = settings.prompts_dir
        self._system = (prompts / "compare_system.txt").read_text(encoding="utf-8")
        self._user_tpl = Template((prompts / "compare_user.j2").read_text(encoding="utf-8"))
        self._rubrics_dir = prompts / "rubrics"

    def _rubric_text(self, rubric_id: str) -> str:
        path = self._rubrics_dir / f"{rubric_id}.txt"
        if not path.is_file():
            path = self._rubrics_dir / "generic_merge.txt"
        return path.read_text(encoding="utf-8")

    def _mode(self) -> tuple[bool, dict[str, Any] | None, int]:
        """Режим compare: (think, schema, narrative_cap) — по аналогии с синтезом.

        Схема доступна только при выключенном рассуждении (`format` × thinking
        несовместимы, doc 16). Дефолт — канон: стадия весит 21 % сессии, но
        качество сравнения (winner, порядок rankings) дороже её длительности.
        """
        if self._s.compare_think or not self._s.compare_schema:
            return self._s.compare_think, None, 0
        schema: dict[str, Any] = ComparisonOutput.model_json_schema()
        return False, schema, self._s.compare_narrative_cap

    async def compare(
        self,
        *,
        task: str,
        rubric_id: str,
        inputs: list[tuple[str, ExtractionResult]],
    ) -> tuple[ComparisonResult, dict[str, Any]]:
        think, schema, cap = self._mode()
        user = self._user_tpl.render(
            task=task,
            rubric_id=rubric_id,
            rubric=self._rubric_text(rubric_id),
            sites_count=len(inputs),
            sites_block=build_sites_block(inputs),
            narrative_cap=cap,
        )
        num_ctx = WIDE_NUM_CTX if len(inputs) > 3 else self._s.synth_num_ctx
        raw, content, stats = await chat_json(
            self._client,
            model=self._s.synth_model,
            system=self._system,
            user=user,
            retry_note="Your previous reply was not valid JSON. JSON object only.",
            schema=schema,
            think=think if supports_think(self._s.synth_model) else None,
            temperature=self._s.compare_temperature,  # воспроизводимость важнее разнообразия
            num_ctx=num_ctx,
            max_tokens=self._s.synth_max_tokens,
            # Стадия `compare` весит 36–41 % реальной сессии — бюджет ей нужен тот же, что
            # синтезу: у общего 300 s запаса на тяжёлый случай нет (замер, doc 20).
            timeout_s=self._s.synth_timeout_s,
        )
        if raw is None:
            return (ComparisonResult(status="failed", narrative=strip_thinking(content)[:500]), stats)
        result = self._validated(raw, task=task, rubric_id=rubric_id, inputs=inputs)
        return result, stats

    def _validated(
        self,
        raw: dict[str, Any],
        *,
        task: str,
        rubric_id: str,
        inputs: list[tuple[str, ExtractionResult]],
    ) -> ComparisonResult:
        by_host = {_host(res.start_url): (run_id, res) for run_id, res in inputs}
        by_url = {res.start_url: (run_id, res) for run_id, res in inputs}

        def resolve(url_or_label: str) -> tuple[str, ExtractionResult] | None:
            return by_url.get(url_or_label) or by_host.get(_host(url_or_label))

        raw_winner = raw.get("winner")
        if isinstance(raw_winner, dict) and "url" in raw_winner:  # LLM-shape → doc 05 shape
            raw_winner.setdefault("start_url", raw_winner.get("url"))
        try:
            result = ComparisonResult.model_validate(
                {**raw, "comparison_task": task, "rubric": rubric_id, "status": "completed"}
            )
        except ValidationError:
            return ComparisonResult(
                status="partial",
                comparison_task=task,
                rubric=rubric_id,
                narrative=str(raw.get("narrative", ""))[:2000],
            )
        # run_id — только детерминированно, по нашим inputs; чужие сайты отбрасываем
        # resolve() зовём один раз на ranking: раньше он вызывался дважды (в фильтре
        # и в цикле), и второй вызов формально мог вернуть None.
        resolved = [(r, hit) for r in result.rankings if (hit := resolve(r.url)) is not None]
        result.rankings = [r for r, _ in resolved]
        for ranking, (run_id, res) in resolved:
            ranking.run_id, ranking.url = run_id, res.start_url
        if result.winner is not None:
            hit = resolve(result.winner.start_url or result.winner.label)
            if hit is None:
                result.winner = None
            else:
                run_id, res = hit
                result.winner.run_id = run_id
                result.winner.start_url = res.start_url
                result.winner.label = result.winner.label or _host(res.start_url)
        return result
