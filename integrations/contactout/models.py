"""Typed ContactOut request/response models (normalized, secret-free).

These are the client's view of ContactOut data. Availability flags are kept
STRICTLY separate from actual contact values (§10): a `work_email_available=True`
never implies a fabricated address — the value is only ever the one ContactOut
actually returned. Personal email is captured but is never the primary business
contact (§11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContactAvailability:
    """What ContactOut says EXISTS for a person — not the values themselves."""

    work_email: bool = False
    personal_email: bool = False
    phone: bool = False


@dataclass
class ContactOutPerson:
    """A real person as returned by ContactOut. Every field is optional; nothing is
    invented. `linkedin_url` is stored verbatim (never modified/constructed)."""

    contactout_id: Optional[str] = None      # source_record_id (li vanity / profile id)
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    job_function: Optional[str] = None
    seniority: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    is_current: Optional[bool] = None

    # Availability (booleans) vs actual values — never conflated.
    availability: ContactAvailability = field(default_factory=ContactAvailability)
    work_email: Optional[str] = None
    work_email_verified: bool = False
    personal_email: Optional[str] = None
    phone: Optional[str] = None

    def best_business_email(self) -> Optional[str]:
        """Business outreach preference: work email only (never personal). §11."""
        return self.work_email or None


@dataclass
class PeopleResult:
    """A page of people (decision-makers or search results)."""

    people: list[ContactOutPerson] = field(default_factory=list)
    total: Optional[int] = None
    page: int = 1
    endpoint: str = ""

    @property
    def count(self) -> int:
        return len(self.people)
