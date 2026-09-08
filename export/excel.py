"""Build the real-data Excel workbook (Prompt 45).

Every sheet is populated from the actual database via the same models the APIs use
(§43). Empty tables get their headers + an honest "No real data available yet."
note — never fabricated rows (§42). Text cells are sanitised against
formula-injection (§33); no secrets are ever written (§32). Source URLs become
clickable hyperlinks where present (§30/§31).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from io import BytesIO
from typing import Callable, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import (
    AIIntelligenceResult,
    Alert,
    BusinessSignal,
    CRMActivity,
    CollectionRun,
    Company,
    DecisionMaker,
    EvidenceRecord,
    JobRecord,
    JobSourceReference,
    Lead,
    OpportunityCandidate,
    OutreachDraft,
    SalesOpportunity,
    utcnow,
)

# Safety caps (§38/§39): bound memory + rows per sheet.
MAX_ROWS_PER_SHEET = 100_000
_BATCH = 500

_HEADER_FILL = PatternFill("solid", fgColor="1F2937")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_WRAP = Alignment(vertical="top", wrap_text=True)
_DANGEROUS = ("=", "+", "-", "@")


def _safe(value):
    """Coerce a DB value to a spreadsheet-safe cell value. Neutralises
    formula-injection on strings; formats dates; joins lists."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value
    if hasattr(value, "value"):  # enum
        value = value.value
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    text = str(value)
    # Formula-injection protection (§33): prefix a leading control char with '.
    if text and (text[0] in _DANGEROUS or text[0] in ("\t", "\r")):
        text = "'" + text
    return text


def _is_url(value) -> bool:
    return isinstance(value, str) and (value.startswith("http://") or value.startswith("https://"))


@dataclass
class Column:
    header: str
    get: Callable
    is_url: bool = False


@dataclass
class Sheet:
    name: str
    columns: list[Column]
    rows: Callable[[Session], Iterable]   # yields ORM objects / tuples


def _count(session: Session, model) -> int:
    return int(session.execute(select(func.count()).select_from(model)).scalar() or 0)


def _batched(session: Session, stmt):
    """Yield ORM rows in batches, capped, to avoid loading whole tables."""
    stmt = stmt.limit(MAX_ROWS_PER_SHEET)
    result = session.execute(stmt.execution_options(yield_per=_BATCH))
    for row in result:
        yield row[0] if len(row) == 1 else row


# --------------------------------------------------------------------------- #
# Sheet definitions (only real, stored entities).
# --------------------------------------------------------------------------- #
def _sheets() -> list[Sheet]:
    C = Column
    return [
        Sheet("Companies", [
            C("Company ID", lambda o: o.id),
            C("Canonical Name", lambda o: o.canonical_name),
            C("Legal Name", lambda o: o.legal_name),
            C("Website", lambda o: o.website, is_url=True),
            C("Primary Domain", lambda o: o.primary_domain),
            C("Industry", lambda o: o.industry),
            C("Company Type", lambda o: o.company_type),
            C("HQ Country", lambda o: o.headquarters_country),
            C("HQ City", lambda o: o.headquarters_city),
            C("India Presence", lambda o: o.india_presence),
            C("India Locations", lambda o: o.india_locations),
            C("Employee Count", lambda o: o.employee_count),
            C("Employee Count Source", lambda o: o.employee_count_source),
            C("Identity Confidence", lambda o: o.identity_confidence),
            C("Evidence Confidence", lambda o: o.evidence_confidence),
            C("Verification Status", lambda o: o.verification_status),
            C("Provenance", lambda o: o.data_provenance),
            C("First Seen", lambda o: o.first_seen_at),
            C("Last Seen", lambda o: o.last_seen_at),
        ], lambda s: _batched(s, select(Company).order_by(Company.id))),

        Sheet("Canonical Jobs", [
            C("Canonical Job ID", lambda o: o.id),
            C("Company", lambda o: o.company_name),
            C("Canonical Title", lambda o: o.normalized_title or o.original_job_title),
            C("Role", lambda o: o.normalized_role),
            C("Technologies", lambda o: o.technologies),
            C("City", lambda o: o.city),
            C("State", lambda o: o.state),
            C("Country", lambda o: o.country),
            C("Remote Type", lambda o: o.remote_type),
            C("Employment Type", lambda o: o.employment_type),
            C("Experience", lambda o: o.experience_level),
            C("Status", lambda o: o.job_status),
            C("Source Reference Count", lambda o: o.source_count),
            C("Primary Source", lambda o: o.primary_source),
            C("Published", lambda o: o.published_at),
            C("First Seen", lambda o: o.first_seen_at),
            C("Last Seen", lambda o: o.last_seen_at),
            C("Content Hash", lambda o: o.content_hash),
            C("Provenance", lambda o: o.data_provenance),
        ], lambda s: _batched(s, select(JobRecord).order_by(JobRecord.id))),

        Sheet("Job Source Listings", [
            C("Reference ID", lambda o: o.id),
            C("Canonical Job ID", lambda o: o.job_record_id),
            C("Source", lambda o: o.source_id),
            C("Source Record ID", lambda o: o.external_id),
            C("Source URL", lambda o: o.source_url, is_url=True),
            C("Primary Source", lambda o: o.is_primary_source),
            C("Source Confidence", lambda o: o.source_confidence),
            C("Published", lambda o: o.published_at),
            C("Observed At", lambda o: o.observed_at),
        ], lambda s: _batched(s, select(JobSourceReference).order_by(JobSourceReference.id))),

        Sheet("Signals", [
            C("Signal ID", lambda o: o.id),
            C("Company", lambda o: o.company_name),
            C("Signal Type", lambda o: o.signal_type),
            C("Title", lambda o: o.signal_title),
            C("Description", lambda o: o.signal_description),
            C("Technologies", lambda o: o.technology_terms),
            C("Project", lambda o: o.project_name),
            C("Signal Strength", lambda o: o.signal_strength),
            C("Commercial Intent", lambda o: o.commercial_intent),
            C("Evidence Confidence", lambda o: o.evidence_confidence),
            C("Published", lambda o: o.published_at),
            C("Collected At", lambda o: o.collected_at),
            C("Source", lambda o: o.source_id),
            C("Source URL", lambda o: o.signal_url, is_url=True),
            C("Provenance", lambda o: o.data_provenance),
        ], lambda s: _batched(s, select(BusinessSignal).order_by(BusinessSignal.id))),

        Sheet("Evidence", [
            C("Evidence ID", lambda o: o.id),
            C("Company", lambda o: o.company_normalized_name),
            C("Lead ID", lambda o: o.lead_id),
            C("Evidence Type", lambda o: o.evidence_type),
            C("Source", lambda o: o.source_name),
            C("Source Category", lambda o: o.source_category),
            C("Source Tier", lambda o: o.source_tier),
            C("Source URL", lambda o: o.source_url, is_url=True),
            C("Published At", lambda o: o.published_at),
            C("Observed At", lambda o: o.observed_at),
            C("Last Verified At", lambda o: o.last_verified_at),
            C("Source Reliability", lambda o: o.source_reliability_score),
            C("Freshness Score", lambda o: o.freshness_score),
            C("Corroboration Score", lambda o: o.corroboration_score),
            C("Evidence Confidence", lambda o: o.evidence_confidence),
            C("Verification Status", lambda o: o.verification_status),
            C("Provenance", lambda o: o.data_provenance),
        ], lambda s: _batched(s, select(EvidenceRecord).order_by(EvidenceRecord.id))),

        Sheet("Opportunities", [
            C("Opportunity ID", lambda o: o.id),
            C("Company", lambda o: o.company_name),
            C("Lead ID", lambda o: o.lead_id),
            C("Opportunity Types", lambda o: o.opportunity_types),
            C("IT Job Count", lambda o: o.it_job_count),
            C("Hiring Intensity", lambda o: o.hiring_intensity),
            C("Top Technologies", lambda o: o.top_technologies),
            C("Total Signals", lambda o: o.total_business_signals),
            C("Confidence", lambda o: o.confidence),
            C("Evidence Confidence", lambda o: o.evidence_confidence),
            C("Reason", lambda o: o.reason),
            C("Status", lambda o: o.status),
            C("Provenance", lambda o: o.data_provenance),
            C("Created At", lambda o: o.created_at),
        ], lambda s: _batched(s, select(OpportunityCandidate).order_by(OpportunityCandidate.id))),

        Sheet("Sales Opportunities", [
            C("ID", lambda o: o.id),
            C("Company ID", lambda o: o.company_id),
            C("Lead ID", lambda o: o.lead_id),
            C("Title", lambda o: o.title),
            C("Type", lambda o: o.opportunity_type),
            C("Stage", lambda o: o.stage),
            C("Estimated Value", lambda o: o.estimated_value),
            C("Currency", lambda o: o.estimated_value_currency),
            C("Value Source", lambda o: o.value_source),
            C("Probability", lambda o: o.probability),
            C("Confidence", lambda o: o.confidence),
            C("Owner", lambda o: o.owner),
            C("Created At", lambda o: o.created_at),
            C("Updated At", lambda o: o.updated_at),
        ], lambda s: _batched(s, select(SalesOpportunity).order_by(SalesOpportunity.id))),

        Sheet("Leads", [
            C("Lead ID", lambda o: o.id),
            C("Company", lambda o: o.company_name),
            C("Industry", lambda o: o.industry),
            C("Location", lambda o: o.location),
            C("Lead Score", lambda o: o.lead_score),
            C("Priority", lambda o: o.lead_priority),
            C("Status", lambda o: o.status),
            C("Signal Type", lambda o: o.signal_type),
            C("Signal Title", lambda o: o.signal_title),
            C("IT Job Count", lambda o: o.it_job_count),
            C("Estimated Hiring", lambda o: o.estimated_hiring),
            C("Technologies", lambda o: o.technologies),
            C("Target Role", lambda o: o.primary_target_role),
            C("Recommended Action", lambda o: o.recommended_action),
            C("Evidence Confidence", lambda o: o.evidence_confidence),
            C("Source Reliability", lambda o: o.source_reliability),
            C("Verification Status", lambda o: o.verification_status),
            C("Outreach Readiness", lambda o: o.lead_readiness),
            C("Company Website", lambda o: o.company_website, is_url=True),
            C("Source", lambda o: o.source_name),
            C("Source URL", lambda o: o.source_url, is_url=True),
            C("Provenance", lambda o: o.data_provenance),
            C("Created At", lambda o: o.created_at),
            C("Updated At", lambda o: o.updated_at),
        ], lambda s: _batched(s, select(Lead).order_by(Lead.lead_score.desc(), Lead.id))),

        Sheet("Contacts", [
            C("Contact ID", lambda o: o.id),
            C("Company", lambda o: o.company_name),
            C("Full Name", lambda o: o.full_name),
            C("Job Title", lambda o: o.job_title),
            C("Normalized Role", lambda o: o.normalized_role),
            C("Department", lambda o: o.department),
            C("Geography", lambda o: o.geography),
            C("Business Email", lambda o: o.business_email),
            C("Business Phone", lambda o: o.business_phone),
            C("Profile URL", lambda o: o.profile_url, is_url=True),
            C("Contact Source", lambda o: o.contact_source),
            C("Source URL", lambda o: o.source_url, is_url=True),
            C("Identity Confidence", lambda o: o.identity_confidence),
            C("Contact Confidence", lambda o: o.contact_confidence),
            C("Email Status", lambda o: o.email_status),
            C("Verification Status", lambda o: o.verification_status),
            C("Last Verified", lambda o: o.last_verified_at),
            C("Provenance", lambda o: o.data_provenance),
        ], lambda s: _batched(s, select(DecisionMaker).order_by(DecisionMaker.id))),

        Sheet("CRM Activities", [
            C("Activity ID", lambda o: o.id),
            C("Lead ID", lambda o: o.lead_id),
            C("Company ID", lambda o: o.company_id),
            C("Contact ID", lambda o: o.contact_id),
            C("Opportunity ID", lambda o: o.opportunity_id),
            C("Activity Type", lambda o: o.activity_type),
            C("Direction", lambda o: o.direction),
            C("Subject", lambda o: o.subject),
            C("Status", lambda o: o.status),
            C("System Event", lambda o: o.is_system_event),
            C("Source", lambda o: o.source),
            C("External ID", lambda o: o.external_id),
            C("Occurred At", lambda o: o.occurred_at),
            C("Created By", lambda o: o.created_by),
        ], lambda s: _batched(s, select(CRMActivity).order_by(CRMActivity.id))),

        Sheet("Outreach", [
            C("Outreach ID", lambda o: o.id),
            C("Lead ID", lambda o: o.lead_id),
            C("Company ID", lambda o: o.company_id),
            C("Contact ID", lambda o: o.contact_id),
            C("Target Role", lambda o: o.target_role),
            C("Channel", lambda o: o.channel),
            C("Subject", lambda o: o.subject),
            C("Message", lambda o: o.message),
            C("Grounded", lambda o: o.grounding_ok),
            C("AI Generated", lambda o: o.ai_generated),
            C("Confidence", lambda o: o.confidence),
            C("Status", lambda o: o.status),
            C("Provider", lambda o: o.provider),
            C("Created At", lambda o: o.created_at),
            C("Approved At", lambda o: o.approved_at),
            C("Sent At", lambda o: o.sent_at),
            C("Evidence IDs", lambda o: o.evidence_ids),
        ], lambda s: _batched(s, select(OutreachDraft).order_by(OutreachDraft.id))),

        Sheet("Alerts", [
            C("Alert ID", lambda o: o.id),
            C("Alert Type", lambda o: o.alert_type),
            C("Severity", lambda o: o.severity),
            C("Company ID", lambda o: o.company_id),
            C("Lead ID", lambda o: o.lead_id),
            C("Opportunity ID", lambda o: o.opportunity_id),
            C("Title", lambda o: o.title),
            C("Message", lambda o: o.message),
            C("Status", lambda o: o.status),
            C("Triggered At", lambda o: o.triggered_at),
            C("Evidence IDs", lambda o: o.evidence_ids),
        ], lambda s: _batched(s, select(Alert).order_by(Alert.id))),

        Sheet("AI Intelligence", [
            C("AI ID", lambda o: o.id),
            C("Subject Type", lambda o: o.subject_type),
            C("Subject ID", lambda o: o.subject_id),
            C("Company ID", lambda o: o.company_id),
            C("Lead ID", lambda o: o.lead_id),
            C("Executive Summary", lambda o: o.executive_summary),
            C("Verified Facts", lambda o: _claims(o.verified_facts)),
            C("Inferred Insights", lambda o: _claims(o.inferred_insights)),
            C("Unknowns", lambda o: o.unknowns),
            C("Recommended Action", lambda o: o.recommended_action),
            C("Next Best Action", lambda o: o.next_best_action),
            C("Sales Angle", lambda o: o.sales_angle),
            C("Risk Flags", lambda o: o.risk_flags),
            C("AI Confidence", lambda o: o.confidence),
            C("Analysis Status", lambda o: o.analysis_status),
            C("Model", lambda o: o.model_name),
            C("Prompt Version", lambda o: o.prompt_version),
            C("Generated At", lambda o: o.generated_at),
            C("Evidence IDs", lambda o: o.evidence_ids),
        ], lambda s: _batched(s, select(AIIntelligenceResult).order_by(AIIntelligenceResult.id))),

        Sheet("Ingestion Runs", [
            C("Run ID", lambda o: o.id),
            C("Source", lambda o: o.source_id),
            C("Query", lambda o: o.query),
            C("Status", lambda o: o.status),
            C("Started", lambda o: o.started_at),
            C("Completed", lambda o: o.completed_at),
            C("Duration (s)", lambda o: o.duration_seconds),
            C("Pages", lambda o: o.pages),
            C("Records Fetched", lambda o: o.records_fetched),
            C("Records Created", lambda o: o.records_created),
            C("Records Updated", lambda o: o.records_updated),
            C("Duplicates", lambda o: o.duplicates),
            C("Errors", lambda o: o.errors),
        ], lambda s: _batched(s, select(CollectionRun).order_by(CollectionRun.id.desc()))),
    ]


def _claims(claims) -> str:
    """Render AI claim dicts as 'text [FACT]' lines, preserving FACT vs INFERENCE."""
    if not claims:
        return ""
    out = []
    for c in claims:
        if isinstance(c, dict):
            out.append(f"{c.get('claim_text', '')} [{c.get('claim_type', '')}]".strip())
        else:
            out.append(str(c))
    return "\n".join(out)


# Scope → sheet-name subset (primary is "all").
_SCOPES = {
    "leads": {"Leads"}, "companies": {"Companies"}, "jobs": {"Canonical Jobs", "Job Source Listings"},
    "opportunities": {"Opportunities", "Sales Opportunities"}, "contacts": {"Contacts"},
}


def workbook_counts(session: Session) -> dict:
    """Actual counts for the README (never hard-coded)."""
    return {
        "Companies": _count(session, Company),
        "Canonical Jobs": _count(session, JobRecord),
        "Job Source Listings": _count(session, JobSourceReference),
        "Signals": _count(session, BusinessSignal),
        "Evidence": _count(session, EvidenceRecord),
        "Opportunities": _count(session, OpportunityCandidate),
        "Sales Opportunities": _count(session, SalesOpportunity),
        "Leads": _count(session, Lead),
        "Contacts": _count(session, DecisionMaker),
        "CRM Activities": _count(session, CRMActivity),
        "Outreach": _count(session, OutreachDraft),
        "Alerts": _count(session, Alert),
        "AI Intelligence": _count(session, AIIntelligenceResult),
        "Ingestion Runs": _count(session, CollectionRun),
    }


def build_workbook(session: Session, *, scope: str = "all", now: datetime | None = None,
                   timezone_label: str = "Asia/Kolkata") -> tuple[BytesIO, dict]:
    """Build the .xlsx in memory. Returns (BytesIO, metadata). Metadata includes
    actual per-sheet row counts and total rows exported."""
    now = now or utcnow()
    wb = Workbook()
    wb.remove(wb.active)   # drop default sheet; we add our own

    counts = workbook_counts(session)
    all_sheets = _sheets()
    scope = (scope or "all").lower()
    wanted = _SCOPES.get(scope)   # None → all
    sheets = [s for s in all_sheets if (wanted is None or s.name in wanted)]

    # README + Data Dictionary first.
    _write_readme(wb, counts, now, timezone_label, scope)
    _write_data_dictionary(wb, sheets)

    exported: dict[str, int] = {}
    for sheet in sheets:
        n = _write_sheet(wb, sheet, session)
        exported[sheet.name] = n

    # Sources sheet (from the source inventory helper; never secrets).
    _write_sources(wb, session)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    meta = {
        "scope": scope,
        "generated_at": now.isoformat(),
        "sheets": list(wb.sheetnames),
        "rows_by_sheet": exported,
        "total_rows": sum(exported.values()),
        "counts": counts,
    }
    return buffer, meta


def _style_header(ws, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"
    if ncols:
        ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}1"


def _autosize(ws, headers: list[str], sample_widths: list[int]) -> None:
    for i, header in enumerate(headers, start=1):
        width = max(len(header) + 2, sample_widths[i - 1] if i - 1 < len(sample_widths) else 10)
        ws.column_dimensions[get_column_letter(i)].width = min(max(width, 10), 60)


def _write_sheet(wb: Workbook, sheet: Sheet, session: Session) -> int:
    ws = wb.create_sheet(title=sheet.name[:31])
    headers = [c.header for c in sheet.columns]
    ws.append(headers)
    widths = [len(h) for h in headers]

    count = 0
    for obj in sheet.rows(session):
        row_vals = []
        for ci, col in enumerate(sheet.columns):
            try:
                raw = col.get(obj)
            except Exception:
                raw = None
            val = _safe(raw)
            row_vals.append(val)
            if isinstance(val, str):
                widths[ci] = max(widths[ci], min(len(val), 60))
        ws.append(row_vals)
        count += 1
        # Hyperlink URL columns.
        for ci, col in enumerate(sheet.columns, start=1):
            if col.is_url:
                cell = ws.cell(row=count + 1, column=ci)
                if _is_url(cell.value):
                    cell.hyperlink = cell.value
                    cell.style = "Hyperlink"

    if count == 0:
        ws.append(["No real data available yet." ] + [None] * (len(headers) - 1))
    _style_header(ws, len(headers))
    _autosize(ws, headers, widths)
    return count


def _write_readme(wb: Workbook, counts: dict, now: datetime, tz: str, scope: str) -> None:
    ws = wb.create_sheet(title="README")
    rows = [
        ["LeadGenerationAgent — Real Data Export"],
        [],
        ["Export timestamp (UTC)", now.isoformat()],
        ["Display timezone", tz],
        ["Export scope", scope],
        [],
        ["Entity", "Total records (actual)"],
    ]
    for name, n in counts.items():
        rows.append([name, n])
    rows += [
        [],
        ["Data Policy",
         "Business records in this workbook are exported from the application database "
         "and retain their source/provenance information. This is REAL data only — no "
         "demo, dummy, synthetic, or fabricated records are included."],
    ]
    for r in rows:
        ws.append([_safe(v) for v in r])
    ws["A1"].font = Font(bold=True, size=14)
    ws["A7"].font = _HEADER_FONT
    ws["B7"].font = _HEADER_FONT
    ws["A7"].fill = _HEADER_FILL
    ws["B7"].fill = _HEADER_FILL
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 90


_DICT_ROWS = [
    ("(all)", "Provenance", "REAL = collected from a permitted real source", "text", "system", "no",
     "Synthetic never appears in production exports"),
    ("Leads", "Lead Score", "0-100 composite intent score", "number", "scoring", "no",
     "Distinct from Evidence Confidence and AI Confidence"),
    ("Leads", "Evidence Confidence", "0-100 strength of source-backed evidence", "number", "verification",
     "no", "Not the same as lead score"),
    ("Leads", "Outreach Readiness", "READY / ROLE_ONLY / RESEARCH_REQUIRED / HOLD", "text", "verification",
     "no", ""),
    ("Evidence", "Source URL", "Clickable link to the originating source", "url", "collector", "yes",
     "Provenance; some aggregator evidence carries source name not URL"),
    ("Contacts", "Business Email", "Source-published business email only", "text", "enrichment", "yes",
     "Never guessed/constructed"),
    ("AI Intelligence", "Verified Facts", "FACT claims, each tagged [FACT], cite evidence", "text", "ai",
     "yes", "AI never becomes source of truth"),
    ("Sales Opportunities", "Estimated Value", "Only when user- or evidence-sourced", "number", "crm",
     "yes", "Never inferred/fabricated"),
]


def _write_data_dictionary(wb: Workbook, sheets: list[Sheet]) -> None:
    ws = wb.create_sheet(title="Data Dictionary")
    headers = ["Sheet", "Field", "Description", "Data Type", "Source", "Nullable", "Notes"]
    ws.append(headers)
    for r in _DICT_ROWS:
        ws.append([_safe(v) for v in r])
    _style_header(ws, len(headers))
    for i, w in enumerate([20, 22, 44, 12, 12, 10, 40], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _write_sources(wb: Workbook, session: Session) -> None:
    from app.source_inventory import source_inventory
    ws = wb.create_sheet(title="Sources")
    headers = ["Source ID", "Provider", "Category", "Implementation", "Configuration",
               "Connection", "Reliability Tier", "Capabilities", "Last Success", "Last Failure",
               "Licensing", "Documentation URL", "Terms URL"]
    ws.append(headers)
    for s in source_inventory(session):
        ws.append([_safe(s.get(k)) for k in (
            "source_id", "provider", "category", "implementation", "configuration_status",
            "connection_status", "reliability_tier", "capabilities", "last_success_at",
            "last_failure_at", "commercial_use_status", "documentation_url", "terms_url")])
    # Hyperlink doc/terms URL columns (12, 13).
    for r in range(2, ws.max_row + 1):
        for c in (12, 13):
            cell = ws.cell(row=r, column=c)
            if _is_url(cell.value):
                cell.hyperlink = cell.value
                cell.style = "Hyperlink"
    _style_header(ws, len(headers))
    _autosize(ws, headers, [len(h) for h in headers])
