"""Location normalization (India-first). Reuses the configurable city map in
config.locations_in via ingestion.location, adds region, and preserves original.
Unknown locations stay UNKNOWN rather than being wrongly mapped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database.models import RemoteType
from ingestion.location import normalize_location as _base_normalize

# State/UT -> broad Indian region (configurable).
_STATE_REGION: dict[str, str] = {
    "Karnataka": "South India", "Tamil Nadu": "South India", "Telangana": "South India",
    "Kerala": "South India", "Andhra Pradesh": "South India",
    "Maharashtra": "West India", "Gujarat": "West India",
    "Delhi": "North India", "Haryana": "North India", "Uttar Pradesh": "North India",
    "Rajasthan": "North India", "Chandigarh": "North India", "Punjab": "North India",
    "West Bengal": "East India", "Odisha": "East India",
    "Madhya Pradesh": "Central India",
}


@dataclass
class NormalizedLocation:
    original_location: Optional[str]
    normalized_city: Optional[str] = None
    normalized_state: Optional[str] = None
    normalized_country: Optional[str] = None
    normalized_region: Optional[str] = None
    remote_type: RemoteType = RemoteType.UNKNOWN
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def normalize_location(original: Optional[str]) -> NormalizedLocation:
    base = _base_normalize(original)
    warnings: list[str] = []
    if original and original.strip() and base.city is None and base.remote_type is RemoteType.UNKNOWN:
        warnings.append("Location could not be mapped to a known Indian city")
    return NormalizedLocation(
        original_location=original,
        normalized_city=base.city,
        normalized_state=base.state,
        normalized_country=base.country,
        normalized_region=_STATE_REGION.get(base.state) if base.state else None,
        remote_type=base.remote_type,
        warnings=warnings,
    )
