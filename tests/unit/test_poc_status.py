"""POC Status derivation (Prompt 50, §7). Pure function over existing fields — no DB."""

from __future__ import annotations

from datetime import timedelta

from database.models import DecisionMaker, DataProvenance, VerificationStatus, utcnow
from intelligence.poc_status import derive_poc_status, is_stale

NOW = utcnow()


def _dm(**kw) -> DecisionMaker:
    d = DecisionMaker(company_id=1, full_name="Jane Doe", normalized_name="jane doe",
                      data_provenance=DataProvenance.REAL, last_seen_at=NOW, last_verified_at=NOW)
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def test_verified_requires_current_and_strong_verification():
    dm = _dm(employment_status="CURRENT_VERIFIED", verification_status=VerificationStatus.VERIFIED)
    assert derive_poc_status(dm, now=NOW) == "VERIFIED"


def test_verified_via_trust_status_and_current():
    dm = _dm(employment_status="CURRENT_LIKELY", contact_trust_status="VERIFIED",
             verification_status=VerificationStatus.PARTIALLY_VERIFIED)
    assert derive_poc_status(dm, now=NOW) == "VERIFIED"


def test_likely_partial():
    dm = _dm(employment_status="CURRENT_LIKELY", verification_status=VerificationStatus.PARTIALLY_VERIFIED)
    assert derive_poc_status(dm, now=NOW) == "LIKELY"


def test_former_from_employment_status():
    assert derive_poc_status(_dm(employment_status="FORMER"), now=NOW) == "FORMER"


def test_former_from_is_current_false():
    assert derive_poc_status(_dm(is_current=False), now=NOW) == "FORMER"


def test_stale_from_verification_status():
    dm = _dm(employment_status="CURRENT_VERIFIED", verification_status=VerificationStatus.STALE)
    assert derive_poc_status(dm, now=NOW) == "STALE"


def test_stale_from_old_last_verified():
    old = NOW - timedelta(days=400)
    dm = _dm(employment_status="CURRENT_LIKELY", verification_status=VerificationStatus.VERIFIED,
             last_verified_at=old, last_seen_at=old)
    assert derive_poc_status(dm, now=NOW) == "STALE"


def test_former_takes_precedence_over_stale():
    old = NOW - timedelta(days=400)
    dm = _dm(is_current=False, verification_status=VerificationStatus.STALE, last_verified_at=old)
    assert derive_poc_status(dm, now=NOW) == "FORMER"


def test_unverified_default():
    dm = _dm(employment_status="UNKNOWN", verification_status=VerificationStatus.UNVERIFIED)
    assert derive_poc_status(dm, now=NOW) == "UNVERIFIED"


def test_no_person_is_recommended_role_only():
    assert derive_poc_status(None) == "RECOMMENDED_ROLE_ONLY"
    assert derive_poc_status(_dm(full_name=None)) == "RECOMMENDED_ROLE_ONLY"


def test_is_stale_never_guesses_without_a_timestamp():
    dm = _dm(verification_status=VerificationStatus.UNVERIFIED, last_verified_at=None, last_seen_at=None)
    assert is_stale(dm, now=NOW) is False
