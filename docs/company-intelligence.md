# Company-Level Intelligence Pipeline

The product is **not** a job-listing dashboard. It is an Indian IT-market sales
intelligence system that turns real technology-hiring signals into qualified
staffing / technology-service opportunities. A **company** with 40 open IT roles
is ONE lead, not 40.

## Pipeline

```
REAL JOB SOURCES → collection → RAW JOB RECORDS (raw_source_records)
      → normalization → job dedup → company resolution
      → COMPANY AGGREGATION (intelligence/company_aggregator.py)
      → hiring intensity + technology demand + company signals
      → company scoring (intelligence/company_pipeline.py)
      → ONE company-level Lead per company (with evidence)
      → DASHBOARD (GET /leads, REAL-only in production)
```

Real and synthetic data are kept strictly separate at every stage.

## Data provenance (REAL vs SYNTHETIC)

Every `Lead` carries `data_provenance`:

- **REAL** — built from actually collected job records.
- **SYNTHETIC** — demo/development data, always visibly labelled.

`GET /leads` defaults to **REAL-only in production** (`Settings.synthetic_leads_visible`
is false unless `APP_ENV` is non-production or `SHOW_SYNTHETIC_LEADS=true`). The
`provenance` query param (`real` | `synthetic` | `all`) overrides per request.
The dashboard shows a "Demo data" banner when only synthetic leads are present,
and an honest empty state ("No verified Indian IT signals available yet.") when
no real data is connected. **It is better to show no data than misleading data.**

Because no real collector is connected yet, the production dashboard currently
shows the empty state. The pipeline is exercised only by SYNTHETIC fixtures inside
the test suite (`tests/fixtures/`, isolated per-test databases) — there is no
production seed/demo command, and synthetic records are rejected by the write-guards.

## Company aggregation (`intelligence/company_aggregator.py`)

Groups raw job records by normalized company name and computes:

- `it_job_count`, `recent_job_count` (jobs within the recency window)
- technology demand (openings per canonical technology, reusing the existing
  `extract_technologies`), roles, and cities
- `hiring_intensity` — LOW / MEDIUM / HIGH / VERY_HIGH (configurable thresholds)
- `company_signals` — LARGE_TECH_HIRING, RAPID_HIRING, MULTI_TECH_HIRING,
  ENGINEERING_EXPANSION, VENDOR_REQUIREMENT, CLOUD_MIGRATION, AI_INITIATIVE,
  DIGITAL_TRANSFORMATION (evidence-based)
- `company_type` classification (IT_SERVICES, SOFTWARE_PRODUCT, FINTECH_TECH, …)
- `source_count` and an `evidence` trail (the supporting postings)

All thresholds/weights live in `config/aggregation.py` (configurable, not hard-coded).

### Job deduplication

Two levels:

- **Same posting re-seen** (same source + external id) → ignored.
- **Cross-source duplicate** (same company + title + city from a *different*
  source) → not counted as a new opening, but the extra source is recorded as
  confirming evidence (`source_count` increases). Distinct requisitions within a
  single source still count.

### Company deduplication

Companies are grouped by `normalize_company_name` (e.g. "ABC Technologies Pvt
Ltd", "ABC Technologies", "ABC Technologies Private Limited" → one company).
Domain is captured when available. Companies are not merged on fuzzy name
similarity alone.

## Scoring (`intelligence/company_pipeline.py`)

A deterministic, no-LLM score (0–100) from hiring intensity, recency ratio,
technology breadth, number of signals, multi-source confirmation, and seniority
mix. Priority: HOT ≥ 80, WARM ≥ 60, NURTURE ≥ 40, else LOW (aligned with the
lead scorer). Opportunity type is derived from the strongest company signal
(e.g. VENDOR_REQUIREMENT → "Staff Augmentation").

Original job titles are preserved on the raw records (`title`); the lead exposes
aggregated `technologies`, `hiring_roles`, and a `primary_target_role`
(decision-maker to approach).

## Quality control

- Non-IT / borderline records are tagged (`it_relevance`) by collectors and
  retained, never silently dropped; the signal engine remains authoritative.
- A company becomes a lead only with real evidence (`min_jobs_for_lead`); a
  single stale job yields LOW priority, not HOT.

## Endpoints

- `GET /leads?provenance=real|synthetic|all` — company opportunities.
- `GET /leads/technology-demand?provenance=…` — aggregated technology demand
  (openings + companies) across collected job records.

## Running it

```bash
# Production step: aggregate REAL collected jobs into company leads.
python scripts/build_company_leads.py

# Audit / clean the database (real-data-only compliance).
python scripts/db_audit.py --fail-on-synthetic
```

## What the dashboard shows after the next real collector

Once a real collector (e.g. Adzuna) is configured, tested, and its raw job
records aggregated via `build_company_leads.py`, the production dashboard
(REAL-only) will show real Indian IT company opportunities — company, location,
IT openings, recent hiring, top technologies, signal, opportunity, score,
priority, target role, source count, and last signal date — each traceable to
its supporting job postings. Until then it honestly shows the empty state.
