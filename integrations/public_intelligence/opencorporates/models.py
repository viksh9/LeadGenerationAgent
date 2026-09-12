"""Typed OpenCorporates records (normalized, secret-free). Nothing is fabricated —
absent fields stay None."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OCAddress:
    line_1: Optional[str] = None
    line_2: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    in_full: Optional[str] = None

    def any(self) -> bool:
        return any((self.line_1, self.city, self.region, self.postal_code, self.country, self.in_full))


@dataclass
class OCOfficer:
    name: Optional[str] = None
    position: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@dataclass
class OCCompany:
    name: Optional[str] = None
    legal_name: Optional[str] = None
    company_number: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    company_type: Optional[str] = None
    current_status: Optional[str] = None
    inactive: Optional[bool] = None
    incorporation_date: Optional[str] = None
    dissolution_date: Optional[str] = None
    branch: Optional[str] = None
    registered_address: OCAddress = field(default_factory=OCAddress)
    registry_url: Optional[str] = None
    opencorporates_url: Optional[str] = None
    opencorporates_id: Optional[str] = None
    previous_names: list[str] = field(default_factory=list)
    industry_codes: list[str] = field(default_factory=list)
    officers: list[OCOfficer] = field(default_factory=list)
    # Underlying publisher provenance (§14), when OpenCorporates exposes it.
    publisher: Optional[str] = None
    publisher_url: Optional[str] = None
    publisher_retrieved_at: Optional[str] = None


@dataclass
class OCSearchResult:
    companies: list[OCCompany] = field(default_factory=list)
    total_count: Optional[int] = None
