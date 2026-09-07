"""Controlled query strategy for the Adzuna collector.

Avoids a blind roles×locations×pages explosion (which would burn the daily API
quota). Instead it generates a bounded, de-duplicated request plan from a chosen
mode, capped at ``max_requests``:

  ROLE_FIRST        one India-wide search per role term (breadth of roles first)
  TECHNOLOGY_FIRST  one India-wide search per technology term
  LOCATION_FIRST    one broad IT search per major Indian location

"India-wide" means no ``where`` filter (the country path already scopes to India),
so a single request per term covers the whole country instead of one-per-city.
Pagination (``max_pages``) is applied per base query, newest results first, and the
total is always clamped to ``max_requests``.
"""

from __future__ import annotations

from typing import Optional

from collectors.base import FetchRequest

VALID_MODES = ("ROLE_FIRST", "TECHNOLOGY_FIRST", "LOCATION_FIRST")

# A broad but still IT-scoped query used by LOCATION_FIRST (one per city).
_LOCATION_MODE_QUERY = "software engineer"


def _dedupe(requests: list[FetchRequest]) -> list[FetchRequest]:
    seen: set[tuple] = set()
    out: list[FetchRequest] = []
    for req in requests:
        key = (req.query, req.location, req.page)
        if key not in seen:
            seen.add(key)
            out.append(req)
    return out


def build_plan(
    *,
    mode: str,
    search_terms: list[str],
    locations: list[str],
    max_pages: int,
    max_requests: int,
    location_query: str = _LOCATION_MODE_QUERY,
) -> list[FetchRequest]:
    """Build a bounded FetchRequest plan for the given mode.

    Raises ValueError for an unknown mode (never silently falls back).
    """
    mode = (mode or "ROLE_FIRST").upper()
    if mode not in VALID_MODES:
        raise ValueError(f"Unknown Adzuna search_mode {mode!r}; expected one of {VALID_MODES}.")
    max_pages = max(1, max_pages)
    max_requests = max(1, max_requests)

    plan: list[FetchRequest] = []
    if mode in ("ROLE_FIRST", "TECHNOLOGY_FIRST"):
        # One India-wide base query per term; paginate each until the cap.
        for term in search_terms:
            for page in range(1, max_pages + 1):
                plan.append(FetchRequest(query=term, location=None, page=page))
    else:  # LOCATION_FIRST
        for location in locations:
            for page in range(1, max_pages + 1):
                plan.append(FetchRequest(query=location_query, location=location, page=page))

    return _dedupe(plan)[:max_requests]


def describe_plan(plan: list[FetchRequest]) -> dict:
    """Small summary for logging/audit (no credentials)."""
    return {
        "requests": len(plan),
        "distinct_queries": len({r.query for r in plan}),
        "distinct_locations": len({r.location for r in plan}),
        "max_page": max((r.page or 1) for r in plan) if plan else 0,
    }
