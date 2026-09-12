"""Company Data Trust scoring (Prompt 46 → enhanced Prompt 47, §18/§21).

Evidence-based only — points are awarded ONLY when the corresponding evidence
actually exists; never assigned by default; 100 requires the full evidence set.

Company Data Trust (max 100):
    official company identity verified            +30
    official company website verified             +20
    official address verified                     +15
    government/registry evidence                  +15
    OpenCorporates legal-entity match             +10
    official career/ATS relationship               +5
    fresh retrieval                                +5
"""

from __future__ import annotations

IDENTITY_POINTS = 30
WEBSITE_POINTS = 20
ADDRESS_POINTS = 15
REGISTRY_POINTS = 15
OPENCORPORATES_POINTS = 10
CAREERS_POINTS = 5
FRESH_POINTS = 5

# Field-level trust for a value sourced from an official company page (§21).
FIELD_TRUST = {
    "website_url": 100,
    "company_identity": 100,
    "company_phone": 100,
    "company_email": 100,
    "linkedin_url": 100,
    "careers_url": 100,
    "contact_url": 100,
    "leadership_url": 100,
    "address": 95,
    # OpenCorporates-sourced legal fields (§19).
    "legal_name": 90,
    "company_number": 95,
    "registered_address": 85,
    "registry_url": 90,
    "opencorporates_url": 90,
}


def company_data_trust(*, identity_confirmed: bool, website_confirmed: bool = False,
                       address_confirmed: bool = False, registry_confirmed: bool = False,
                       opencorporates_match: bool = False, careers_confirmed: bool = False,
                       fresh: bool = False) -> int:
    score = 0
    if identity_confirmed:
        score += IDENTITY_POINTS
    if website_confirmed:
        score += WEBSITE_POINTS
    if address_confirmed:
        score += ADDRESS_POINTS
    if registry_confirmed:
        score += REGISTRY_POINTS
    if opencorporates_match:
        score += OPENCORPORATES_POINTS
    if careers_confirmed:
        score += CAREERS_POINTS
    if fresh:
        score += FRESH_POINTS
    return min(100, score)


def field_trust(field: str) -> int:
    return FIELD_TRUST.get(field, 90)
