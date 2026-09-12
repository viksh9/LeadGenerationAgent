"""Excel export endpoints (Prompt 45).

Exports REAL database records to a professional .xlsx workbook using the same
models the APIs use (§43). Authenticated + role-guarded server-side (§36),
rate-limited (§38), and every export is audited (§37). No secrets are exported;
text cells are formula-injection-safe (handled in export.excel). Small dataset →
synchronous in-memory generation streamed to the client (§25) — no server-side
file is stored (nothing to leak or expire).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.security import rate_limit, require_role
from config.exceptions import ValidationError
from crm.audit import record_audit
from database.models import UserRole, utcnow
from export.excel import build_workbook, workbook_counts
from export.full_intelligence import build_full_intelligence_workbook

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["export"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ALLOWED_SCOPES = {"all", "leads", "companies", "jobs", "opportunities", "contacts"}

# Exporting ALL lead intelligence requires SALES (or ADMIN). When no ADMIN_API_KEY
# is configured the app is open locally (resolves to ADMIN); once a key is set,
# an unauthenticated caller (default VIEWER) is blocked (§30/§36).
_export_role = require_role(UserRole.SALES)
_export_limit = rate_limit("export_excel", 12)   # at most 12 exports/min process-wide


def _safe_filename(scope: str, now: datetime) -> str:
    # The export is always the single "Lead Data" report.
    return f"leadgenerationagent_lead_data_{now.date().isoformat()}.xlsx"


@router.get("/summary", summary="Counts of what an export would contain (real)")
def export_summary(session: Session = Depends(get_session), role=Depends(_export_role)) -> dict:
    counts = workbook_counts(session)
    return {"counts": counts, "total_records": sum(counts.values())}


@router.get("/excel", summary="Export real data to an Excel workbook (.xlsx)")
def export_excel(
    scope: str = Query("all", description="all | leads | companies | jobs | opportunities | contacts"),
    session: Session = Depends(get_session),
    role=Depends(_export_role),
    _rl=Depends(_export_limit),
) -> StreamingResponse:
    scope = (scope or "all").lower()
    if scope not in _ALLOWED_SCOPES:
        raise ValidationError(f"Invalid export scope '{scope}'. Expected one of {sorted(_ALLOWED_SCOPES)}.")

    now = utcnow()
    buffer, meta = build_workbook(session, scope=scope, now=now)
    filename = _safe_filename(scope, now)

    # Audit the export (§37) — actor, scope, row count; no secrets/values leaked.
    record_audit(session, entity_type="export", action="EXCEL_EXPORT",
                 actor=getattr(role, "value", str(role)), new_value=scope,
                 reason=f"{meta['total_rows']} rows across {len(meta['sheets'])} sheets", now=now)
    session.commit()
    logger.info("excel_export scope=%s rows=%s sheets=%s", scope, meta["total_rows"], len(meta["sheets"]))

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Export-Rows": str(meta["total_rows"]),
        "X-Export-Filename": filename,
    }
    return StreamingResponse(iter([buffer.getvalue()]), media_type=_XLSX_MEDIA, headers=headers)


@router.get("/full-intelligence", summary="Export the FULL intelligence workbook (real data)")
def export_full_intelligence(
    session: Session = Depends(get_session),
    role=Depends(_export_role),
    _rl=Depends(_export_limit),
) -> StreamingResponse:
    """Complete-intelligence export (separate from the fixed 16-column business export,
    which is unchanged). One row per real company-level lead with company/legal/address/
    opportunity/POC fields + per-field source. No secrets exported."""
    now = utcnow()
    buffer, meta = build_full_intelligence_workbook(session, now=now)
    filename = f"leadgenerationagent_full_intelligence_{now.date().isoformat()}.xlsx"
    record_audit(session, entity_type="export", action="FULL_INTELLIGENCE_EXPORT",
                 actor=getattr(role, "value", str(role)),
                 reason=f"{meta['total_rows']} rows, {meta['columns']} columns", now=now)
    session.commit()
    logger.info("full_intelligence_export rows=%s columns=%s", meta["total_rows"], meta["columns"])
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Export-Rows": str(meta["total_rows"]),
        "X-Export-Filename": filename,
    }
    return StreamingResponse(iter([buffer.getvalue()]), media_type=_XLSX_MEDIA, headers=headers)
