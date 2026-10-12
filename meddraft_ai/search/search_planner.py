"""Structured Scholar search planner (academic-search-agent skill — code layer).

Implements the portable, offline-safe subset of the upstream playbook:

  * ``plan_search_angles`` — Phase 1 breadth planning: 3–5 core search angles
    (review, timeline, seminal, recent, methods) derived from the raw topic.
  * Stalemate guard (``MAX_ATTEMPTS_PER_GOAL = 2``) and research-log word
    budgets (``RESEARCH_LOG_WORD_BUDGET = 5000``) from the skill's Golden Rules.
  * ``truncate_to_budget`` — active content compression helper.

Live searching stays with ``ResearchOrchestrator`` (deep_search /
scholar-stealth); this module only plans, so it is fully deterministic.
"""

from __future__ import annotations

import re

# Golden Rule 2 — never more than 2 invalid attempts on one blocked sub-goal.
MAX_ATTEMPTS_PER_GOAL = 2

# Golden Rule 2 — hard word-count ceilings for log and final report.
RESEARCH_LOG_WORD_BUDGET = 5000
REPORT_WORD_BUDGET = 5000
# Stop collecting new information once the log reaches this size.
STOP_COLLECTION_AT_WORDS = 4000

# Phase 1, Step 4a — deep-read at most this many authoritative URLs per round.
MAX_DEEP_READ_URLS = 4


def _clean_topic(topic: str) -> str:
    cleaned = re.sub(r"\s+", " ", (topic or "").strip()).strip("\"'")
    return cleaned[:200]


def plan_search_angles(topic: str, n: int = 5) -> list[str]:
    """Formulate 3–5 breadth-search angles for *topic* (Phase 1, Step 1).

    Pure function — no I/O, safe to call anywhere including tests.
    """
    base = _clean_topic(topic)
    if not base:
        return []
    angles = [
        f"{base} review",
        f"{base} timeline key papers",
        f"seminal papers on {base}",
        f"{base} recent advances",
        f"{base} methods comparison",
    ]
    n = max(3, min(n, 5))
    return angles[:n]


def count_words(text: str) -> int:
    """Whitespace word count used for budget enforcement."""
    return len((text or "").split())


def truncate_to_budget(text: str, budget: int = RESEARCH_LOG_WORD_BUDGET) -> str:
    """Compress *text* to *budget* words (Golden Rule 2: distill, don't copy).

    Keeps the head and tail of the text with an explicit omission marker so
    no silent mid-document loss occurs.
    """
    words = (text or "").split()
    if len(words) <= budget:
        return text or ""
    if budget < 10:
        return " ".join(words[:budget])
    head = budget * 3 // 4
    tail = budget - head
    omitted = len(words) - budget
    return (
        " ".join(words[:head])
        + f"\n\n[… {omitted} words distilled out under the {budget}-word research-log budget …]\n\n"
        + " ".join(words[-tail:])
    )


def should_stop_collecting(research_log: str) -> bool:
    """Dynamic stop mechanism: log at ~4000 words → proceed to synthesis."""
    return count_words(research_log) >= STOP_COLLECTION_AT_WORDS
