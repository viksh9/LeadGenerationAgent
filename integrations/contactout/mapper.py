"""Map raw ContactOut JSON into typed, normalized models.

Defensive by design: ContactOut response shapes differ by plan/version, so we read
several documented key spellings and tolerate list-or-scalar values. We NEVER invent
a value that is absent — a missing email/phone/LinkedIn stays None, and availability
booleans are derived only from what ContactOut actually returned.
"""

from __future__ import annotations

from typing import Any, Optional

from integrations.contactout.models import ContactAvailability, ContactOutPerson, PeopleResult


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _first_str(value: Any) -> Optional[str]:
    for item in _as_list(value):
        if isinstance(item, dict):
            item = item.get("email") or item.get("value") or item.get("number") or item.get("address")
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _get(raw: dict, *keys: str) -> Any:
    for k in keys:
        if k in raw and raw[k] not in (None, "", [], {}):
            return raw[k]
    return None


def _is_verified_email(raw: dict) -> bool:
    status = (_get(raw, "work_email_status", "email_status", "verification") or "")
    return str(status).lower() in {"verified", "valid", "safe", "deliverable"}


def parse_person(raw: dict) -> ContactOutPerson:
    """Parse one ContactOut profile object into a ContactOutPerson (nothing invented)."""
    if not isinstance(raw, dict):
        return ContactOutPerson()

    work_email = _first_str(_get(raw, "work_email", "work_emails", "business_email"))
    personal_email = _first_str(_get(raw, "personal_email", "personal_emails"))
    # A generic `email`/`emails` field is treated as work email only if no explicit
    # work email was provided — never promoted over a personal-labelled address.
    if not work_email and not personal_email:
        work_email = _first_str(_get(raw, "email", "emails"))
    phone = _first_str(_get(raw, "phone", "phones", "phone_number", "mobile"))

    company = _get(raw, "company", "company_name", "current_company")
    if isinstance(company, dict):
        company_name = company.get("name")
        company_domain = company.get("domain") or company.get("website")
    else:
        company_name = company
        company_domain = _get(raw, "company_domain", "domain", "website")

    linkedin = _get(raw, "linkedin_url", "linkedin", "li_vanity", "profile_url", "url")
    if isinstance(linkedin, list):
        linkedin = _first_str(linkedin)

    # Availability: explicit flags if present, else derived from actual values.
    avail_raw = _get(raw, "contact_availability", "availability") or {}
    availability = ContactAvailability(
        work_email=bool(avail_raw.get("work_email")) if isinstance(avail_raw, dict) else False,
        personal_email=bool(avail_raw.get("personal_email")) if isinstance(avail_raw, dict) else False,
        phone=bool(avail_raw.get("phone")) if isinstance(avail_raw, dict) else False,
    )
    availability.work_email = availability.work_email or bool(work_email)
    availability.personal_email = availability.personal_email or bool(personal_email)
    availability.phone = availability.phone or bool(phone)

    is_current = raw.get("is_current")
    if is_current is None:
        is_current = raw.get("current")

    return ContactOutPerson(
        contactout_id=_first_str(_get(raw, "id", "profile_id", "li_vanity")) or (str(linkedin) if linkedin else None),
        full_name=_get(raw, "full_name", "name"),
        first_name=_get(raw, "first_name"),
        last_name=_get(raw, "last_name"),
        job_title=_get(raw, "job_title", "title", "headline", "current_title"),
        job_function=_get(raw, "job_function", "function"),
        seniority=_get(raw, "seniority", "seniority_level"),
        company_name=company_name,
        company_domain=company_domain,
        linkedin_url=linkedin if isinstance(linkedin, str) else None,
        location=_get(raw, "location", "city", "region"),
        is_current=bool(is_current) if is_current is not None else None,
        availability=availability,
        work_email=work_email,
        work_email_verified=_is_verified_email(raw) if work_email else False,
        personal_email=personal_email,
        phone=phone,
    )


def _profiles_from(raw: dict) -> list[dict]:
    """Extract the profile list from the several documented envelope shapes."""
    for key in ("profiles", "people", "results", "data", "decision_makers"):
        val = raw.get(key)
        if isinstance(val, list):
            return [p for p in val if isinstance(p, dict)]
        if isinstance(val, dict):  # some endpoints key profiles by id
            return [p for p in val.values() if isinstance(p, dict)]
    return []


def parse_people(raw: dict, *, endpoint: str, page: int = 1) -> PeopleResult:
    if not isinstance(raw, dict):
        return PeopleResult(endpoint=endpoint, page=page)
    profiles = _profiles_from(raw)
    total = raw.get("total") or raw.get("total_results") or raw.get("count")
    return PeopleResult(
        people=[parse_person(p) for p in profiles],
        total=int(total) if isinstance(total, (int, float)) else None,
        page=page, endpoint=endpoint,
    )


def parse_enrich(raw: dict) -> Optional[ContactOutPerson]:
    """Parse an enrich response. Returns None when ContactOut returns no profile."""
    if not isinstance(raw, dict):
        return None
    profile = raw.get("profile") or raw.get("person") or raw.get("data")
    if isinstance(profile, list):
        profile = profile[0] if profile else None
    if not isinstance(profile, dict):
        # Some plans return the fields at the top level.
        if any(k in raw for k in ("full_name", "name", "work_email", "linkedin_url", "linkedin")):
            profile = raw
        else:
            return None
    person = parse_person(profile)
    return person if (person.full_name or person.linkedin_url or person.work_email) else None
