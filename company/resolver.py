"""CompanyEntityResolver — deterministic, explainable entity resolution.

Domain-first: a verified domain match is the strongest signal; a name match alone
NEVER produces a high-confidence merge, and a name match with a CONFLICTING domain
goes to review. Accuracy over aggressive merging. No LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config.company import DEFAULT_MATCH_CONFIG, CompanyMatchConfig
from company.normalization import normalize_domain, normalize_name
from database.models import CompanyMatchStatus


@dataclass
class ObservedCompany:
    name: Optional[str] = None
    domain: Optional[str] = None          # may be a URL; normalized internally
    website: Optional[str] = None
    email_domain: Optional[str] = None
    legal_name: Optional[str] = None
    city: Optional[str] = None
    source_id: Optional[str] = None
    source_url: Optional[str] = None


@dataclass
class CompanyCandidate:
    id: int
    normalized_name: str
    primary_domain: Optional[str] = None
    alternate_domains: list[str] = field(default_factory=list)
    legal_name: Optional[str] = None
    headquarters_city: Optional[str] = None
    tokens: list[str] = field(default_factory=list)


@dataclass
class CompanyResolutionResult:
    matched_company_id: Optional[int]
    match_status: CompanyMatchStatus
    confidence: int
    matching_factors: list[str] = field(default_factory=list)
    conflicting_factors: list[str] = field(default_factory=list)
    candidate_companies: list[int] = field(default_factory=list)
    recommended_action: str = "CREATE_NEW"    # LINK | REVIEW | CREATE_NEW
    resolution_explanation: str = ""


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class CompanyEntityResolver:
    def __init__(self, config: CompanyMatchConfig = DEFAULT_MATCH_CONFIG) -> None:
        self.config = config

    def _score(self, obs: ObservedCompany, cand: CompanyCandidate) -> tuple[int, list[str], list[str], bool]:
        c = self.config
        factors: list[str] = []
        conflicts: list[str] = []
        score = 0
        obs_domain = normalize_domain(obs.domain or obs.website)
        cand_domains = {d for d in ([cand.primary_domain] + list(cand.alternate_domains)) if d}

        domain_match = bool(obs_domain and obs_domain in cand_domains)
        domain_conflict = bool(obs_domain and cand.primary_domain and obs_domain not in cand_domains)

        if domain_match:
            score += c.weight_domain_exact
            factors.append("exact verified domain match")
        if domain_conflict:
            conflicts.append(f"different domain ({obs_domain} vs {cand.primary_domain})")
            score -= c.conflicting_domain_penalty

        obs_norm = normalize_name(obs.name)
        if obs.legal_name and cand.legal_name and normalize_name(obs.legal_name).normalized_name == normalize_name(cand.legal_name).normalized_name:
            score += c.weight_legal_name_exact
            factors.append("legal name match")
        name_exact = obs_norm.normalized_name and obs_norm.normalized_name == cand.normalized_name
        if name_exact:
            score += c.weight_normalized_name_exact
            factors.append("normalized name match")
        else:
            overlap = _jaccard(set(obs_norm.tokens), set(cand.tokens))
            if overlap:
                score += int(c.weight_token_overlap * overlap)
                if overlap >= 0.5:
                    factors.append(f"token overlap {overlap:.0%}")

        if obs.email_domain and normalize_domain(obs.email_domain) in cand_domains:
            score += c.weight_email_domain
            factors.append("email domain match")
        if obs.city and cand.headquarters_city and obs.city.lower() == cand.headquarters_city.lower():
            score += c.weight_hq_city
            factors.append("same city")

        return max(-100, min(100, score)), factors, conflicts, bool(name_exact)

    def resolve(self, obs: ObservedCompany, candidates: list[CompanyCandidate]) -> CompanyResolutionResult:
        c = self.config
        if not candidates:
            return CompanyResolutionResult(
                None, CompanyMatchStatus.NO_MATCH, 0, [], [], [], "CREATE_NEW",
                "No candidate companies in the same block — new company.")

        scored = []
        for cand in candidates:
            score, factors, conflicts, name_exact = self._score(obs, cand)
            scored.append((score, cand, factors, conflicts, name_exact))
        scored.sort(key=lambda t: t[0], reverse=True)
        best_score, best, factors, conflicts, name_exact = scored[0]
        candidate_ids = [s[1].id for s in scored]

        domain_match = any("exact verified domain match" == f for f in factors)
        domain_conflict = bool(conflicts)

        if domain_match:
            status, action, conf = CompanyMatchStatus.EXACT_MATCH, "LINK", min(99, 90 + max(0, best_score - c.weight_domain_exact))
        elif domain_conflict and name_exact:
            # Same name, different domain — do NOT auto-merge.
            status, action, conf = CompanyMatchStatus.CONFLICT, "REVIEW", max(0, best_score)
        elif best_score >= c.high_min:
            status, action, conf = CompanyMatchStatus.HIGH_CONFIDENCE_MATCH, "LINK", min(95, best_score)
        elif best_score >= c.possible_min:
            status, action, conf = CompanyMatchStatus.POSSIBLE_MATCH, "REVIEW", best_score
        else:
            status, action, conf = CompanyMatchStatus.NO_MATCH, "CREATE_NEW", max(0, best_score)

        matched = best.id if action == "LINK" else None
        explanation = (
            f"{status.value} (score {best_score}). "
            f"Matched: {', '.join(factors) or 'none'}."
            + (f" Conflicts: {', '.join(conflicts)}." if conflicts else "")
        )
        return CompanyResolutionResult(
            matched_company_id=matched, match_status=status, confidence=conf,
            matching_factors=factors, conflicting_factors=conflicts,
            candidate_companies=candidate_ids, recommended_action=action,
            resolution_explanation=explanation,
        )
