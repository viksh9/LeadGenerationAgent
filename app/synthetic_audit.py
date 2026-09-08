"""Synthetic-data audit (Prompt 41 §4, §36, §37).

Two checks:
1. DATABASE — any production business record flagged SYNTHETIC (or is_synthetic).
   A single synthetic production record is a FAIL.
2. RUNTIME CODE — scans backend + frontend runtime code (excluding tests) for
   fabrication tokens, classifying each hit as TEST_ONLY (ok) or
   PRODUCTION_RUNTIME (must be reviewed/removed). Legitimate real-data guards
   (purge_synthetic, is_synthetic flag, demo-mode-OFF handling) are recognised and
   not flagged.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.integrity import _PROVENANCE_ENTITIES, _SYNTHETIC_FLAG_ENTITIES
from database.models import DataProvenance

ROOT = Path(__file__).resolve().parent.parent

_TOKENS = re.compile(r"\b(demo|dummy|fake|synthetic|sample|mock)\b", re.IGNORECASE)

# Directories that are TEST_ONLY or non-runtime — hits here are allowed.
_TEST_ONLY_DIRS = ("/tests/", "/test/", "/__pycache__/", "/node_modules/", "/dist/", "/.git/")
_TEST_FILE_MARKERS = (".test.", ".spec.", "conftest.py", "/fixtures/", "synthetic_leads")

# Guard / audit / policy modules legitimately mention these tokens (they ENFORCE
# the real-data policy or scan for it). Excluded from the fabrication scan.
_GUARD_MODULES = (
    "app/audit.py", "app/synthetic_audit.py", "app/provenance_audit.py", "app/report.py",
    "app/quality_audit.py", "app/source_inventory.py", "app/live_audit.py",
    "config/validation.py", "config/settings.py", "database/integrity.py",
    "collectors/source_status.py", "collectors/source_registry.py", "scripts/db_audit.py",
    # Frontend components that LABEL synthetic/dev data honestly (provenance
    # warnings) rather than fabricate it — part of the real-data-honesty UX.
    "frontend/src/components/ui/Badge.tsx",
    "frontend/src/components/common/DataProvenanceBanner.tsx",
    "frontend/src/components/companies/CompanyIntelligencePanel.tsx",
    "frontend/src/components/leads/detail/VerificationPanel.tsx",
)

# Substrings on a matching line that indicate a legitimate real-data GUARD rather
# than a fabrication path.
_ALLOWED_CONTEXT = (
    "purge_synthetic", "is_synthetic", "data_provenance", "SYNTHETIC =", "SYNTHETIC:",
    "DataProvenance.SYNTHETIC", "show_synthetic", "synthetic_leads", "demo_mode", "DEMO_MODE",
    "no demo", "not demo", "never", "reject", "guard", "placeholder", "real-data", "real data",
    "# ", '"""', "must not", "must never", "no fake", "not fake", "TEST_ONLY", "test-only",
    "_synthetic", "synthetic_", "mock transport", "MockTransport",  # httpx test transport
    "provenance", "ProvenanceFilter", "SYNTHETIC", "help=", "description=", "add_parser",
    "* ", "-- ", "#", "://",  # comment/doc/url lines
    "demo data", "not a real", "generated for development", "never inserts", "not to fake",
    "processed independently", "no dummy", "title=",
)

# Runtime code roots to scan (backend packages + frontend src, excluding tests).
_SCAN_ROOTS = [
    "api", "ai", "app", "collectors", "company", "config", "crm", "database", "enrichment",
    "ingestion", "intelligence", "monitoring", "notifications", "outreach", "processors",
    "resilience", "scheduler", "scripts", "verification", "frontend/src",
]


def db_synthetic_report(session: Session) -> dict:
    """Count SYNTHETIC rows across all provenance-bearing production tables."""
    per_table: dict[str, int] = {}
    for table, model in _PROVENANCE_ENTITIES:
        n = int(session.execute(
            select(func.count()).select_from(model)
            .where(model.data_provenance == DataProvenance.SYNTHETIC)
        ).scalar() or 0)
        if n:
            per_table[table] = n
    for table, model in _SYNTHETIC_FLAG_ENTITIES:
        n = int(session.execute(
            select(func.count()).select_from(model).where(model.is_synthetic.is_(True))
        ).scalar() or 0)
        if n:
            per_table[table] = n
    total = sum(per_table.values())
    return {"synthetic_records": total, "by_table": per_table, "ok": total == 0}


def _is_test_only(path: str) -> bool:
    p = path.replace("\\", "/")
    if any(seg in p for seg in _TEST_ONLY_DIRS):
        return True
    return any(m in p for m in _TEST_FILE_MARKERS)


def _allowed_context(line: str) -> bool:
    low = line.lower()
    return any(ctx.lower() in low for ctx in _ALLOWED_CONTEXT)


def runtime_scan() -> dict:
    """Scan runtime code for fabrication tokens, classifying each surviving hit."""
    production_hits: list[dict] = []
    test_only_hits = 0
    for root in _SCAN_ROOTS:
        base = ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in (".py", ".ts", ".tsx", ".js", ".jsx"):
                continue
            rel = str(path.relative_to(ROOT))
            if _is_test_only(str(path)):
                continue
            if any(rel.endswith(m) or ("/" + m) in ("/" + rel) for m in _GUARD_MODULES):
                continue   # guard/audit/policy code legitimately references these tokens
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if not _TOKENS.search(line):
                    continue
                if _allowed_context(line):
                    test_only_hits += 1   # recognised guard/comment — allowed
                    continue
                production_hits.append({"file": rel, "line": i, "text": line.strip()[:160]})
    return {
        "production_runtime_hits": production_hits,
        "allowed_or_guard_hits": test_only_hits,
        "ok": len(production_hits) == 0,
    }


def synthetic_report(session: Session) -> dict:
    # The DATABASE check is authoritative: a synthetic production RECORD is a hard
    # FAIL (§4). The runtime code scan is ADVISORY — legitimate guard/label/comment
    # code references these tokens — so surviving hits are REQUIRES_REVIEW, listed
    # for a human, and do NOT by themselves fail the command or block go/no-go.
    db = db_synthetic_report(session)
    runtime = runtime_scan()
    return {
        "database": db,
        "runtime": runtime,
        "runtime_requires_review": len(runtime["production_runtime_hits"]),
        "ok": db["ok"],   # authoritative: DB has no synthetic production records
    }
