"""URL / address / location normalization for official-company facts (Prompt 46).

Normalization never invents data — it only canonicalizes values a source actually
provided (§8/§25). City canonicalization reuses the app's existing Indian geo map;
unknown cities are passed through unchanged (never guessed).
"""

from __future__ import annotations

import re
from typing import Optional

from config.locations_in import CITY_STATE, INDIAN_CITY_ALIASES

# alias (lowercased) -> canonical city
_ALIAS_TO_CITY = {alias: city for city, aliases in INDIAN_CITY_ALIASES.items() for alias in aliases}


def normalize_url(url: Optional[str]) -> Optional[str]:
    """Canonical https URL: force https for bare/http hosts, lowercase host, strip a
    trailing slash. Returns None for empty/invalid input (never fabricates)."""
    if not url or not str(url).strip():
        return None
    u = str(url).strip()
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u.lstrip("/")
    u = re.sub(r"^http://", "https://", u, flags=re.I)
    m = re.match(r"^(https://)([^/]+)(.*)$", u, re.I)
    if not m:
        return u
    scheme, host, rest = m.groups()
    host = host.lower()
    rest = rest.rstrip("/") if rest and rest != "/" else ""
    return f"{scheme}{host}{rest}"


def canonical_city(city: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(canonical_city, state_or_None) using the app's geo map. Unknown cities pass
    through unchanged; state is only added when the map knows it."""
    if not city or not city.strip():
        return None, None
    key = city.strip().lower()
    canonical = _ALIAS_TO_CITY.get(key, city.strip())
    return canonical, CITY_STATE.get(canonical)


def build_full_address(*, line1=None, line2=None, city=None, state=None,
                       postal=None, country=None) -> Optional[str]:
    """Join only the components that are actually present."""
    parts = [p.strip() for p in (line1, line2, city, state, postal, country) if p and str(p).strip()]
    return ", ".join(parts) or None


def location_key(*, line1=None, city=None, postal=None, country=None) -> str:
    """Stable dedup key for a location (line1 + city + postal + country)."""
    raw = "|".join((line1 or "", city or "", postal or "", country or "")).lower()
    return re.sub(r"\s+", " ", raw).strip()
