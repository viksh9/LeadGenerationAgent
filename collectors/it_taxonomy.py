"""Centralized IT taxonomy shared across collectors.

Single home for the IT role list and the high/low relevance term sets so
collectors don't each maintain their own copy. Technology detection itself is
NOT duplicated here — collectors reuse `ingestion.normalizer.extract_technologies`
(backed by `intelligence.signal_detector.TECHNOLOGY_ALIASES`).
"""

from __future__ import annotations

import re

# Canonical IT roles this system optimizes collection for (§10). Kept as display
# strings; role *detection* in free text reuses ROLE_ALIASES in the normalizer.
IT_ROLES: tuple[str, ...] = (
    "Software Engineer", "Software Developer", "Backend Engineer", "Frontend Engineer",
    "Full Stack Engineer", "Java Developer", "Python Developer", ".NET Developer",
    "React Developer", "Angular Developer", "Node.js Developer", "AWS Engineer",
    "Azure Engineer", "Cloud Engineer", "DevOps Engineer", "SRE", "Platform Engineer",
    "Kubernetes Engineer", "Data Engineer", "Data Scientist", "Machine Learning Engineer",
    "AI Engineer", "QA Automation Engineer", "SDET", "Automation Engineer",
    "Technical Lead", "Engineering Manager", "Software Architect", "Solutions Architect",
)

# High-relevance IT signal terms (collection optimization only — the Signal
# Detection Engine remains the authority for business-signal classification).
HIGH_RELEVANCE_TERMS: tuple[str, ...] = (
    "software", "developer", "engineer", "cloud", "aws", "azure", "gcp", "devops",
    "java", "python", "javascript", "typescript", "react", "angular", "node",
    ".net", "c#", "kubernetes", "docker", "qa", "sdet", "automation", "data",
    "ai", "artificial intelligence", "machine learning", "ml", "technology",
    "technical", "backend", "frontend", "full stack", "sre", "platform", "architect",
)

# Clearly non-IT terms. Used only to tag obvious non-technical roles; borderline
# records are never discarded (§30) — they are retained and marked UNKNOWN.
LOW_RELEVANCE_TERMS: tuple[str, ...] = (
    "office administration", "administrative assistant", "receptionist", "front desk",
    "driver", "security guard", "facilities", "housekeeping", "janitor", "cleaner",
    "chef", "cook", "waiter", "waitress", "barista", "cashier", "retail associate",
    "warehouse", "delivery", "gardener", "plumber", "electrician",
)

# Three-way relevance labels stored on the raw payload.
RELEVANT = "RELEVANT"
NOT_RELEVANT = "NOT_RELEVANT"
UNKNOWN = "UNKNOWN"


def _word_matcher(terms: tuple[str, ...]) -> re.Pattern:
    """Word-boundary matcher for single alnum tokens; substrings for the rest.

    Prevents short terms ("ai", "ml") from matching inside unrelated words
    ("waiter") while still matching compound terms ("full stack") as substrings.
    """
    word = [t for t in terms if t.isalnum() and " " not in t]
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in word) + r")\b") if word else re.compile(r"(?!x)x")


_HIGH_WORD_RE = _word_matcher(HIGH_RELEVANCE_TERMS)
_HIGH_SUBSTR = tuple(t for t in HIGH_RELEVANCE_TERMS if not (t.isalnum() and " " not in t))
_LOW_WORD_RE = _word_matcher(LOW_RELEVANCE_TERMS)
_LOW_SUBSTR = tuple(t for t in LOW_RELEVANCE_TERMS if not (t.isalnum() and " " not in t))


def _matches(text: str, word_re: re.Pattern, substrings: tuple[str, ...]) -> bool:
    return bool(word_re.search(text)) or any(s in text for s in substrings)


def classify_it_relevance(*parts: str | None) -> str:
    """Classify text as RELEVANT / NOT_RELEVANT / UNKNOWN (§30).

    High-relevance wins outright. An obvious non-IT term with no IT term present
    is NOT_RELEVANT. Everything else is UNKNOWN — retained, never dropped.
    """
    text = " ".join(p for p in parts if p).lower()
    if not text.strip():
        return UNKNOWN
    if _matches(text, _HIGH_WORD_RE, _HIGH_SUBSTR):
        return RELEVANT
    if _matches(text, _LOW_WORD_RE, _LOW_SUBSTR):
        return NOT_RELEVANT
    return UNKNOWN
