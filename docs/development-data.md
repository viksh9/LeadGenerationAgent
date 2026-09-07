# Development & Test Data (real-data-only policy)

**LeadGenerationAgent is a real-data-only platform.** There is **no** demo, dummy,
sample, or seeded business data in the application or its runtime paths, and there
is no production command that can populate the database with synthetic records.

> **Removed:** the previous `scripts/seed_database.py` and
> `scripts/seed_demo_companies.py` seed commands and the `data/sample_*.json`
> business-data files have been removed. Synthetic data now exists **only** inside
> the test suite. Any older documentation referring to "30/32 synthetic leads",
> "seed data", or "demo companies" describes that removed setup.

## Where synthetic data lives now (test-only)

Synthetic records are confined to the test suite and never reach the application
database or the UI:

- `tests/fixtures/sample_leads.json` — synthetic sample-lead records (fictional
  companies, **role-only** POCs; no real people, emails, or private identifiers).
- `tests/fixtures/synthetic_leads.py` — reusable synthetic lead builders
  (`hot_lead`, `warm_lead`, `project_lead`, `missing_data_lead`, …) exposed as
  pytest fixtures in `tests/integration/conftest.py`.
- `tests/fixtures/seeding.py` — **test-only** seeding helpers (`load_sample_leads`,
  `select_records`, `to_analyze_request`, `seed`, `reset_leads`) that run records
  through the real `LeadAnalysisPipeline` and tag every result
  `DataProvenance.SYNTHETIC`.

These helpers only ever write to **isolated, throwaway per-test SQLite databases**
(see `tests/integration/conftest.py`). They are never imported by application or
runtime code, and the write-guards in `database/integrity.py` reject `SYNTHETIC`
records in production/staging regardless.

## Getting real data into the local database

Instead of seeding, collect real data from a configured, permitted source and run
the pipeline:

```bash
# 1. configure a source (example: Adzuna) in .env — see docs/sources/adzuna.md
#    ADZUNA_APP_ID=... ADZUNA_APP_KEY=...
# 2. collect + process real raw records into leads
python scripts/process_raw.py            # normalize pending raw records → leads
python scripts/build_company_leads.py    # REAL raw jobs → canonical jobs → company leads
```

Until a real source is connected the database stays empty and the UI shows honest
empty states. That is the intended behavior — see [Empty states](#empty-states).

## Auditing / cleaning the database

```bash
python scripts/db_audit.py                      # real-data-only compliance report
python scripts/db_audit.py --fail-on-synthetic  # CI gate: non-zero if not clean
python scripts/db_audit.py --purge-synthetic --yes   # remove synthetic rows (dev/test only)
```

`purge_synthetic` (in `database/integrity.py`) deletes only `SYNTHETIC`-provenance
records (and `is_synthetic` raw records) in foreign-key-safe order — it never
touches real data or schema.

## Empty states

With no collected data:

- Dashboard → "No verified real data available yet."
- Companies → "No companies have been discovered from configured real sources."
- Leads → "No real leads available."
- Opportunities → "No verified opportunities available."

An API failure shows an error state; the UI never substitutes fabricated data.

## Provenance & guards

Every business record carries `data_provenance` (`REAL` in production). Write
guards (`database/integrity.py`) enforce:

- No `SYNTHETIC` records in production/staging.
- A `REAL` lead must have source-backed evidence (`source_url` / `source_name` /
  `source_count` / `evidence`). Generated AI text is never evidence.

The data-integrity tests (`tests/integration/test_real_data_integrity.py`) verify
these invariants, and `scripts/db_audit.py --fail-on-synthetic` gates CI.
