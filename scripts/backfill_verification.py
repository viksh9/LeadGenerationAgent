"""One-off remediation: verify REAL leads that were persisted without verification, then
re-propagate company evidence confidence.

The audit ingestion persist path builds company leads but does not run lead verification,
leaving new leads (and their companies) with evidence_confidence=0. This recomputes
verification from each lead's REAL evidence (no fabricated values) and re-runs the company
pipeline to propagate. Idempotent; safe to re-run.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from config import get_settings
from database.models import DataProvenance, Lead
from database.session import create_session_factory, get_engine, init_db
from ingestion.job_pipeline import run_company_pipeline
from verification.service import EvidenceVerificationService


def main() -> int:
    engine = get_engine(get_settings().database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        svc = EvidenceVerificationService(session)
        leads = list(session.scalars(select(Lead).where(Lead.data_provenance == DataProvenance.REAL)))
        verified = 0
        for lead in leads:
            svc.verify_lead(lead, persist=True)
            verified += 1
        session.commit()
        # Re-propagate company evidence_confidence/verification_status from leads.
        run_company_pipeline(session, provenance=DataProvenance.REAL)
        print(f"verified {verified} real lead(s); company evidence re-propagated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
