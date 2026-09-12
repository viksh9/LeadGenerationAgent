"""Build the real-data lead export (Prompt 47).

The workbook contains EXACTLY ONE worksheet, "Lead Data", with a fixed 16-column
sales report — one row per company-level lead (the Lead table is already the
company-level aggregation from the pipeline, so one Lead == one row; syndicated
jobs are never counted as separate rows). Real data only: only leads with
provenance REAL are exported. Text cells are formula-injection-safe; no secrets;
contacts/emails are only ever the source-verified values (never guessed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import (
    Company,
    ContactType,
    DataProvenance,
    DecisionMaker,
    EmailStatus,
    Lead,
    LeadPriority,
    VerificationStatus,
    utcnow,
)
from intelligence.opportunity_view import derive_opportunity_view, opportunity_cell

SHEET_NAME = "Lead Data"

# Exact column order (§2) — do not rename/add/remove.
COLUMNS: list[tuple[str, int]] = [
    ("Sr No", 8),
    ("Company Name", 30),
    ("No of Openings", 16),
    ("Location", 25),
    ("Intensity", 15),
    ("Signal", 30),
    ("Technology", 30),
    ("Target POC Details", 35),
    ("Score", 10),
    ("Priority", 12),
    ("Status", 18),
    ("Contact Number", 20),
    ("Email", 35),
    ("Opportunity", 42),
    ("Signal Date", 18),
    ("Source", 30),
]
# Signal + Technology get a little more room for combined values (§30).
COLUMNS[5] = ("Signal", 35)
COLUMNS[6] = ("Technology", 35)
HEADERS = [c[0] for c in COLUMNS]

_HEADER_FILL = PatternFill("solid", fgColor="1F2937")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_WRAP = Alignment(vertical="top", wrap_text=True)
_DANGEROUS = ("=", "+", "-", "@")
# A genuine phone number may legitimately start with "+"; openpyxl stores it as a
# string (only "=" becomes a formula), so a strict phone pattern is exempt from the
# apostrophe guard for clean display while arbitrary text is still neutralised.
_PHONE_RE = re.compile(r"^\+?[\d][\d\s\-().]{4,}$")

# Restrained, colour+value (never colour-alone) conditional fills.
_PRIORITY_FILL = {
    "HOT": PatternFill("solid", fgColor="FDE2E1"),
    "WARM": PatternFill("solid", fgColor="FDECC8"),
    "NURTURE": PatternFill("solid", fgColor="E6F0FB"),
    "LOW": PatternFill("solid", fgColor="EEF0F2"),
}
_PRIORITY_RANK = {LeadPriority.HOT: 3, LeadPriority.WARM: 2, LeadPriority.NURTURE: 1, LeadPriority.LOW: 0}
_VERIFIED = {VerificationStatus.VERIFIED, VerificationStatus.PARTIALLY_VERIFIED}


def _safe(value):
    """Formula-injection-safe text/number cell value (§31)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, datetime):
        return value
    if hasattr(value, "value"):
        value = value.value
    text = str(value)
    if _PHONE_RE.match(text):
        return text   # genuine phone number — safe as a string, keep it clean
    if text and (text[0] in _DANGEROUS or text[0] in ("\t", "\r")):
        text = "'" + text
    return text


def _enum(v) -> str:
    return v.value if hasattr(v, "value") else (str(v) if v is not None else "")


def _clean_source(source_name: str | None) -> str:
    """Turn '1 source(s): adzuna' into 'adzuna'; keep concise multi-source lists."""
    if not source_name:
        return ""
    text = source_name.strip()
    if ":" in text and "source" in text.lower():
        text = text.split(":", 1)[1].strip()
    return text


# Readable signal_type labels — mirrors the Opportunities tab (frontend
# constants/leads.ts SIGNAL_LABELS). The tab never shows raw SCREAMING_CASE.
_SIGNAL_LABELS = {
    "HIRING": "Hiring",
    "PROJECT_AWARD": "Project Award",
    "PROJECT_EXECUTION": "Project Execution",
    "EXPANSION": "Expansion",
    "DIGITAL_TRANSFORMATION": "Digital Transformation",
    "TECHNOLOGY_INITIATIVE": "Technology Initiative",
    "VENDOR_REQUIREMENT": "Vendor Requirement",
    "CONTRACT": "Contract",
    "OTHER": "Other",
}


def _humanize_signal(value) -> str:
    """signal_type -> readable label (mirrors frontend humanizeSignal)."""
    v = _enum(value)
    return _SIGNAL_LABELS.get(v, v) if v else ""


def _source_text(lead: Lead, contact_sources: list[str] | None = None) -> str:
    """Cleaned job source, plus any contact source(s) (Official Company Website /
    GitHub / ContactOut) that materially back the shown POC/contact (§33)."""
    base = _clean_source(lead.source_name)
    parts = [base] if base else []
    for src in (contact_sources or []):
        if src and src.lower() not in " ".join(parts).lower():
            parts.append(src)
    return " | ".join(parts)


def _signal_text(lead: Lead) -> str:
    """Signal cell mirroring the Opportunities tab 'Signal' representation:
    the readable signal type, the specific signal title, and confidence.
    Real data only — nothing shown when a field is absent."""
    lines: list[str] = [_humanize_signal(lead.signal_type) or "Not available"]
    title = (lead.signal_title or "").strip()
    if title:
        lines.append(title)
    if lead.signal_confidence is not None:
        lines.append(f"Confidence: {round(float(lead.signal_confidence))}%")
    return "\n".join(lines)


def _tech_text(lead: Lead) -> str:
    techs = [str(t).strip() for t in (lead.technologies or []) if str(t).strip()]
    return " | ".join(dict.fromkeys(techs))   # de-dup, preserve order


def _poc_text(lead: Lead, people: list[DecisionMaker]) -> str:
    """Real people win (up to two — Primary/Secondary, §22/§33); otherwise a
    clearly-labelled recommended role. A person's name is NEVER fabricated (§19)."""
    named = [p for p in people if p.full_name][:2]
    if named:
        lines = []
        for p in named:
            role = p.job_title or p.normalized_role
            lines.append(f"{p.full_name} — {role}" if role else p.full_name)
        return "\n".join(lines)
    if lead.poc_name:
        return f"{lead.poc_name} — {lead.poc_title}" if lead.poc_title else lead.poc_name
    role = lead.primary_target_role
    if role:
        return f"{role} — Recommended Role"
    # Fall back to hiring roles as recommended roles, if any.
    roles = [str(r).strip() for r in (lead.hiring_roles or []) if str(r).strip()]
    if roles:
        return " | ".join(roles[:3]) + " — Recommended Role"
    return ""


def _signal_date(lead: Lead) -> datetime | None:
    return lead.signal_date or lead.last_signal_date


def eligible_leads_query():
    """Real leads only, sorted for sales usefulness (priority desc, score desc,
    signal date desc)."""
    return (
        select(Lead)
        .where(Lead.data_provenance == DataProvenance.REAL)
        .order_by(Lead.lead_priority, Lead.lead_score.desc())  # refined in Python for enum rank
    )


def workbook_counts(session: Session) -> dict:
    """Actual eligible real-lead count (for the export summary/confirmation)."""
    n = int(session.execute(
        select(func.count(Lead.id)).where(Lead.data_provenance == DataProvenance.REAL)
    ).scalar() or 0)
    return {"Leads": n}


@dataclass
class _POCBundle:
    """The real contacts available for one company: ranked people (for Target POC
    Details) plus the best email/phone carriers (which may be the same people)."""

    people: list[DecisionMaker]
    email_contact: DecisionMaker | None
    phone_contact: DecisionMaker | None


_VERIF_RANK = {VerificationStatus.VERIFIED: 2, VerificationStatus.PARTIALLY_VERIFIED: 1}


def _person_key(d: DecisionMaker) -> tuple:
    return (d.match_score or 0, d.contact_trust_score or 0,
            _VERIF_RANK.get(d.verification_status, 0), d.identity_confidence or 0)


def _company_id_map(session: Session) -> dict[str, int]:
    """normalized_company_name -> Company.id (leads carry no company_id, so the
    export must resolve the link by normalized name)."""
    rows = session.execute(select(Company.id, Company.normalized_name)).all()
    return {name: cid for cid, name in rows if name}


def _contacts_by_company(session: Session, company_ids: set[int]) -> dict[int, _POCBundle]:
    """Preload real contacts per company (§35 — no N+1): ranked named people, the best
    real business email, and the best real phone. Only actual stored values are used."""
    ids = {cid for cid in company_ids if cid}
    if not ids:
        return {}
    rows = session.execute(
        select(DecisionMaker).where(DecisionMaker.company_id.in_(ids),
                                    DecisionMaker.data_provenance == DataProvenance.REAL)
    ).scalars().all()
    by_co: dict[int, list[DecisionMaker]] = {}
    for dm in rows:
        by_co.setdefault(dm.company_id, []).append(dm)
    bundles: dict[int, _POCBundle] = {}
    for cid, dms in by_co.items():
        people = sorted([d for d in dms if d.full_name and d.is_current is not False],
                        key=_person_key, reverse=True)
        emailers = sorted(
            [d for d in dms if d.business_email and d.contact_type == ContactType.BUSINESS_EMAIL],
            key=lambda d: ((d.email_status == EmailStatus.VERIFIED_SOURCE,) + _person_key(d)), reverse=True)
        phoners = sorted([d for d in dms if d.business_phone], key=_person_key, reverse=True)
        bundles[cid] = _POCBundle(
            people=people,
            email_contact=emailers[0] if emailers else None,
            phone_contact=phoners[0] if phoners else None,
        )
    return bundles


def build_workbook(session: Session, *, scope: str = "all", now: datetime | None = None,
                   timezone_label: str = "Asia/Kolkata") -> tuple[BytesIO, dict]:
    """Build the single-sheet 'Lead Data' workbook from REAL leads. ``scope`` is
    accepted for API compatibility but the export is always the lead report."""
    now = now or utcnow()
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    ws.append(HEADERS)
    for i, (_, width) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    leads = list(session.execute(eligible_leads_query()).scalars().all())
    # Final sort by priority RANK desc, score desc, signal date desc (§17).
    leads.sort(key=lambda l: (
        _PRIORITY_RANK.get(l.lead_priority, -1),
        float(l.lead_score or 0),
        (_signal_date(l) or datetime.min),
    ), reverse=True)

    # Resolve each lead to its Company entity by normalized name (leads carry no
    # company_id), then preload real contacts for those companies.
    name_map = _company_id_map(session)
    lead_company_id = {
        l.id: (l.company_id or name_map.get(l.normalized_company_name)) for l in leads
    }
    contacts = _contacts_by_company(session, set(lead_company_id.values()))

    row_count = 0
    for idx, lead in enumerate(leads, start=1):
        bundle = contacts.get(lead_company_id.get(lead.id))
        people = bundle.people if bundle else []
        email_dm = bundle.email_contact if bundle else None
        phone_dm = bundle.phone_contact if bundle else None
        # Source hint: note the contact source(s) that materially back the shown
        # POC/contact — e.g. Official Company Website / GitHub / ContactOut (§33).
        shown = people[:2] + [d for d in (email_dm, phone_dm) if d is not None]
        contact_sources = []
        for d in shown:
            src = getattr(d, "contact_source", None)
            if src and src not in contact_sources:
                contact_sources.append(src)
        openings = lead.it_job_count if (lead.it_job_count and lead.it_job_count > 0) else None
        sig_date = _signal_date(lead)
        # Opportunity column: same values as the Opportunity tab (§26) — Type,
        # Staffing, Est. Team (actual estimated_hiring), Urgency — as ONE multi-line
        # cell. Note: Est. Team is NOT the No of Openings above (§6).
        oview = derive_opportunity_view(lead, signal_date=sig_date, now=now)
        values = [
            idx,                                             # Sr No (export row number)
            _safe(lead.company_name),
            openings,                                        # No of Openings (canonical; blank if unknown)
            _safe(lead.location_all or lead.location),   # full city list (compact "+N more" is UI-only)
            _enum(lead.hiring_intensity) or "UNKNOWN",
            _safe(_signal_text(lead)),
            _safe(_tech_text(lead)),
            _safe(_poc_text(lead, people)),
            round(float(lead.lead_score or 0)),
            _enum(lead.lead_priority),
            _enum(lead.status),
            _safe(phone_dm.business_phone if phone_dm else None),   # real returned phone, else blank
            _safe(email_dm.business_email if email_dm else None),   # real business email, else blank
            _safe(opportunity_cell(oview)),                  # multi-line: Type / Staffing / Est. Team / Urgency
            sig_date,                                        # real date object → formatted below
            _safe(_source_text(lead, contact_sources)),
        ]
        ws.append(values)
        row_count += 1
        r = row_count + 1  # sheet row (1 = header)

        # Signal Date format (§19).
        if sig_date is not None:
            ws.cell(row=r, column=15).number_format = "dd-mmm-yyyy"
        # Wrap long text columns.
        for col in (2, 4, 6, 7, 8, 14, 16):
            ws.cell(row=r, column=col).alignment = _WRAP
        # The Opportunity cell has 4 lines — give the row room to show them (§5).
        ws.row_dimensions[r].height = 66
        # Restrained priority fill (value is also present as text → not colour-alone).
        pv = _enum(lead.lead_priority)
        if pv in _PRIORITY_FILL:
            ws.cell(row=r, column=10).fill = _PRIORITY_FILL[pv]
        # Source hyperlink when a URL is available (§33) — no extra column.
        if lead.source_url and str(lead.source_url).startswith(("http://", "https://")):
            cell = ws.cell(row=r, column=16)
            cell.hyperlink = lead.source_url
            cell.style = "Hyperlink"

    if row_count == 0:
        ws.append(["No real lead data available."] + [None] * (len(HEADERS) - 1))

    # Header styling + freeze + filter (§14/§16).
    for c in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{max(2, row_count + 1)}"

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    meta = {
        "scope": "all",
        "generated_at": now.isoformat(),
        "sheets": wb.sheetnames,
        "total_rows": row_count,
    }
    return buffer, meta
