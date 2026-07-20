"""Layer 2 Action registry (doc 25): импорт модуля действия = его регистрация.

Runner и llm_planner работают только через реестр (A-H1): membership-проверка,
пер-action enforce (M-H3), execute reply-block действий, описания для
meta-промпта (`prompt_block`). Новое действие: модуль здесь + register(...) +
`data/prompts/tools/<name>.txt` — runner/planner не трогаем.
"""

from app.research.actions import (  # noqa: F401 — импорт = регистрация
    compare,
    crawl,
    file_export,
    gdocs_export,
    list_runs,
    run_details,
)
from app.research.actions.base import ActionContext, ActionSpec
from app.research.actions.registry import get, names, prompt_block, register

__all__ = ["ActionContext", "ActionSpec", "get", "names", "prompt_block", "register"]
