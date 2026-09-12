"""Deterministic OpenCorporates entity matching + India classification (Prompt 47).

Never marks VERIFIED_MATCH from name similarity alone (§6): a single exact
normalized-name match is upgraded to VERIFIED only with corroboration (a real
company number + India jurisdiction when India-first). Ambiguity → MULTIPLE_MATCHES.
"""

from __future__ import annotations

from typing import Optional

from integrations.public_intelligence.matching import normalize_company
from integrations.public_intelligence.opencorporates.models import OCCompany

VERIFIED_MATCH = "VERIFIED_MATCH"
LIKELY_MATCH = "LIKELY_MATCH"
MULTIPLE_MATCHES = "MULTIPLE_MATCHES"
NO_MATCH = "NO_MATCH"

# India presence classification (§15). GLOBAL_COMPANY kept as a back-compat alias of
# NON_INDIA for callers/tests that referenced the earlier name.
INDIA_ENTITY = "INDIA_ENTITY"
INDIA_OPERATION = "INDIA_OPERATION"
INDIA_OFFICE = "INDIA_OFFICE"
GLOBAL_WITH_INDIA_PRESENCE = "GLOBAL_WITH_INDIA_PRESENCE"
NON_INDIA = "NON_INDIA"
UNKNOWN = "UNKNOWN"
GLOBAL_COMPANY = NON_INDIA   # backwards-compatible alias


def _is_india(jc: Optional[str]) -> bool:
    return bool(jc) and jc.lower().startswith("in")


def _names(c: OCCompany) -> set[str]:
    names = {normalize_company(c.name), normalize_company(c.legal_name)}
    names.update(normalize_company(p) for p in c.previous_names)
    return {n for n in names if n}


def match_entity(*, company_name: str, candidates: list[OCCompany],
                 prefer_india: bool = True) -> tuple[Optional[OCCompany], str]:
    """Return (best_candidate_or_None, match_status)."""
    target = normalize_company(company_name)
    if not target or not candidates:
        return None, NO_MATCH

    exact = [c for c in candidates if target in _names(c)]
    if not exact:
        return None, NO_MATCH

    india_exact = [c for c in exact if _is_india(c.jurisdiction_code)]
    pool = india_exact if (prefer_india and india_exact) else exact

    if len(pool) == 1:
        best = pool[0]
        corroborated = bool(best.company_number) and (not prefer_india or _is_india(best.jurisdiction_code))
        return best, (VERIFIED_MATCH if corroborated else LIKELY_MATCH)
    # More than one exact match — ambiguous; surface the India-preferred one but flag it.
    return pool[0], MULTIPLE_MATCHES


def classify_india_entity(oc: Optional[OCCompany], *, india_presence: bool) -> str:
    """Classify India presence from EVIDENCE only (§15):
    - Indian-jurisdiction legal entity      -> INDIA_ENTITY
    - non-India legal entity + India office  -> GLOBAL_WITH_INDIA_PRESENCE
    - India presence but no legal entity     -> INDIA_OPERATION
    - non-India legal entity, no India office -> NON_INDIA
    - otherwise                              -> UNKNOWN"""
    if oc and _is_india(oc.jurisdiction_code):
        return INDIA_ENTITY
    if india_presence:
        return GLOBAL_WITH_INDIA_PRESENCE if oc else INDIA_OPERATION
    if oc:
        return NON_INDIA
    return UNKNOWN
