"""Job identity + layered match scoring (explainable, deterministic).

A match is decided from LAYERED evidence — never company + title alone. Different
cities or clearly different project tails prevent a merge even when the title and
company match (§7, §9, §39).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config.deduplication import DEFAULT_DEDUP_CONFIG, DedupConfig
from database.models import DataProvenance, MatchConfidence, MatchDecision, RemoteType
from processors.deduplication.similarity import (
    description_similarity,
    title_similarity,
    title_tail,
)


@dataclass
class DedupRecord:
    """Everything the matcher needs from one source record (post-normalization)."""

    source_id: str
    external_id: Optional[str] = None
    source_url: Optional[str] = None            # normalized for comparison
    content_hash: Optional[str] = None
    normalized_company_name: Optional[str] = None
    original_company_name: Optional[str] = None
    company_domain: Optional[str] = None
    source_company_id: Optional[str] = None
    normalized_title: Optional[str] = None
    original_title: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    remote_type: RemoteType = RemoteType.UNKNOWN
    published_at: Optional[datetime] = None
    description: Optional[str] = None
    technologies: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: Optional[str] = None
    employment_type: Optional[str] = None
    job_status: Optional[str] = None
    source_priority: int = 5
    source_confidence: int = 0
    raw_record_id: Optional[int] = None
    data_provenance: DataProvenance = DataProvenance.REAL

    def blocking_key(self) -> Optional[str]:
        """Records with a different key are never compared (candidate blocking).

        Uses the normalized company name (stable across sources) — the domain is
        a matching signal WITHIN a block, not a block key, so a source that lacks
        a domain still lands in the same block as one that has it."""
        return self.normalized_company_name or self.company_domain or None


@dataclass
class MatchResult:
    score: int
    confidence: MatchConfidence
    decision: MatchDecision
    matched_fields: list[str] = field(default_factory=list)
    differences: list[str] = field(default_factory=list)
    reason: str = ""


def _days_apart(a: Optional[datetime], b: Optional[datetime]) -> Optional[int]:
    if a is None or b is None:
        return None
    return abs((a - b).days)


def _no_match(reason: str, diffs: list[str]) -> MatchResult:
    return MatchResult(0, MatchConfidence.NO_MATCH, MatchDecision.NO_MATCH, [], diffs, reason)


def match(a: DedupRecord, b: DedupRecord, config: DedupConfig = DEFAULT_DEDUP_CONFIG) -> MatchResult:
    matched: list[str] = []
    diffs: list[str] = []

    # 1. Strongest: same source + external id (a re-fetch of the exact posting).
    if a.external_id and a.source_id == b.source_id and a.external_id == b.external_id:
        return MatchResult(config.score_same_source_external_id, MatchConfidence.HIGH,
                           MatchDecision.AUTO_MERGE, ["source_external_id"], [], "Same source + external id")

    # 2. Same canonical URL.
    if a.source_url and b.source_url and a.source_url == b.source_url:
        return MatchResult(config.score_same_url, MatchConfidence.HIGH, MatchDecision.AUTO_MERGE,
                           ["source_url"], [], "Same canonical source URL")

    # 2b. Different external ids WITHIN the same source are distinct postings —
    # the source's own ids are authoritative. Deduplication is cross-source.
    if a.external_id and b.external_id and a.source_id == b.source_id and a.external_id != b.external_id:
        return _no_match("Distinct external ids within the same source", ["different external id (same source)"])

    # 3. Company gate — required.
    domain_match = bool(a.company_domain and a.company_domain == b.company_domain)
    name_match = bool(a.normalized_company_name and a.normalized_company_name == b.normalized_company_name)
    if not (domain_match or name_match):
        return _no_match("Company domain/name differs", ["company differs"])

    score = config.weight_company_domain if domain_match else config.weight_company_name
    matched.append("company_domain" if domain_match else "normalized_company_name")

    # 4. Location.
    city_a, city_b = (a.city or "").lower(), (b.city or "").lower()
    remote_a = a.remote_type is RemoteType.REMOTE
    remote_b = b.remote_type is RemoteType.REMOTE
    location_conflict = False
    if city_a and city_b and city_a == city_b:
        score += config.weight_location_city
        matched.append("city")
    elif remote_a and remote_b and (a.country or "") == (b.country or ""):
        score += config.weight_remote_match
        matched.append("remote")
    elif city_a and city_b and city_a != city_b:
        location_conflict = True
        diffs.append("city differs")
    elif a.state and a.state == b.state:
        score += config.weight_location_state
        matched.append("state")

    # 5. Title.
    title_exact = bool(a.normalized_title and a.normalized_title.lower() == (b.normalized_title or "").lower())
    tsim = title_similarity(a.normalized_title, b.normalized_title)
    tail_a, tail_b = title_tail(a.normalized_title), title_tail(b.normalized_title)
    tail_conflict = bool(tail_a and tail_b and title_similarity(tail_a, tail_b) < 0.5)
    if title_exact:
        score += config.weight_title_exact
        matched.append("normalized_title")
    else:
        score += int(config.weight_title_similar * tsim)
        if tsim < config.title_similar_min:
            diffs.append("title differs")

    # 6. Dates.
    d = _days_apart(a.published_at, b.published_at)
    if d is not None:
        if d <= config.date_close_days:
            score += config.weight_date_close
            matched.append("published_date")
        elif d <= config.date_near_days:
            score += config.weight_date_near

    # 7. Description similarity (supporting).
    dsim = description_similarity(a.description, b.description)
    if a.description and b.description:
        score += int(config.weight_description * dsim)
        if dsim >= 0.4:
            matched.append("description_similarity")

    score = max(0, min(100, score))

    # 8. Guards against over-merging distinct jobs.
    strong_text = title_exact or (tsim >= config.title_similar_min and dsim >= config.description_similar_strong)
    if location_conflict:
        return _no_match("Same company/title but different city — separate jobs", diffs)
    if tail_conflict and dsim < config.description_similar_strong:
        return _no_match("Same role but different project/team — separate jobs", diffs + ["project/team differs"])

    # 9. Decision. REVIEW still requires the titles/descriptions to be plausibly
    # the same role — different roles at the same company are not near-duplicates.
    plausible_same_role = tsim >= 0.6 or dsim >= config.description_similar_strong
    if score >= config.auto_merge_min and strong_text:
        conf, decision = MatchConfidence.HIGH, MatchDecision.AUTO_MERGE
    elif score >= config.review_min and plausible_same_role:
        conf, decision = MatchConfidence.MEDIUM, MatchDecision.REVIEW
    elif score > 0:
        conf, decision = MatchConfidence.LOW, MatchDecision.NO_MATCH
    else:
        conf, decision = MatchConfidence.NO_MATCH, MatchDecision.NO_MATCH

    reason = f"score={score}; matched: {', '.join(matched) or 'none'}" + (
        f"; differences: {', '.join(diffs)}" if diffs else "")
    return MatchResult(score, conf, decision, matched, diffs, reason)
