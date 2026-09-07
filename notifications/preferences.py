"""User alert preferences (§32). Single-user app => one DEFAULT row. Defaults are
conservative to avoid notification noise: only high-value alert types are on."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import AlertSeverity, NotificationPreference
from monitoring.config import DEFAULT_ALERT

DEFAULT_SCOPE = "DEFAULT"


def get_or_create_preferences(session: Session, scope: str = DEFAULT_SCOPE) -> NotificationPreference:
    pref = session.execute(
        select(NotificationPreference).where(NotificationPreference.scope == scope)
    ).scalars().first()
    if pref is not None:
        return pref
    pref = NotificationPreference(
        scope=scope,
        hot_leads_only=False,
        min_score_increase=10,
        enabled_alert_types=list(DEFAULT_ALERT.default_enabled_types),
        min_severity=AlertSeverity.LOW,
        channels=["IN_APP"],
    )
    session.add(pref)
    session.flush()
    return pref


def update_preferences(session: Session, scope: str = DEFAULT_SCOPE, **fields) -> NotificationPreference:
    pref = get_or_create_preferences(session, scope)
    allowed = {
        "hot_leads_only", "min_score_increase", "enabled_alert_types", "min_severity", "channels",
    }
    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(pref, key, value)
    session.flush()
    return pref
