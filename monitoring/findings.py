"""A ``Finding`` is a detector's proposed alert-worthy fact (§26, §27).

Detectors emit Findings from REAL data; the notification service is the single
place that turns Findings into persisted ``Alert`` rows after applying user
preferences, severity rules, provenance gating, and deduplication. Keeping
detection and alerting separate means detectors never decide notification
policy, and alerting never re-derives facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from database.models import AlertSeverity, AlertType


@dataclass
class Finding:
    alert_type: AlertType
    title: str
    message: str
    dedup_key: str
    severity: AlertSeverity = AlertSeverity.LOW
    company_id: int | None = None
    lead_id: int | None = None
    opportunity_id: int | None = None
    signal_id: int | None = None
    tender_id: int | None = None
    source_id: str | None = None
    evidence_ids: list[int] = field(default_factory=list)
    link: str | None = None
    # Business findings must be REAL; operational (source-health) findings are
    # not business data. The alert service enforces the REAL requirement for
    # business alert types.
    provenance: str = "REAL"
