"""Company name + domain normalization (for matching, never display).

Original source names are preserved by the caller. Reuses the shared
normalize_company_name (legal-suffix stripping) and domain normalization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from collectors.raw_record import normalize_company_name
from processors.normalization.company_normalizer import normalize_domain  # noqa: F401 (re-export)
from processors.normalization.text import normalize_for_compare

# Legal suffix tokens removed when producing the suffix-removed comparison name.
_LEGAL_SUFFIXES = (
    "pvt", "ltd", "private", "limited", "llp", "inc", "incorporated", "corp",
    "corporation", "llc", "plc", "gmbh", "co", "company",
)
_DESCRIPTORS = ("technologies", "technology", "solutions", "services", "systems", "labs", "india")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class NormalizedCompanyName:
    original_name: Optional[str]
    normalized_name: str                 # comparison key (lowercase, de-suffixed)
    comparison_name: str                 # same as normalized_name (explicit alias)
    legal_suffix_removed_name: str
    tokens: list[str] = field(default_factory=list)
    descriptor_tokens: list[str] = field(default_factory=list)  # tech/solutions/... (weak signal)


def normalize_name(original: Optional[str]) -> NormalizedCompanyName:
    normalized = normalize_company_name(original) or ""
    base = normalize_for_compare(original)
    # Suffix-removed: drop legal suffix tokens only (keeps meaningful words).
    tokens_all = _TOKEN_RE.findall(base)
    suffix_removed = " ".join(t for t in tokens_all if t not in _LEGAL_SUFFIXES).strip()
    core_tokens = [t for t in _TOKEN_RE.findall(normalized) if t not in _LEGAL_SUFFIXES]
    descriptors = [t for t in core_tokens if t in _DESCRIPTORS]
    distinctive = [t for t in core_tokens if t not in _DESCRIPTORS]
    return NormalizedCompanyName(
        original_name=original,
        normalized_name=normalized,
        comparison_name=normalized,
        legal_suffix_removed_name=suffix_removed or normalized,
        tokens=distinctive or core_tokens,
        descriptor_tokens=descriptors,
    )
