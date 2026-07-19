"""Реестр named checks (doc 13 § ContractSpec): loader отклоняет всё вне KNOWN_CHECKS.

Checks сгруппированы по стадии исполнения:
- CONFIG_CHECKS — на старте run (preconditions + config governance);
- ACTION_CHECKS — shield перед каждым Playwright-действием;
- orchestrator/synthesis/vision — enforcement живёт в state machine,
  SynthesisValidator и VisionLoader соответственно (имена валидируются здесь).
"""

from __future__ import annotations

from app.contracts.rules import budget, navigation

CONFIG_CHECKS = {
    "url_scheme": budget.url_scheme,
    "non_empty": budget.non_empty,
    "rate_limit_floor": budget.rate_limit_floor,
    "page_timeout_ceiling": budget.page_timeout_ceiling,
}

ACTION_CHECKS = {
    "url_in_allowed_domains": navigation.url_in_allowed_domains,
    "url_in_candidate_queue": navigation.url_in_candidate_queue,
    "public_http_url": navigation.public_http_url,
    "action_not_in": navigation.action_not_in,
    "url_not_visited": navigation.url_not_visited,
    "intent_conditional_paths": navigation.intent_conditional_paths,
    "click_target_safe": navigation.click_target_safe,  # I-H10 (doc 25 Tier 1)
    "fill_target_safe": navigation.fill_target_safe,  # I-H11 (doc 25 Tier 2)
    "pages_budget": budget.pages_budget,
    "hop_depth": budget.hop_depth,
    "robots_allowed": budget.robots_allowed,
}

ORCHESTRATOR_CHECKS = {"browser_session_active", "post_navigation_domain", "orchestrator_state"}

SYNTHESIS_CHECKS = {
    "min_snapshots", "pydantic_model", "confidence_evidence", "evidence_substring",
    "strip_thinking_nonempty", "prefer_not_found_over_empty", "facts_budget",
}

VISION_CHECKS = {
    "min_screenshots_or_never", "screenshot_path_allowlist", "path_normalize_safe",
    "file_size_ceiling", "profile_allowed", "vision_pages_budget", "vision_calls_budget",
    "vlm_timeout_ceiling",
}

KNOWN_CHECKS = (
    set(CONFIG_CHECKS) | set(ACTION_CHECKS) | ORCHESTRATOR_CHECKS
    | SYNTHESIS_CHECKS | VISION_CHECKS
)
