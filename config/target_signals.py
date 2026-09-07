"""Real business signals collectors should aim to surface.

These are collection *targets*. Each maps onto the existing `SignalType` used by
the signal-detection engine — we deliberately do NOT create a duplicate signal
enum. Some collection targets (e.g. LARGE_TECHNOLOGY_HIRING, CLOUD_MIGRATION,
STAFF_AUGMENTATION) are refinements that map onto an existing SignalType; the
detector/scorer decide the final classification.
"""

from __future__ import annotations

from dataclasses import dataclass

from database.models import SignalType


@dataclass(frozen=True)
class TargetSignal:
    """A signal we want collectors to help identify."""

    key: str
    signal_type: SignalType
    description: str


TARGET_SIGNALS: tuple[TargetSignal, ...] = (
    TargetSignal("HIRING", SignalType.HIRING, "Active technology hiring."),
    TargetSignal("LARGE_TECHNOLOGY_HIRING", SignalType.HIRING, "High-volume technology hiring (ramp-up)."),
    TargetSignal("PROJECT_AWARD", SignalType.PROJECT_AWARD, "A project or contract has been awarded/won."),
    TargetSignal("PROJECT_EXECUTION", SignalType.PROJECT_EXECUTION, "A project is being delivered/executed."),
    TargetSignal("DIGITAL_TRANSFORMATION", SignalType.DIGITAL_TRANSFORMATION, "Digital transformation programme."),
    TargetSignal("CLOUD_MIGRATION", SignalType.DIGITAL_TRANSFORMATION, "Cloud migration / modernization."),
    TargetSignal("TECHNOLOGY_MODERNIZATION", SignalType.TECHNOLOGY_INITIATIVE, "Application/technology modernization."),
    TargetSignal("EXPANSION", SignalType.EXPANSION, "Capacity or business expansion."),
    TargetSignal("VENDOR_REQUIREMENT", SignalType.VENDOR_REQUIREMENT, "Need for external vendors/partners."),
    TargetSignal("STAFF_AUGMENTATION", SignalType.VENDOR_REQUIREMENT, "Staff-augmentation / contract resourcing need."),
    TargetSignal("TECHNOLOGY_IMPLEMENTATION", SignalType.TECHNOLOGY_INITIATIVE, "Technology implementation initiative."),
    TargetSignal("CONTRACT", SignalType.CONTRACT, "A contractual engagement (SOW/MSA)."),
    TargetSignal("GOVERNMENT_PROJECT", SignalType.PROJECT_AWARD, "Government project/tender award."),
)

TARGET_SIGNALS_BY_KEY: dict[str, TargetSignal] = {t.key: t for t in TARGET_SIGNALS}


def signal_type_for(key: str) -> SignalType | None:
    """Return the mapped SignalType for a collection-target key (or None)."""
    target = TARGET_SIGNALS_BY_KEY.get(key)
    return target.signal_type if target else None
