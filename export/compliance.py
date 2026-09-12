"""Export real-data compliance check (Prompt 55, §24).

Scans the ACTUAL rows of a generated export workbook for two classes of problem:

  1. Obvious demo/synthetic markers (example.com, john doe, "test company", dummy,
     placeholder, all-zero/sequential phone numbers, …). Patterns are word/phrase
     anchored so legitimate real company names that merely *contain* a substring
     (e.g. "Testbook", "Sample Labs") are NOT rejected — §24 explicitly warns against
     blind string filtering.
  2. Missing provenance: a real exported lead row must carry at least one real source
     (Primary Source / Source URL / Supporting Sources). String matching alone is not
     sufficient for correctness (§24), so provenance is validated too.

This never mutates or deletes data — it reports violations for a human to investigate.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional

import openpyxl

# Demo/synthetic markers — anchored to whole words/phrases/domains to avoid flagging
# legitimate real names. Each entry is (label, compiled-regex).
_MARKERS: list[tuple[str, re.Pattern]] = [
    ("example-domain", re.compile(r"\bexample\.(?:com|org|net)\b", re.I)),
    ("placeholder-email", re.compile(r"\b(?:test|demo|dummy|sample|placeholder|foo|bar)@", re.I)),
    ("john-doe", re.compile(r"\bjohn\s+doe\b", re.I)),
    ("jane-doe", re.compile(r"\bjane\s+doe\b", re.I)),
    ("test-company", re.compile(r"\b(?:test|demo|dummy|sample|fake|placeholder)\s+(?:company|corp|inc|ltd|pvt)\b", re.I)),
    ("acme-placeholder", re.compile(r"\bacme\s+(?:corp|corporation|inc|co)\b", re.I)),
    ("lorem-ipsum", re.compile(r"\blorem\s+ipsum\b", re.I)),
    ("standalone-placeholder", re.compile(r"\bplaceholder\b", re.I)),
    ("sequential-phone", re.compile(r"(?<!\d)1234567890(?!\d)")),
    ("zero-phone", re.compile(r"(?<!\d)0{10}(?!\d)")),
]

# Fields that must trace to a real source for a real lead (any one is sufficient).
_PROVENANCE_FIELDS = ("Source", "Source URL", "Supporting Sources", "Primary Source")


@dataclass
class ComplianceViolation:
    row: int                       # 1-based data row index (excludes header)
    company: Optional[str]
    kind: str                      # "demo-marker" | "missing-provenance"
    detail: str


@dataclass
class ComplianceReport:
    sheet: str
    rows_scanned: int = 0
    violations: list[ComplianceViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict:
        return {
            "sheet": self.sheet, "rows_scanned": self.rows_scanned, "ok": self.ok,
            "violation_count": len(self.violations),
            "violations": [{"row": v.row, "company": v.company, "kind": v.kind, "detail": v.detail}
                           for v in self.violations],
        }


def scan_rows(rows: list[dict], *, sheet: str = "Full Intelligence",
              require_provenance: bool = True) -> ComplianceReport:
    """Scan a list of header->value row dicts. Pure (no DB, no I/O)."""
    report = ComplianceReport(sheet=sheet)
    for i, row in enumerate(rows, start=1):
        report.rows_scanned += 1
        company = str(row.get("Company Name") or "").strip() or None
        for header, value in row.items():
            if value is None:
                continue
            text = str(value)
            for label, pat in _MARKERS:
                if pat.search(text):
                    report.violations.append(ComplianceViolation(
                        row=i, company=company, kind="demo-marker",
                        detail=f"{label} in '{header}': {text[:60]}"))
        if require_provenance:
            has_source = any(str(row.get(f) or "").strip() for f in _PROVENANCE_FIELDS)
            if not has_source:
                report.violations.append(ComplianceViolation(
                    row=i, company=company, kind="missing-provenance",
                    detail="row has no Source / Source URL / Supporting Sources"))
    return report


def _workbook_rows(buffer: io.BytesIO) -> tuple[str, list[dict]]:
    wb = openpyxl.load_workbook(io.BytesIO(buffer.getvalue()), read_only=True)
    ws = wb.active
    values = list(ws.iter_rows(values_only=True))
    if not values:
        return ws.title, []
    headers = list(values[0])
    rows = [dict(zip(headers, r)) for r in values[1:]]
    # Skip the honest "no data" placeholder row the builder emits for an empty DB.
    rows = [r for r in rows if str(r.get("Company Name") or "").strip()
            and "No real lead data" not in str(r.get("Company Name") or "")]
    return ws.title, rows


def check_full_intelligence_export(session, *, now=None) -> ComplianceReport:
    """Build the real Full Intelligence export and scan exactly what would ship."""
    from export.full_intelligence import build_full_intelligence_workbook
    buffer, _meta = build_full_intelligence_workbook(session, now=now)
    sheet, rows = _workbook_rows(buffer)
    return scan_rows(rows, sheet=sheet, require_provenance=True)
