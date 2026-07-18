"""Crawl state machine states (doc 04). VISION_BATCH — Phase 2."""

from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    INIT = "INIT"
    OBSERVE = "OBSERVE"
    PLAN = "PLAN"
    VALIDATE = "VALIDATE"
    ACT = "ACT"
    SYNTHESIZE = "SYNTHESIZE"
    DONE = "DONE"
