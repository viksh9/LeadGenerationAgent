"""Real-data-only integrity: provenance guards, database audit, and cleanup.

This module is the single source of truth for the platform's real-data-only
policy. It does three things, none of which depend on the network or an LLM:

1. Guards (``guard_lead_fields`` / ``guard_provenance``) that runtime write
   paths call before persisting a business record. When enforcement is active
   (production/staging, or ``ENFORCE_REAL_DATA=true``) they reject synthetic/demo
   provenance and REAL records that carry no source-backed evidence.

2. An audit (``audit_database``) that reports what is actually stored: counts per
   entity, provenance breakdown, records missing provenance/source, and any
   synthetic records lingering in the database. Used by ``scripts/db_audit.py``
   and the data-integrity tests.

3. A safe cleanup (``purge_synthetic``) that removes ONLY synthetic/demo records
   in foreign-key-safe order, never touching schema or real data.

The guards never fabricate or mutate provenance: unknown stays unknown, synthetic
stays synthetic. They only refuse to persist data that violates the policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from config.exceptions import AppError
from database.models import (
    BusinessSignal,
    Company,
    CompanyEvent,
    CompanyRelationship,
    CompanyResolutionCandidate,
    CompanySourceReference,
    DataProvenance,
    EvidenceClaim,
    EvidenceConflict,
    EvidenceRecord,
    JobDuplicateCandidate,
    JobRecord,
    JobSourceReference,
    Lead,
    OpportunityCandidate,
    RawSourceRecord,
    SignalSourceReference,
)


class RealDataViolation(AppError):
    """A write would have persisted fabricated / source-less business data."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422, code="real_data_violation")


# --------------------------------------------------------------------------- #
# Enforcement toggle
# --------------------------------------------------------------------------- #
def enforcement_active(environment: Optional[str] = None) -> bool:
    """Whether real-data-only write guards are active.

    Defaults to the ``real_data_only`` setting (on in production/staging). An
    explicit ``environment`` argument overrides it (used by tests and callers
    that already hold the environment string).
    """
    if environment is not None:
        return environment.strip().lower() in {"production", "prod", "staging", "stage"}
    from config.settings import get_settings

    return get_settings().real_data_only


# --------------------------------------------------------------------------- #
# Write guards
# --------------------------------------------------------------------------- #
def _has_source_evidence(fields: dict[str, Any]) -> bool:
    """True if a lead payload carries at least one trace back to a real source.

    A real lead must point at *something* observed: a source URL/name, a positive
    source count, or a non-empty evidence list. AI-generated narrative fields
    (opportunity_summary, recommended_pitch, …) never count as evidence.
    """
    for key in ("source_url", "source_name"):
        value = fields.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if value and not isinstance(value, str):
            return True
    if (fields.get("source_count") or 0) > 0:
        return True
    evidence = fields.get("evidence")
    if isinstance(evidence, (list, tuple)) and len(evidence) > 0:
        return True
    return False


def guard_provenance(
    provenance: Any,
    *,
    entity: str,
    environment: Optional[str] = None,
) -> None:
    """Reject synthetic/demo provenance when enforcement is active.

    No-op outside enforcement (development/test) so local demos and the test
    suite are unaffected. Raises ``RealDataViolation`` for SYNTHETIC in a
    real-data-only environment.
    """
    if not enforcement_active(environment):
        return
    value = provenance.value if isinstance(provenance, DataProvenance) else provenance
    if value == DataProvenance.SYNTHETIC.value:
        raise RealDataViolation(
            f"Refusing to persist a SYNTHETIC {entity} in a real-data-only environment. "
            "Synthetic/demo data is not permitted in production."
        )


def guard_lead_fields(fields: dict[str, Any], *, environment: Optional[str] = None) -> None:
    """Guard a lead write: no synthetic provenance, and REAL needs source evidence.

    Called by ``create_lead`` before persistence. No-op outside enforcement.
    """
    if not enforcement_active(environment):
        return
    provenance = fields.get("data_provenance", DataProvenance.REAL)
    guard_provenance(provenance, entity="lead", environment=environment)
    if not _has_source_evidence(fields):
        raise RealDataViolation(
            "Refusing to persist a lead with no source-backed evidence. A real lead "
            "must reference at least one collected source (source_url, source_name, "
            "source_count, or evidence). Generated text does not count as evidence."
        )


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
# Entities that carry data_provenance, and the ones that use the raw
# is_synthetic flag. Child/join tables inherit provenance from their parent.
_PROVENANCE_ENTITIES: tuple[tuple[str, Any], ...] = (
    ("leads", Lead),
    ("companies", Company),
    ("job_records", JobRecord),
    ("business_signals", BusinessSignal),
    ("opportunity_candidates", OpportunityCandidate),
    ("evidence_records", EvidenceRecord),
    ("evidence_conflicts", EvidenceConflict),
    ("evidence_claims", EvidenceClaim),
    ("job_duplicate_candidates", JobDuplicateCandidate),
    ("company_events", CompanyEvent),
    ("company_relationships", CompanyRelationship),
    ("company_resolution_candidates", CompanyResolutionCandidate),
)

# Tables whose "real vs synthetic" is expressed by the raw is_synthetic flag.
_SYNTHETIC_FLAG_ENTITIES: tuple[tuple[str, Any], ...] = (
    ("raw_source_records", RawSourceRecord),
)


@dataclass
class EntityAudit:
    table: str
    total: int
    real: int = 0
    synthetic: int = 0
    missing_provenance: int = 0
    missing_source: int = 0


@dataclass
class DatabaseAudit:
    entities: list[EntityAudit] = field(default_factory=list)

    @property
    def synthetic_total(self) -> int:
        return sum(e.synthetic for e in self.entities)

    @property
    def missing_provenance_total(self) -> int:
        return sum(e.missing_provenance for e in self.entities)

    @property
    def total_records(self) -> int:
        return sum(e.total for e in self.entities)

    @property
    def is_clean(self) -> bool:
        """True when the database contains no synthetic/demo or provenance-less
        business records — the invariant a real-data-only deployment must hold."""
        return self.synthetic_total == 0 and self.missing_provenance_total == 0

    def by_table(self, table: str) -> Optional[EntityAudit]:
        return next((e for e in self.entities if e.table == table), None)


def _count(session: Session, model: Any, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    return int(session.scalar(stmt) or 0)


def audit_database(session: Session) -> DatabaseAudit:
    """Report counts, provenance, and integrity gaps for every business table."""
    audit = DatabaseAudit()

    for table, model in _PROVENANCE_ENTITIES:
        total = _count(session, model)
        real = _count(session, model, model.data_provenance == DataProvenance.REAL)
        synthetic = _count(session, model, model.data_provenance == DataProvenance.SYNTHETIC)
        missing_prov = _count(session, model, model.data_provenance.is_(None))
        entry = EntityAudit(
            table=table, total=total, real=real, synthetic=synthetic,
            missing_provenance=missing_prov,
        )
        # Source completeness only where the model exposes a source URL column.
        if hasattr(model, "source_url"):
            entry.missing_source = _count(
                session, model,
                model.data_provenance == DataProvenance.REAL,
                (model.source_url.is_(None)) | (func.trim(model.source_url) == ""),
            )
        audit.entities.append(entry)

    for table, model in _SYNTHETIC_FLAG_ENTITIES:
        total = _count(session, model)
        synthetic = _count(session, model, model.is_synthetic.is_(True))
        entry = EntityAudit(
            table=table, total=total, real=total - synthetic, synthetic=synthetic,
        )
        if hasattr(model, "source_url"):
            entry.missing_source = _count(
                session, model,
                model.is_synthetic.is_(False),
                (model.source_url.is_(None)) | (func.trim(model.source_url) == ""),
            )
        audit.entities.append(entry)

    return audit


# --------------------------------------------------------------------------- #
# Safe synthetic cleanup
# --------------------------------------------------------------------------- #
def _synthetic_ids(session: Session, model: Any) -> list[int]:
    return list(
        session.scalars(select(model.id).where(model.data_provenance == DataProvenance.SYNTHETIC))
    )


def purge_synthetic(session: Session) -> dict[str, int]:
    """Delete every synthetic/demo record in foreign-key-safe order.

    Returns a mapping of table -> rows removed. Only touches SYNTHETIC-provenance
    rows (and is_synthetic raw records) plus the child/join rows that reference
    them; never deletes real data and never alters schema.
    """
    removed: dict[str, int] = {}

    def _delete(table: str, model: Any, *where) -> None:
        stmt = delete(model)
        for clause in where:
            stmt = stmt.where(clause)
        result = session.execute(stmt)
        removed[table] = result.rowcount or 0

    # Parent id sets captured before their parents are deleted.
    synthetic_company_ids = _synthetic_ids(session, Company)
    synthetic_job_ids = _synthetic_ids(session, JobRecord)
    synthetic_signal_ids = _synthetic_ids(session, BusinessSignal)

    # 1) Child / join tables (no own provenance) — delete by synthetic parent.
    if synthetic_company_ids:
        _delete("company_source_references", CompanySourceReference,
                CompanySourceReference.company_id.in_(synthetic_company_ids))
    else:
        removed["company_source_references"] = 0
    if synthetic_job_ids:
        _delete("job_source_references", JobSourceReference,
                JobSourceReference.job_record_id.in_(synthetic_job_ids))
    else:
        removed["job_source_references"] = 0
    if synthetic_signal_ids:
        _delete("signal_source_references", SignalSourceReference,
                SignalSourceReference.business_signal_id.in_(synthetic_signal_ids))
    else:
        removed["signal_source_references"] = 0

    # 2) Provenance-bearing tables (children before parents).
    _delete("company_events", CompanyEvent, CompanyEvent.data_provenance == DataProvenance.SYNTHETIC)
    _delete("company_relationships", CompanyRelationship,
            CompanyRelationship.data_provenance == DataProvenance.SYNTHETIC)
    _delete("company_resolution_candidates", CompanyResolutionCandidate,
            CompanyResolutionCandidate.data_provenance == DataProvenance.SYNTHETIC)
    _delete("evidence_claims", EvidenceClaim, EvidenceClaim.data_provenance == DataProvenance.SYNTHETIC)
    _delete("evidence_conflicts", EvidenceConflict,
            EvidenceConflict.data_provenance == DataProvenance.SYNTHETIC)
    _delete("evidence_records", EvidenceRecord, EvidenceRecord.data_provenance == DataProvenance.SYNTHETIC)
    _delete("job_duplicate_candidates", JobDuplicateCandidate,
            JobDuplicateCandidate.data_provenance == DataProvenance.SYNTHETIC)
    _delete("opportunity_candidates", OpportunityCandidate,
            OpportunityCandidate.data_provenance == DataProvenance.SYNTHETIC)
    _delete("business_signals", BusinessSignal, BusinessSignal.data_provenance == DataProvenance.SYNTHETIC)
    _delete("job_records", JobRecord, JobRecord.data_provenance == DataProvenance.SYNTHETIC)
    _delete("leads", Lead, Lead.data_provenance == DataProvenance.SYNTHETIC)
    _delete("companies", Company, Company.data_provenance == DataProvenance.SYNTHETIC)

    # 3) Raw records flagged synthetic.
    _delete("raw_source_records", RawSourceRecord, RawSourceRecord.is_synthetic.is_(True))

    session.commit()
    return {k: v for k, v in removed.items() if v}
