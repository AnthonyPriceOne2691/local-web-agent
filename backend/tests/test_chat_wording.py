"""Служебный текст не уезжает в чат, а язык вывода — только английский (doc 17 § Словарь).

Оба дефекта видел владелец в интерфейсе после живых прогонов:

1. в ответе стояло `couldn't be read (Page.evaluate: TypeError: Cannot read properties of
   null (reading 'innerText') at eval (…) at UtilityScript.evaluate (…))` — три строки
   стека Playwright там, где нужна одна человеческая фраза;
2. на русской задаче `narrative` и `summary` приходили по-русски. Решение владельца:
   **вся информация в интерфейсе по-английски**, даже если сайты русские. Прежнее правило
   промптов («in the language of the TASK») это и вызывало.
"""

from __future__ import annotations

from pathlib import Path

from app.research.phrasing import exclusion_reason, humanize_detail

PROMPTS = Path(__file__).resolve().parents[2] / "data" / "prompts"

STACK = (
    "Page.evaluate: TypeError: Cannot read properties of null (reading 'innerText')\n"
    "    at eval (eval at evaluate (:303:30), <anonymous>:9:24)\n"
    "    at UtilityScript.evaluate (<anonymous>:310:18)"
)


# --- служебный текст ---


def test_stack_trace_never_reaches_the_chat():
    reason = exclusion_reason("failed", None, STACK)

    assert "UtilityScript" not in reason
    assert "TypeError" not in reason
    assert "at eval" not in reason
    assert reason.startswith("couldn't be read")


def test_known_technical_causes_become_human_phrases():
    assert humanize_detail(STACK) == "the page never finished loading"
    assert humanize_detail("Page.goto: Timeout 30000ms exceeded") == "the site did not respond in time"
    assert humanize_detail("net::ERR_NAME_NOT_RESOLVED") == "the address could not be resolved"
    assert humanize_detail("TargetClosedError") == "the browser was closed"


def test_blocker_names_pass_through():
    """`blocked_by` — наш собственный короткий словарь, его прятать не надо."""
    assert exclusion_reason("blocked", "captcha", None) == "blocked us — captcha"
    assert exclusion_reason("blocked", "login_wall", None) == "blocked us — login_wall"


def test_unrecognized_long_text_is_dropped_entirely():
    noise = "SomeInternalError: " + "x" * 200
    assert humanize_detail(noise) == ""
    assert exclusion_reason("failed", None, noise) == "couldn't be read"


def test_no_detail_leaves_a_clean_phrase():
    assert exclusion_reason("not_found", None, None) == "had nothing on the topic"
    assert humanize_detail(None) == ""
    assert humanize_detail("") == ""


# --- язык вывода ---


def test_synthesis_prompt_demands_english_regardless_of_task_language():
    text = (PROMPTS / "synthesizer_system.txt").read_text(encoding="utf-8")

    assert "Write everything in English" in text
    assert "in the language of the TASK" not in text, "старое правило и давало русский вывод"


def test_compare_prompt_demands_english_regardless_of_task_language():
    text = (PROMPTS / "compare_system.txt").read_text(encoding="utf-8")

    assert "Write everything in English" in text
    assert "in the language of the TASK" not in text


def test_quotes_are_explicitly_exempt_from_translation():
    """Цитата — доказательство: её перевод сорвал бы сверку S-H3 с DOM."""
    for name in ("synthesizer_system.txt", "compare_system.txt"):
        text = (PROMPTS / name).read_text(encoding="utf-8")
        assert "verbatim" in text.lower()
        assert "quote" in text.lower()
