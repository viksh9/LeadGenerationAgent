"""Location normalization: original text -> {country, state, city, remote_type}.

Preserves the original location string and only derives structured fields it can
support from evidence. Ambiguous input is left as UNKNOWN / null rather than
guessed. Backed by the configurable India city map in config.locations_in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from config.locations_in import (
    CITY_STATE,
    HYBRID_KEYWORDS,
    INDIA_KEYWORDS,
    INDIAN_CITY_ALIASES,
    ONSITE_KEYWORDS,
    REMOTE_KEYWORDS,
)
from database.models import RemoteType

# Precompile alias -> canonical, longest-first so "new delhi" beats "delhi".
_ALIAS_TO_CITY: list[tuple[re.Pattern, str]] = sorted(
    (
        (re.compile(rf"(?<![a-z]){re.escape(alias)}(?![a-z])"), city)
        for city, aliases in INDIAN_CITY_ALIASES.items()
        for alias in aliases
    ),
    key=lambda t: -len(t[0].pattern),
)


@dataclass
class NormalizedLocation:
    original: Optional[str]
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    remote_type: RemoteType = RemoteType.UNKNOWN


def _remote_type(text: str) -> RemoteType:
    if any(k in text for k in HYBRID_KEYWORDS):
        return RemoteType.HYBRID
    if any(k in text for k in REMOTE_KEYWORDS):
        return RemoteType.REMOTE
    if any(k in text for k in ONSITE_KEYWORDS):
        return RemoteType.ONSITE
    return RemoteType.UNKNOWN


def _match_city(text: str) -> Optional[str]:
    for pattern, city in _ALIAS_TO_CITY:
        if pattern.search(text):
            return city
    return None


def normalize_location(original: Optional[str]) -> NormalizedLocation:
    if not original or not original.strip():
        return NormalizedLocation(original=original)
    text = original.lower()
    remote = _remote_type(text)
    city = _match_city(text)
    state = CITY_STATE.get(city) if city else None
    country: Optional[str] = None
    if city or any(k in text for k in INDIA_KEYWORDS):
        country = "India"
    elif remote is RemoteType.REMOTE and "india" in text:
        country = "India"
    return NormalizedLocation(
        original=original, country=country, state=state, city=city, remote_type=remote
    )
