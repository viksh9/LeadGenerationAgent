"""Company Data Trust scoring for official-company intelligence (Prompt 46, §20/§21).

Points are awarded ONLY when the corresponding evidence actually exists — never
assigned by default, and never reaching 100 unless every criterion is met.

Company Data Trust (max 100):
    official website confirms identity            +30
    official contact page confirms address        +25
    official page confirms phone/email             +15
    official social/LinkedIn confirms identity     +10
    official careers/ATS relation                  +10
    fresh retrieval                                +10
"""

from __future__ import annotations

IDENTITY_POINTS = 30
ADDRESS_POINTS = 25
CONTACT_POINTS = 15
LINKEDIN_POINTS = 10
CAREERS_POINTS = 10
FRESH_POINTS = 10

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
}


def company_data_trust(*, identity_confirmed: bool, address_confirmed: bool,
                       contact_confirmed: bool, linkedin_confirmed: bool,
                       careers_confirmed: bool, fresh: bool) -> int:
    score = 0
    if identity_confirmed:
        score += IDENTITY_POINTS
    if address_confirmed:
        score += ADDRESS_POINTS
    if contact_confirmed:
        score += CONTACT_POINTS
    if linkedin_confirmed:
        score += LINKEDIN_POINTS
    if careers_confirmed:
        score += CAREERS_POINTS
    if fresh:
        score += FRESH_POINTS
    return min(100, score)


def field_trust(field: str) -> int:
    return FIELD_TRUST.get(field, 90)
