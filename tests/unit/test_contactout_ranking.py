"""ContactOut POC ranking, company-match validation, and contact trust (Prompt 44).

Pure/offline. Verifies the deterministic precedence, that a person is never matched
on name-alone / past roles, work-email priority, phone handling, and that trust is
honest (VERIFIED only with the evidence; NO_CONTACT_DATA when there is none)."""

from __future__ import annotations

from integrations.contactout.models import ContactAvailability, ContactOutPerson
from integrations.contactout.ranking import (
    TRUST_LIKELY,
    TRUST_NO_CONTACT_DATA,
    TRUST_UNVERIFIED,
    TRUST_VERIFIED,
    rank_person,
    validate_company_match,
)

ROLES = ["VP Engineering", "Head of Engineering", "Engineering Director", "Head of Talent Acquisition"]


def _person(**kw) -> ContactOutPerson:
    kw.setdefault("availability", ContactAvailability(
        work_email=bool(kw.get("work_email")), phone=bool(kw.get("phone"))))
    return ContactOutPerson(**kw)


def test_domain_match_is_strong():
    m, conf, _ = validate_company_match(_person(company_domain="acme.com"), target_name="Acme", target_domain="acme.com")
    assert m and conf == 100


def test_name_alone_never_matches_wrong_company():
    m, conf, _ = validate_company_match(
        _person(company_name="Globex", company_domain="globex.com"),
        target_name="Acme Corp", target_domain="acme.com")
    assert not m and conf == 0


def test_past_role_never_matches():
    m, _, reason = validate_company_match(
        _person(company_domain="acme.com", is_current=False), target_name="Acme", target_domain="acme.com")
    assert not m and "past role" in reason.lower()


def test_verified_poc_full_signal():
    p = _person(full_name="Jane Doe", job_title="VP Engineering", company_domain="acme.com",
                work_email="jane@acme.com", work_email_verified=True, phone="+91-1",
                linkedin_url="https://linkedin.com/in/jane", is_current=True)
    r = rank_person(p, target_name="Acme", target_domain="acme.com", recommended_roles=ROLES)
    assert r.company_matched and r.trust_status == TRUST_VERIFIED and r.match_score >= 90


def test_matched_but_unverified_email_is_likely():
    p = _person(full_name="Sam", job_title="Head of Engineering", company_domain="acme.com",
                work_email="sam@acme.com", work_email_verified=False, is_current=True)
    r = rank_person(p, target_name="Acme", target_domain="acme.com", recommended_roles=ROLES)
    assert r.company_matched and r.trust_status == TRUST_LIKELY


def test_no_contact_data_status():
    p = _person(full_name="Nolan", job_title="CTO", company_domain="acme.com", is_current=True)
    r = rank_person(p, target_name="Acme", target_domain="acme.com", recommended_roles=ROLES)
    assert r.trust_status == TRUST_NO_CONTACT_DATA and r.availability_score == 0


def test_wrong_company_unverified_low_score():
    p = _person(full_name="Bob", job_title="VP Engineering", company_domain="globex.com",
                work_email="bob@globex.com", is_current=True)
    r = rank_person(p, target_name="Acme", target_domain="acme.com", recommended_roles=ROLES)
    assert not r.company_matched and r.trust_status == TRUST_UNVERIFIED


def test_precedence_company_dominates_title():
    # Same title; the one whose company matches must outrank the one whose does not.
    match = _person(full_name="A", job_title="VP Engineering", company_domain="acme.com", is_current=True,
                    work_email="a@acme.com")
    nomatch = _person(full_name="B", job_title="VP Engineering", company_domain="globex.com", is_current=True,
                      work_email="b@globex.com")
    rm = rank_person(match, target_name="Acme", target_domain="acme.com", recommended_roles=ROLES)
    rn = rank_person(nomatch, target_name="Acme", target_domain="acme.com", recommended_roles=ROLES)
    assert rm.match_score > rn.match_score
