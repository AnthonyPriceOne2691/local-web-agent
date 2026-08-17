"""SYNTHESIZE: снапшоты → R1 (think) → ExtractionResult (docs 05/14/16/20)."""

from __future__ import annotations

import json
from typing import Any

from jinja2 import Template
from pydantic import ValidationError

from app.config import Settings
from app.llm.json_chat import chat_json
from app.llm.ollama_client import OllamaClient, strip_thinking, supports_think
from app.observer.snapshot import MAIN_TEXT_CAP
from app.schemas.extraction import ExtractionResult, SynthesisOutput
from app.schemas.snapshot import PageSnapshot

PAGE_TEXT_CAP = 1000  # doc 20 synthesis bundle
PRIORITY_TEXT_CAP = 4000
# Сколько текста статьи уходит в синтез и дальше в сравнение. Привязан к тому, что снапшот
# РЕАЛЬНО хранит: раньше здесь стояло 12000 при `MAIN_TEXT_CAP` 8000, и верхняя треть бюджета
# не использовалась никогда — замер записей прогонов показал excerpt ровно 8000 у двух живых
# статей из трёх (King Arthur 3771 слово, legalbet 1380).
#
# Поднимать пару 8000/12000 вслепую нельзя, и это тоже замерено: блок сравнения трёх сайтов
# вырос бы с 25 620 до ~33 620 символов, то есть до ~13 450 токенов на русском, а с ответом
# (`synth_max_tokens` 4096) это 17 546 при `num_ctx` 16384 — переполнение. Подъём возможен
# только вместе с `WIDE_NUM_CTX` для сравнения (doc 20 § Бюджет статьи).
ARTICLE_TEXT_CAP = MAIN_TEXT_CAP  # content_search: excerpt для compare (doc 20)
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

    def _mode(self, intent: str) -> tuple[bool, dict[str, Any] | None, int]:
        """Режим синтеза по интенту: (think, schema, summary_cap) — doc 16.

        Канон (`think: true`, без схемы) остаётся там, где ответ по природе
        длинный: замер показал, что быстрый путь на `content_search` бимодален
        (350 ↔ 1265 токенов при одной конфигурации), а на извлечении —
        детерминирован и втрое дешевле. `format` + thinking несовместимы, поэтому
        схема появляется только в паре с выключенным рассуждением.
        """
        reasoning = self._s.synth_reasoning_intents.strip()
        canon = reasoning == "*" or intent in {i.strip() for i in reasoning.split(",") if i.strip()}
        if canon:
            return True, None, 0
        return False, SynthesisOutput.model_json_schema(), self._s.synth_summary_cap

    async def synthesize(
        self,
        *,
        task: str,
        snapshots: list[PageSnapshot],
        intent: str = "generic",
        unreached: list[str] | None = None,
        early_stop: str = "",
    ) -> tuple[ExtractionResult, dict[str, Any]]:
        """`unreached` — страницы, которые агент счёл нужными, но не открыл из-за
        своих же лимитов (doc 26 § T-3a-2). Без этого списка модель описывает
        исчерпание бюджета как отсутствие содержания на сайте: на живом прогоне
        она с `confidence: high` заявила, что в блоге Rust «нет подробного разбора
        релизов» — при том, что анонсы релизов там основной жанр, а статья лежала
        на третьем хопе при `max_depth: 2`.
        """
        think, schema, cap = self._mode(intent)
        user = self._user_tpl.render(
            task=task,
            intent=intent,
            pages_count=len(snapshots),
            pages_block=build_pages_block(snapshots, intent),
            summary_cap=cap,
            unreached=unreached or [],
            early_stop=early_stop,
        )
        raw, content, stats = await chat_json(
            self._client,
            model=self._s.synth_model,
            system=self._system,
            user=user,
            retry_note="Your previous reply was not valid JSON. Respond with the JSON object only.",
            schema=schema,
            think=think if supports_think(self._s.synth_model) else None,
            num_ctx=self._s.synth_num_ctx,
            max_tokens=self._s.synth_max_tokens,
            timeout_s=self._s.synth_timeout_s,
        )
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
            dropped = [
                k for k in ("article", "article_candidates_considered", "design_tokens") if k in payload
            ]
            for key in dropped:
                payload.pop(key, None)
            try:
                result = ExtractionResult.model_validate(payload)
                # След обязателен: без него «статьи нет» и «блок статьи не прошёл схему»
                # выглядят в ответе одинаково (doc 20 § Телеметрия синтеза).
                stats["dropped_blocks"] = dropped
            except ValidationError:
                result = ExtractionResult(status="partial", summary=str(raw.get("summary", ""))[:500])
                stats["invalid_payload"] = True
        return result, stats
