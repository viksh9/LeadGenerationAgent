"""Deterministic lead readiness — based on EVIDENCE quality, not the lead score.

Weak/unverified data must never silently become a high-confidence production lead.
"""

from __future__ import annotations

from config.evidence import DEFAULT_THRESHOLDS, VerificationThresholds
from database.models import LeadReadiness, VerificationStatus


def classify_readiness(
    *,
    verification_status: VerificationStatus,
    evidence_confidence: int,
    freshness_score: int,
    has_meaningful_signal: bool,
    thresholds: VerificationThresholds = DEFAULT_THRESHOLDS,
) -> LeadReadiness:
    if verification_status is VerificationStatus.CONTRADICTED:
        return LeadReadiness.HOLD
    if verification_status is VerificationStatus.STALE:
        return LeadReadiness.HOLD
    if (verification_status is VerificationStatus.VERIFIED
            and evidence_confidence >= thresholds.ready_min_confidence
            and freshness_score >= thresholds.ready_min_freshness
            and has_meaningful_signal):
        return LeadReadiness.READY
    if evidence_confidence >= thresholds.review_min_confidence and has_meaningful_signal:
        return LeadReadiness.REVIEW_REQUIRED
    # Insufficient/absent evidence for a real opportunity.
    return LeadReadiness.DISCARD
