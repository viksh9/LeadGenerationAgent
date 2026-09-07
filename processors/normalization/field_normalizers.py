"""Employment type, experience, salary, source name, and URL normalization.

All conservative: periods/currencies are only set when the source is explicit,
and nothing is fabricated. Originals are preserved by the caller.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from processors.normalization.text import normalize_for_compare


class EmploymentType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERNSHIP = "INTERNSHIP"
    FREELANCE = "FREELANCE"
    UNKNOWN = "UNKNOWN"


_EMPLOYMENT_RULES: tuple[tuple[EmploymentType, tuple[str, ...]], ...] = (
    (EmploymentType.INTERNSHIP, ("intern", "internship")),
    (EmploymentType.FREELANCE, ("freelance", "freelancer")),
    (EmploymentType.CONTRACT, ("contract", "contractor", "contractual", "c2h", "temporary", "temp")),
    (EmploymentType.PART_TIME, ("part-time", "part time", "part_time")),
    (EmploymentType.FULL_TIME, ("full-time", "full time", "fulltime", "full_time", "permanent", "regular")),
)


def normalize_employment_type(original: Optional[str]) -> EmploymentType:
    if not original:
        return EmploymentType.UNKNOWN
    text = f" {normalize_for_compare(original)} "
    for etype, cues in _EMPLOYMENT_RULES:
        if any(c in text for c in cues):
            return etype
    return EmploymentType.UNKNOWN


_EXP_RANGE = re.compile(r"(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s*(?:\+?\s*)?year", re.IGNORECASE)
_EXP_MIN = re.compile(r"(\d{1,2})\s*\+\s*year", re.IGNORECASE)
_EXP_SINGLE = re.compile(r"(?:minimum|min\.?|at least)\s*(\d{1,2})\s*year", re.IGNORECASE)


def normalize_experience(text: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """Return (min_years, max_years). Never invents years."""
    if not text:
        return (None, None)
    m = _EXP_RANGE.search(text)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = _EXP_MIN.search(text)
    if m:
        return (int(m.group(1)), None)
    m = _EXP_SINGLE.search(text)
    if m:
        return (int(m.group(1)), None)
    return (None, None)


_SALARY_TOKEN = re.compile(
    r"(₹|rs\.?|inr|\$|usd)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(lpa|lakhs?|lac|k|cr|crore)?",
    re.IGNORECASE,
)
_ANNUAL_MARKERS = ("lpa", "per annum", " pa", "/year", "/yr", "annually", "annum")
_LAKH = 100_000


def normalize_salary(text: Optional[str]) -> tuple[Optional[float], Optional[float], Optional[str], Optional[str], list[str]]:
    """Return (min, max, currency, period, warnings). Only what the source states."""
    warnings: list[str] = []
    if not text or not text.strip():
        return (None, None, None, None, warnings)
    low = text.lower()
    currency = "INR" if any(c in low for c in ("₹", "rs", "inr", "lpa", "lakh")) else ("USD" if "$" in text or "usd" in low else None)
    period = "ANNUAL" if any(m in low for m in _ANNUAL_MARKERS) else None
    # A unit stated once ("12-18 LPA") applies to bare numbers in the same text.
    context_mult = _LAKH if any(m in low for m in ("lpa", "lakh", "lac")) else (1e7 if "crore" in low or " cr" in low else None)
    unit_mult = {"lpa": _LAKH, "lakh": _LAKH, "lakhs": _LAKH, "lac": _LAKH, "k": 1_000, "cr": 1e7, "crore": 1e7}
    has_currency = currency is not None  # a currency in the text lets a range's bare numbers count
    values: list[float] = []
    for m in _SALARY_TOKEN.finditer(text):
        cur, num_raw, unit = m.group(1), m.group(2), (m.group(3) or "").lower()
        if not cur and not unit and not has_currency:
            continue
        try:
            num = float(num_raw.replace(",", ""))
        except ValueError:
            continue
        if unit:
            mult = unit_mult.get(unit, 1.0)
        elif context_mult and num < 10_000:   # bare number in a lakh/crore context
            mult = context_mult
        else:
            mult = 1.0
        values.append(num * mult)
    if not values:
        return (None, None, currency, period, warnings)
    values.sort()
    lo, hi = values[0], (values[-1] if len(values) > 1 else None)
    if currency is None:
        warnings.append("Currency could not be determined")
    if period is None:
        warnings.append("Salary period could not be determined")
    return (lo, hi, currency, period, warnings)


class SourceName(str, Enum):
    LINKEDIN = "LINKEDIN"
    INDEED = "INDEED"
    NAUKRI = "NAUKRI"
    ADZUNA = "ADZUNA"
    COMPANY_CAREER = "COMPANY_CAREER"
    RSS_NEWS = "RSS_NEWS"
    GOVERNMENT = "GOVERNMENT"
    OTHER = "OTHER"


_SOURCE_MAP: dict[str, SourceName] = {
    "linkedin": SourceName.LINKEDIN, "indeed": SourceName.INDEED, "naukri": SourceName.NAUKRI,
    "adzuna": SourceName.ADZUNA, "company_career": SourceName.COMPANY_CAREER,
    "company_career_pages": SourceName.COMPANY_CAREER, "career": SourceName.COMPANY_CAREER,
    "demo_career": SourceName.COMPANY_CAREER, "demo_jobs": SourceName.OTHER,
    "rss_news": SourceName.RSS_NEWS, "company_newsroom": SourceName.RSS_NEWS,
    "government_open_data": SourceName.GOVERNMENT, "government_procurement": SourceName.GOVERNMENT,
}


def normalize_source_name(original: Optional[str]) -> SourceName:
    if not original:
        return SourceName.OTHER
    key = normalize_for_compare(original).replace(" ", "_")
    if key in _SOURCE_MAP:
        return _SOURCE_MAP[key]
    for token, name in _SOURCE_MAP.items():
        if token in key:
            return name
    return SourceName.OTHER


def normalize_url(url: Optional[str]) -> tuple[Optional[str], list[str]]:
    """Normalize for comparison: drop fragment + tracking params, lowercase host,
    strip trailing slash. Never rewrites the scheme in a way that breaks access."""
    warnings: list[str] = []
    if not url or not url.strip():
        return (None, warnings)
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https", ""):
        warnings.append("unusual URL scheme")
    query = "&".join(
        q for q in parts.query.split("&")
        if q and not any(q.lower().startswith(p) for p in ("utm_", "gclid", "fbclid", "mc_"))
    )
    path = parts.path.rstrip("/") or ""
    normalized = urlunsplit((parts.scheme or "https", parts.netloc.lower(), path, query, ""))
    return (normalized or None, warnings)
