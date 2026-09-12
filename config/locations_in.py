"""Configurable India location mapping for job-location normalization.

Canonical cities + common aliases (e.g. "Bangalore" -> Bengaluru, "Gurgaon" ->
Gurugram). Kept as configuration so the mapping can grow without touching the
normalizer. Ambiguous input is left un-transformed rather than guessed.
"""

from __future__ import annotations

# Canonical city -> lowercase alias phrases that map to it.
INDIAN_CITY_ALIASES: dict[str, tuple[str, ...]] = {
    "Bengaluru": ("bengaluru", "bangalore", "bengalooru", "bangaluru"),
    "Hyderabad": ("hyderabad", "hitec city", "hi-tec city", "secunderabad", "gachibowli"),
    "Pune": ("pune", "hinjewadi", "hinjawadi"),
    "Chennai": ("chennai", "madras"),
    "Mumbai": ("mumbai", "bombay", "navi mumbai", "powai"),
    "Delhi": ("new delhi", "delhi ncr", "delhi-ncr", "delhi"),
    "Gurugram": ("gurugram", "gurgaon"),
    "Noida": ("noida", "greater noida"),
    "Kolkata": ("kolkata", "calcutta"),
    "Ahmedabad": ("ahmedabad",),
    "Kochi": ("kochi", "cochin", "ernakulam"),
    "Coimbatore": ("coimbatore",),
    "Chandigarh": ("chandigarh", "mohali"),
    "Jaipur": ("jaipur",),
    "Indore": ("indore",),
    "Thiruvananthapuram": ("thiruvananthapuram", "trivandrum"),
    "Nagpur": ("nagpur",),
    "Bhubaneswar": ("bhubaneswar", "bhubaneshwar"),
    "Vadodara": ("vadodara", "baroda"),
    "Visakhapatnam": ("visakhapatnam", "vizag"),
}

# Canonical city -> state/UT.
CITY_STATE: dict[str, str] = {
    "Bengaluru": "Karnataka",
    "Hyderabad": "Telangana",
    "Pune": "Maharashtra",
    "Chennai": "Tamil Nadu",
    "Mumbai": "Maharashtra",
    "Delhi": "Delhi",
    "Gurugram": "Haryana",
    "Noida": "Uttar Pradesh",
    "Kolkata": "West Bengal",
    "Ahmedabad": "Gujarat",
    "Kochi": "Kerala",
    "Coimbatore": "Tamil Nadu",
    "Chandigarh": "Chandigarh",
    "Jaipur": "Rajasthan",
    "Indore": "Madhya Pradesh",
    "Thiruvananthapuram": "Kerala",
    "Nagpur": "Maharashtra",
    "Bhubaneswar": "Odisha",
    "Vadodara": "Gujarat",
    "Visakhapatnam": "Andhra Pradesh",
}

INDIA_KEYWORDS: tuple[str, ...] = ("india", "bharat", ", in", "(in)")

# Flattened city aliases for fast India-location detection.
_ALL_CITY_ALIASES: tuple[str, ...] = tuple(
    alias for aliases in INDIAN_CITY_ALIASES.values() for alias in aliases
)


def is_india_location(text: str | None) -> bool:
    """True when a free-text job location is in India — matches the country/region
    keyword ('india'/'bharat') or a known Indian city alias. Conservative: unknown or
    empty locations are NOT treated as India (never guessed)."""
    if not text:
        return False
    t = text.lower()
    if "india" in t or "bharat" in t:
        return True
    return any(alias in t for alias in _ALL_CITY_ALIASES)
REMOTE_KEYWORDS: tuple[str, ...] = ("remote", "work from home", "wfh", "anywhere")
HYBRID_KEYWORDS: tuple[str, ...] = ("hybrid",)
ONSITE_KEYWORDS: tuple[str, ...] = ("on-site", "onsite", "on site", "in office", "in-office", "work from office")
