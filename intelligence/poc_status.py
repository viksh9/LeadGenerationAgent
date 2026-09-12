"""POC Status derivation (Prompt 50, §7 / §27).

A single deterministic function that maps a persisted ``DecisionMaker``'s EXISTING
evidence fields to one of the six POC statuses. It is computed at read time (no new
column, no stored duplicate) so there is exactly one source of truth and no drift
between the API, the export, and the UI.

    VERIFIED               real person, current company + title, strong evidence
    LIKELY                 real person, partial verification
    STALE                  real person but the evidence is old / marked stale
    FORMER                 evidence says the person no longer holds the role
    UNVERIFIED             real person, no corroborating verification
    RECOMMENDED_ROLE_ONLY  no real person at all (handled by callers, see helper)

Nothing here fabricates: every branch reads only fields the collectors actually set
(employment_status, verification_status, contact_trust_status, is_current,
last_verified_at). Staleness reuses the existing verification STALE marker plus a
``last_verified_at`` age window (defaulting to the official-company data TTL) rather
than inventing a new threshold.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from config import get_settings
from database.models import DecisionMaker, VerificationStatus, utcnow
from integrations.public_intelligence.models import (
    STATUS_FORMER,
    STATUS_LIKELY,
    STATUS_RECOMMENDED_ROLE_ONLY,
    STATUS_STALE,
    STATUS_UNVERIFIED,
    STATUS_VERIFIED,
)

# Statuses that mean "no longer current" — evidence explicitly says former.
_FORMER_EMPLOYMENT = {"FORMER"}
_CURRENT_VERIFIED = "CURRENT_VERIFIED"
_CURRENT_LIKELY = "CURRENT_LIKELY"


def _enum_value(v) -> Optional[str]:
    return v.value if hasattr(v, "value") else v


def poc_stale_after_days() -> int:
    """Age (days) beyond which a POC's evidence is considered STALE. Reuses the
    official-company data TTL so freshness policy stays in one place."""
    return max(1, int(get_settings().official_company_data_ttl_days))


def is_stale(dm: DecisionMaker, *, now: Optional[datetime] = None,
             stale_after_days: Optional[int] = None) -> bool:
    """A POC is stale when the verification engine marked it STALE, or its last
    verification is older than the freshness window. Never guesses — if there is no
    ``last_verified_at`` we do not assert staleness on age alone."""
    if _enum_value(dm.verification_status) == VerificationStatus.STALE.value:
        return True
    now = now or utcnow()
    days = stale_after_days if stale_after_days is not None else poc_stale_after_days()
    lv = dm.last_verified_at or dm.last_seen_at
    if lv is not None and lv < now - timedelta(days=days):
        return True
    return False


def derive_poc_status(dm: Optional[DecisionMaker], *, now: Optional[datetime] = None,
                      stale_after_days: Optional[int] = None) -> str:
    """Map a real POC to its status. ``None`` (no person) -> RECOMMENDED_ROLE_ONLY."""
    if dm is None or not (dm.full_name and dm.full_name.strip()):
        return STATUS_RECOMMENDED_ROLE_ONLY

    employment = (dm.employment_status or "").upper()
    if employment in _FORMER_EMPLOYMENT or dm.is_current is False:
        return STATUS_FORMER

    if is_stale(dm, now=now, stale_after_days=stale_after_days):
        return STATUS_STALE

    verification = _enum_value(dm.verification_status)
    trust_status = (dm.contact_trust_status or "").upper()

    # VERIFIED requires current employment confirmation AND strong verification.
    if employment == _CURRENT_VERIFIED and verification == VerificationStatus.VERIFIED.value:
        return STATUS_VERIFIED
    if trust_status == "VERIFIED" and employment in (_CURRENT_VERIFIED, _CURRENT_LIKELY):
        return STATUS_VERIFIED

    if (verification in (VerificationStatus.VERIFIED.value, VerificationStatus.PARTIALLY_VERIFIED.value)
            or trust_status == "LIKELY" or employment in (_CURRENT_VERIFIED, _CURRENT_LIKELY)):
        return STATUS_LIKELY

    return STATUS_UNVERIFIED
