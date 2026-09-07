"""Dependency-light text extraction helpers (technologies, roles, hiring counts).

Kept separate from `ingestion.normalizer` so collectors and the aggregator can
reuse extraction without importing `api.schemas` (which would pull the whole API
package and create an import cycle). Reuses the canonical technology aliases from
the signal detector — no duplicated data.
"""

from __future__ import annotations

import re
from typing import Optional

from intelligence.signal_detector import TECHNOLOGY_ALIASES

# Common IT hiring roles (canonical -> match aliases). Normalization only.
ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "Java Engineer": ("java engineer", "java developer"),
    "Backend Engineer": ("backend engineer", "back-end engineer", "backend developer"),
    "Frontend Engineer": ("frontend engineer", "front-end engineer", "frontend developer"),
    "React Developer": ("react developer", "react engineer"),
    "Python Developer": ("python developer", "python engineer"),
    "AWS Engineer": ("aws engineer",),
    "Cloud Engineer": ("cloud engineer",),
    "DevOps Engineer": ("devops engineer",),
    "QA Automation Engineer": ("qa automation engineer", "automation engineer", "qa engineer"),
    "SDET": ("sdet",),
    "Data Engineer": ("data engineer",),
    "ML Engineer": ("ml engineer", "machine learning engineer"),
    "Platform Engineer": ("platform engineer",),
    "Full Stack Engineer": ("full stack engineer", "fullstack engineer", "full-stack engineer"),
    "Software Engineer": ("software engineer", "software developer"),
}

_HIRING_NOUNS = r"(?:engineers|developers|professionals|specialists|hires|openings|positions|roles)"
# A count near a hiring noun ("30 Java, AWS engineers") or an explicit "hiring 30".
_HIRING_RE = re.compile(
    rf"(?:\bhiring\s+(\d{{1,4}})\b)|(\d{{1,4}})\s*\+?[\w,./&+\s-]{{0,40}}?{_HIRING_NOUNS}",
    re.IGNORECASE,
)


def _match_aliases(text: str, aliases: dict[str, tuple[str, ...]], *, allow_plural: bool = False) -> list[str]:
    lowered = text.lower()
    suffix = "s?" if allow_plural else ""
    found: list[str] = []
    for canonical, variants in aliases.items():
        for variant in variants:
            if re.search(rf"(?<![\w]){re.escape(variant)}{suffix}(?![\w])", lowered):
                found.append(canonical)
                break
    return found


def extract_technologies(text: str) -> list[str]:
    """Canonical technologies mentioned in `text` (reuses TECHNOLOGY_ALIASES)."""
    return _match_aliases(text, TECHNOLOGY_ALIASES)


def extract_roles(text: str) -> list[str]:
    """Canonical IT hiring roles mentioned in `text` (singular or plural)."""
    return _match_aliases(text, ROLE_ALIASES, allow_plural=True)


def extract_estimated_hiring(text: str) -> Optional[int]:
    """Largest explicit hiring count mentioned in `text` (or None)."""
    counts = [int(g) for match in _HIRING_RE.findall(text or "") for g in match if g]
    return max(counts) if counts else None
