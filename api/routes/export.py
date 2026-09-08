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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["export"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ALLOWED_SCOPES = {"all", "leads", "companies", "jobs", "opportunities", "contacts"}

# Any authenticated role may export (read operation); ADMIN always allowed. Open
# locally when no ADMIN_API_KEY is configured (consistent with read endpoints).
_export_role = require_role(UserRole.VIEWER, UserRole.RESEARCHER, UserRole.SALES)
_export_limit = rate_limit("export_excel", 12)   # at most 12 exports/min process-wide


def _safe_filename(scope: str, now: datetime) -> str:
    scope_slug = re.sub(r"[^a-z0-9]+", "_", scope.lower()).strip("_") or "all"
    return f"leadgenerationagent_{scope_slug}_data_{now.date().isoformat()}.xlsx"


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
