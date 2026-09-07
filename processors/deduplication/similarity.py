"""Deterministic text-similarity utilities for job matching.

Token Jaccard + boilerplate reduction. No LLM, no network. Original descriptions
are never modified — a derived comparison representation is built on copies.
"""

from __future__ import annotations

import re
from typing import Optional

from processors.normalization.text import normalize_for_compare

_WORD_RE = re.compile(r"[a-z0-9.#+]+")

# Common recruiting boilerplate reduced before comparison (not deleted from source).
_BOILERPLATE = (
    "equal opportunity employer", "about the company", "about us", "apply now",
    "we are an equal", "diversity and inclusion", "click here to apply",
    "roles and responsibilities", "what you will do", "what we offer",
    "benefits", "perks", "job description", "note:", "disclaimer",
)

_STOPWORDS = frozenset(
    "a an the and or of to for with in on at is are be as you your we our will "
    "this that role job work team years experience strong good using".split()
)


def tokenize(text: Optional[str]) -> set[str]:
    if not text:
        return set()
    cleaned = normalize_for_compare(text)
    for phrase in _BOILERPLATE:
        cleaned = cleaned.replace(phrase, " ")
    return {w for w in _WORD_RE.findall(cleaned) if w not in _STOPWORDS and len(w) > 1}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def title_similarity(a: Optional[str], b: Optional[str]) -> float:
    """Token Jaccard over normalized titles."""
    return jaccard(tokenize(a), tokenize(b))


def description_similarity(a: Optional[str], b: Optional[str]) -> float:
    """Boilerplate-reduced token Jaccard over descriptions (0..1)."""
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    return jaccard(ta, tb)


def title_tail(title: Optional[str]) -> Optional[str]:
    """The distinguishing tail after a dash/pipe (e.g. '- Payments Platform').
    Two jobs whose tails clearly differ are likely different roles (§7, §39)."""
    if not title:
        return None
    parts = re.split(r"\s[-–|]\s", title, maxsplit=1)
    if len(parts) < 2:
        return None
    return normalize_for_compare(parts[1]) or None
