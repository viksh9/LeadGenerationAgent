"""Source-specific evidence verifiers (clean extension point).

BaseEvidenceVerifier.verify() delegates to the shared verification logic; adapters
exist so source-specific rules (e.g. tender closing dates, official-source
provenance) can be added without touching the core. No network by default.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from database.models import EvidenceType
from verification.signal_verification import EvidenceInput, VerificationResult, verify_evidence_set


class BaseEvidenceVerifier:
    name = "generic"

    def verify(
        self, evidences: list[EvidenceInput], *, signal_type: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> VerificationResult:
        return verify_evidence_set(evidences, signal_type=signal_type, now=now)


class GenericSourceVerifier(BaseEvidenceVerifier):
    name = "generic"


class JobSourceVerifier(BaseEvidenceVerifier):
    name = "job"


class OfficialCareerPageVerifier(BaseEvidenceVerifier):
    """Official first-party career pages — highest provenance (tiering handled by
    config; this is the extension point for future first-party-only rules)."""

    name = "official_career_page"


class GovernmentSourceVerifier(BaseEvidenceVerifier):
    name = "government"


class NewsSourceVerifier(BaseEvidenceVerifier):
    name = "news"


class TenderSourceVerifier(BaseEvidenceVerifier):
    """Tenders/RFPs: closing/expiry date drives freshness (already handled by the
    freshness policy). Extension point for procurement-specific status rules."""

    name = "tender"


_BY_TYPE: dict[EvidenceType, BaseEvidenceVerifier] = {
    EvidenceType.JOB: JobSourceVerifier(),
    EvidenceType.BUSINESS_SIGNAL: NewsSourceVerifier(),
    EvidenceType.NEWS: NewsSourceVerifier(),
    EvidenceType.PROJECT: GenericSourceVerifier(),
    EvidenceType.TENDER: TenderSourceVerifier(),
    EvidenceType.COMPANY: OfficialCareerPageVerifier(),
}
_GENERIC = GenericSourceVerifier()


def select_verifier(evidence_type: EvidenceType) -> BaseEvidenceVerifier:
    return _BY_TYPE.get(evidence_type, _GENERIC)
