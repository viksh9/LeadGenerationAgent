"""Job-title normalization + seniority extraction.

Expands common abbreviations into a consistent normalized title while ALWAYS
preserving the original. Deliberately conservative — it does not invent seniority
that the title does not state, and it does not map ambiguous titles (e.g.
"Software Development Engineer II") onto a different level.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from processors.normalization.text import clean_ws, title_case


class SeniorityLevel(str, Enum):
    INTERN = "INTERN"
    TRAINEE = "TRAINEE"
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"
    LEAD = "LEAD"
    STAFF = "STAFF"
    PRINCIPAL = "PRINCIPAL"
    MANAGER = "MANAGER"
    DIRECTOR = "DIRECTOR"
    VP = "VP"
    EXECUTIVE = "EXECUTIVE"
    UNKNOWN = "UNKNOWN"


# Ordered abbreviation expansions (applied on a lowercase working copy, word-bounded).
# Configurable — extend as new source variants appear.
_ABBREVIATIONS: tuple[tuple[str, str], ...] = (
    (r"\bsr\b\.?", "senior"),
    (r"\bjr\b\.?", "junior"),
    (r"\bmgr\b\.?", "manager"),
    (r"\bengg\b\.?", "engineer"),
    (r"\bdev\b", "developer"),
    (r"\bsw\b", "software"),
    (r"\bse\b", "software engineer"),
    (r"\bfullstack\b", "full stack"),
)

# Seniority cues checked most-senior first; each maps a set of tokens to a level.
_SENIORITY_RULES: tuple[tuple[SeniorityLevel, tuple[str, ...]], ...] = (
    (SeniorityLevel.EXECUTIVE, ("chief", "cto", "ceo", "ceo", "founder", "vp of", "svp")),
    (SeniorityLevel.VP, ("vice president", "vp ", " vp", "vp,")),
    (SeniorityLevel.DIRECTOR, ("director", "head of")),
    (SeniorityLevel.MANAGER, ("manager", "mgr")),
    (SeniorityLevel.PRINCIPAL, ("principal",)),
    (SeniorityLevel.STAFF, ("staff",)),
    (SeniorityLevel.LEAD, ("lead", "technical lead", "tech lead")),
    (SeniorityLevel.SENIOR, ("senior", "sr.", "sr ", " sr")),
    (SeniorityLevel.JUNIOR, ("junior", "jr.", "jr ", " jr")),
    (SeniorityLevel.TRAINEE, ("trainee", "graduate", "apprentice")),
    (SeniorityLevel.INTERN, ("intern", "internship")),
    (SeniorityLevel.MID, ("mid-level", "mid level")),
)


def normalize_title(original: Optional[str]) -> tuple[Optional[str], list[str]]:
    """Return (normalized_job_title, warnings). Original is never mutated."""
    warnings: list[str] = []
    if not original or not original.strip():
        return (None, ["empty title"])
    text = f" {original.lower()} "
    for pattern, repl in _ABBREVIATIONS:
        text = re.sub(pattern, repl, text)
    normalized = title_case(clean_ws(text) or "")
    if len(normalized) < 2:
        warnings.append("job role uncertain")
    return (normalized or None, warnings)


def extract_seniority(original: Optional[str]) -> SeniorityLevel:
    """Extract stated seniority; UNKNOWN when the title does not indicate one."""
    if not original:
        return SeniorityLevel.UNKNOWN
    text = f" {original.lower()} "
    for level, cues in _SENIORITY_RULES:
        if any(c in text for c in cues):
            return level
    return SeniorityLevel.UNKNOWN
