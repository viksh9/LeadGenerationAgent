"""Real source inventory (Prompt 41 §5, §47).

Reports the implementation/configuration/connection/licensing status of every
registered source WITHOUT inference: implementation from the collector registry,
configuration from each collector's own config gate, connection + last
success/failure strictly from the persisted ``SourceHealth`` (only a real check
sets CONNECTED), and licensing from the source registry metadata.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from collectors.registry import runnable_source_ids
from collectors.source_status import all_source_status
from database.models import SourceHealth


def source_inventory(session: Session) -> list[dict]:
    runnable = runnable_source_ids()
    health_by_id = {h.source_id: h for h in session.execute(select(SourceHealth)).scalars().all()}

    inventory: list[dict] = []
    for report in all_source_status():
        health = health_by_id.get(report.source_id)
        connection = (health.connection_status.value if health and hasattr(health.connection_status, "value")
                      else (str(health.connection_status) if health else "NOT_CHECKED"))
        inventory.append({
            "source_id": report.source_id,
            "name": report.name,
            "provider": report.provider,
            "category": getattr(report.category, "value", str(report.category)),
            "capabilities": [getattr(c, "value", str(c)) for c in (report.capabilities or [])],
            "supports_india": report.supports_india,
            "reliability_tier": getattr(report.reliability_tier, "value", str(report.reliability_tier)),
            # Implementation: is there a runnable collector?
            "implementation": "IMPLEMENTED" if report.source_id in runnable
                              else ("IMPLEMENTED" if report.collector_implemented else "NOT_IMPLEMENTED"),
            # Configuration: derived from the runtime status report (config gate).
            "configuration_status": report.status.value if hasattr(report.status, "value") else str(report.status),
            # Connection: ONLY from a persisted real health check.
            "connection_status": connection,
            "last_success_at": (health.last_success_at.isoformat()
                                if health and health.last_success_at else None),
            "last_failure_at": (health.last_failure_at.isoformat()
                                if health and health.last_failure_at else None),
            "last_error": (health.last_error if health else None),
            # Licensing / compliance.
            "commercial_use_status": getattr(report.commercial_use_status, "value",
                                             str(report.commercial_use_status)),
            "documentation_url": report.documentation_url,
            "terms_url": report.terms_url,
            "detail": report.detail,
        })
    return inventory
