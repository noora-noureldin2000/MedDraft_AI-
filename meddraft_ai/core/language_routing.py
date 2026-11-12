"""Script-based task detection used by ``SkillRegistry`` auto-routing.

The Arabic mixed-direction skill is not selected by topic keywords: it is
selected by the *script* of the request. A task that mixes Arabic and Latin
letters is, by construction, a mixed-direction document task, and an English
request that names Arabic/RTL plus a document artefact is the same job
described in one language.
"""

from __future__ import annotations

import re

ARABIC_MIXED_RTL_SKILL = "arabic-mixed-rtl"

_ARABIC_SCRIPT = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)
_LATIN_SCRIPT = re.compile(r"[A-Za-z]")

_ARABIC_CUES = ("arabic", "rtl", "right-to-left", "bilingual", "mixed-direction", "bidi")
_DOCUMENT_CUES = (
    "document",
    "docx",
    ".doc",
    "word",
    "manuscript",
    "paper",
    "report",
    "citation",
    "format",
)


def contains_arabic_script(text: str) -> bool:
    return bool(text and _ARABIC_SCRIPT.search(text))


def contains_latin_script(text: str) -> bool:
    return bool(text and _LATIN_SCRIPT.search(text))


def is_mixed_arabic_latin(text: str) -> bool:
    """True when both Arabic and Latin letters appear in the same request."""
    return contains_arabic_script(text) and contains_latin_script(text)


def matches_mixed_arabic_document_task(text: str) -> bool:
    """True for mixed-script requests, or English requests naming Arabic/RTL documents."""
    if not text:
        return False
    if is_mixed_arabic_latin(text):
        return True
    lowered = text.lower()
    mentions_arabic = any(cue in lowered for cue in _ARABIC_CUES)
    mentions_document = any(cue in lowered for cue in _DOCUMENT_CUES)
    return mentions_arabic and mentions_document
