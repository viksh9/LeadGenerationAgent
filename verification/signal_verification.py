"""Combine source reliability + freshness + corroboration + conflicts into a
verification result — keeping the FOUR scores distinct and never collapsing them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from config.evidence import DEFAULT_THRESHOLDS
from database.models import ConflictSeverity, SourceTier, VerificationStatus
from verification.conflicts import ConflictEvidence, ConflictFinding, detect_conflicts
from verification.corroboration import CorroborationResult, EvidenceItem, corroborate
from verification.freshness import compute_freshness
from verification.source_reliability import compute_source_reliability, source_tier_for


@dataclass
class EvidenceInput:
    """One piece of evidence fed to verification (from a raw record / source ref)."""

    source_id: str
    source_category: Optional[str] = None
    content_hash: Optional[str] = None
    canonical_job_id: Optional[int] = None
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status: Optional[str] = None
    closing_date: Optional[datetime] = None
    normalized_company_name: Optional[str] = None
    normalized_title: Optional[str] = None
    city: Optional[str] = None
    project_status: Optional[str] = None

    @property
    def source_tier(self) -> SourceTier:
        return source_tier_for(self.source_id, self.source_category)


@dataclass
class VerificationResult:
    verification_status: VerificationStatus
    source_reliability: int          # 1) trustworthiness of the source(s)
    evidence_confidence: int         # 2) how strongly evidence supports the claim
    signal_confidence: int           # 3) confidence the signal actually exists
    freshness_score: int
    corroboration_score: int
    conflict_score: int              # 0 (none) .. 100 (severe contradiction)
    supporting_evidence_count: int
    independent_support_count: int
    syndicated_count: int
    contradictory_evidence_count: int
    reasons: list[str] = field(default_factory=list)
    verified_at: Optional[datetime] = None


@dataclass
class SignalVerificationResult(VerificationResult):
    signal_id: Optional[int] = None


def verify_evidence_set(
    evidences: list[EvidenceInput],
    *,
    signal_type: Optional[str] = None,
    now: Optional[datetime] = None,
    thresholds=DEFAULT_THRESHOLDS,
) -> VerificationResult:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    reasons: list[str] = []

    if not evidences:
        return VerificationResult(
            VerificationStatus.UNVERIFIED, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            ["No supporting evidence available."], now)

    # 1) Source reliability — best (most authoritative) source.
    reliabilities = [compute_source_reliability(e.source_id, category=e.source_category) for e in evidences]
    best_reliability = max(r.reliability_score for r in reliabilities)
    reasons.append(f"Best source reliability {best_reliability} (tier "
                   f"{min(reliabilities, key=lambda r: -r.reliability_score).source_tier.value}).")

    # freshness — freshest supporting evidence.
    fresh = [compute_freshness(signal_type=signal_type, published_at=e.published_at, observed_at=e.observed_at,
                               updated_at=e.updated_at, closing_date=e.closing_date, source_status=e.status, now=now)
             for e in evidences]
    best_freshness = max(f.score for f in fresh)
    all_stale = all(f.is_stale for f in fresh)
    reasons.append(f"Freshness {best_freshness} ({min(fresh, key=lambda f: -f.score).reason})")

    # corroboration — independent (non-syndicated) support.
    corr: CorroborationResult = corroborate([
        EvidenceItem(e.source_id, e.source_tier, e.content_hash, e.canonical_job_id, e.source_url) for e in evidences
    ])
    if corr.syndicated_count:
        reasons.append(f"{corr.independent_support_count} independent source(s); "
                       f"{corr.syndicated_count} syndicated copy(ies) not counted as independent.")
    elif corr.independent_support_count > 1:
        reasons.append(f"{corr.independent_support_count} independent sources corroborate.")

    # conflicts.
    findings: list[ConflictFinding] = detect_conflicts([
        ConflictEvidence(i, e.source_id, e.source_tier, e.normalized_company_name, e.normalized_title,
                         e.city, e.status, e.project_status, e.published_at)
        for i, e in enumerate(evidences)
    ])
    high_conflict = any(f.severity is ConflictSeverity.HIGH for f in findings)
    conflict_score = 0
    if findings:
        conflict_score = max({ConflictSeverity.HIGH: 90, ConflictSeverity.MEDIUM: 55,
                              ConflictSeverity.LOW: 25}[f.severity] for f in findings)
        reasons.append(f"{len(findings)} conflict(s) detected: " + "; ".join(f.description for f in findings[:2]))

    # Evidence confidence (2) — combines reliability + freshness + corroboration.
    evidence_confidence = round(0.45 * best_reliability + 0.30 * best_freshness) + min(corr.corroboration_score, 25)
    evidence_confidence = max(0, min(100, evidence_confidence))

    # Signal confidence (3) — does the signal actually exist? Boosted by
    # independent support, dampened by conflict. Distinct from evidence_confidence.
    signal_confidence = min(100, evidence_confidence + max(0, corr.independent_support_count - 1) * 4)
    if high_conflict:
        signal_confidence = min(signal_confidence, 45)

    # Status.
    if high_conflict:
        status = VerificationStatus.CONTRADICTED
        evidence_confidence = min(evidence_confidence, 40)
    elif all_stale or best_freshness <= thresholds.stale_max_freshness:
        status = VerificationStatus.STALE
    elif (evidence_confidence >= thresholds.verified_min_confidence
          and best_freshness >= thresholds.verified_min_freshness):
        status = VerificationStatus.VERIFIED
    elif evidence_confidence >= thresholds.partial_min_confidence:
        status = VerificationStatus.PARTIALLY_VERIFIED
    else:
        status = VerificationStatus.UNVERIFIED

    return VerificationResult(
        verification_status=status,
        source_reliability=best_reliability,
        evidence_confidence=evidence_confidence,
        signal_confidence=signal_confidence,
        freshness_score=best_freshness,
        corroboration_score=corr.corroboration_score,
        conflict_score=conflict_score,
        supporting_evidence_count=len(evidences),
        independent_support_count=corr.independent_support_count,
        syndicated_count=corr.syndicated_count,
        contradictory_evidence_count=len(findings),
        reasons=reasons,
        verified_at=now,
    )
