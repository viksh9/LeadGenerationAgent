#!/usr/bin/env python3
"""Audit the database for real-data-only compliance (and optionally clean it).

Reports, for every business table:
  - total / real / synthetic record counts
  - records missing provenance
  - REAL records missing a source URL

This is the operational check that the platform remains real-data-only. It reads
the database only; nothing is fabricated. Use ``--purge-synthetic`` to remove any
lingering synthetic/demo records (development/test environments only) in
foreign-key-safe order — it never deletes real data and never touches schema.

Usage:
    python scripts/db_audit.py                     # print an audit report
    python scripts/db_audit.py --json              # machine-readable report
    python scripts/db_audit.py --fail-on-synthetic # exit 1 if any synthetic found
    python scripts/db_audit.py --purge-synthetic --yes   # remove synthetic records
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import get_settings  # noqa: E402
from database.integrity import audit_database, purge_synthetic  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402

SAFE_ENVIRONMENTS = {"development", "test", "local"}


def _report_dict(audit) -> dict:
    return {
        "total_records": audit.total_records,
        "synthetic_total": audit.synthetic_total,
        "missing_provenance_total": audit.missing_provenance_total,
        "is_clean": audit.is_clean,
        "entities": [
            {
                "table": e.table, "total": e.total, "real": e.real,
                "synthetic": e.synthetic, "missing_provenance": e.missing_provenance,
                "missing_source": e.missing_source,
            }
            for e in audit.entities
        ],
    }


def _print_report(audit) -> None:
    print("Database audit — real-data-only compliance")
    print(f"  Total business records: {audit.total_records}")
    print(f"  Synthetic/demo records: {audit.synthetic_total}")
    print(f"  Missing provenance:     {audit.missing_provenance_total}")
    print(f"  Clean (real-data-only): {'YES' if audit.is_clean else 'NO'}")
    print()
    header = f"  {'table':32}{'total':>7}{'real':>7}{'synth':>7}{'no_prov':>9}{'no_src':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for e in audit.entities:
        if e.total == 0:
            continue
        print(f"  {e.table:32}{e.total:>7}{e.real:>7}{e.synthetic:>7}"
              f"{e.missing_provenance:>9}{e.missing_source:>8}")
    if audit.total_records == 0:
        print("  (database is empty — a valid real-data-only state)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the database for real-data-only compliance.")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable JSON report.")
    parser.add_argument("--fail-on-synthetic", action="store_true",
                        help="Exit non-zero if any synthetic/demo or provenance-less record exists.")
    parser.add_argument("--purge-synthetic", action="store_true",
                        help="Delete synthetic/demo records (development/test only).")
    parser.add_argument("--yes", action="store_true", help="Confirm --purge-synthetic without prompting.")
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        if args.purge_synthetic:
            env = (settings.environment or "").lower()
            if env not in SAFE_ENVIRONMENTS:
                print(f"Refusing to purge in environment '{env or '(unset)'}'. "
                      f"Purge only runs against development/test data.")
                return 1
            if not args.yes:
                print("Pass --yes with --purge-synthetic to confirm deleting synthetic records.")
                return 1
            removed = purge_synthetic(session)
            total = sum(removed.values())
            print(f"Purged {total} synthetic/demo record(s):")
            for table, count in sorted(removed.items()):
                print(f"  {table}: {count}")
            if not removed:
                print("  (nothing to purge — no synthetic records found)")
            print()

        audit = audit_database(session)

    if args.json:
        print(json.dumps(_report_dict(audit), indent=2))
    else:
        _print_report(audit)

    if args.fail_on_synthetic and not audit.is_clean:
        print("\nFAIL: database contains synthetic/demo or provenance-less records.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
