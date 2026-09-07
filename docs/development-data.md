# Development / Sample Data

**All sample data is SYNTHETIC and for development/testing only.** It contains
fictional companies and **role-only** points of contact — no real people,
emails, phone numbers, or private identifiers, and it must never be presented as
real-world evidence.

## Purpose

A reliable synthetic dataset + seed mechanism so developers can populate the
local database, demo the UI, and exercise search/filter/scoring/opportunity/POC/
outreach/analytics against realistic structures.

## Sample data (`data/sample_leads.json`)

32 synthetic leads across **IT / BFSI / FMCG / Healthcare**, with:

- Varied scenarios: large/small hiring, project award/execution, digital
  transformation, cloud migration, vendor requirement, staff augmentation,
  government project, enterprise implementation, expansion, weak/old/recent
  signals, missing POC/project/source, low/medium/high confidence.
- Varied tech stacks and role recommendations; several **companies repeated** so
  Company Intelligence aggregation has something to group.
- Dates stored as a **relative `signal_age_days`** (not absolute), converted to a
  `signal_date` against a configurable reference date at seed time — deterministic
  and never in the future.

Signal type, opportunity type, score and priority are **computed by the real
`LeadAnalysisPipeline`**, not hard-coded, so the dataset naturally produces a mix
of HOT / WARM / NURTURE / LOW.

## Seed commands

```bash
python scripts/seed_database.py                 # seed all 32 synthetic leads
python scripts/seed_database.py --count 10      # seed 10 (variety preserved)
python scripts/seed_database.py --count 50      # seed 50 (generates distinct variants)
python scripts/seed_database.py --reset --yes   # wipe local dev leads, then seed
python scripts/seed_database.py --reference-date 2026-09-01   # dates relative to a fixed day
```

Each run prints created / skipped(duplicates) / failed plus priority, opportunity,
industry, and signal distributions.

- **`--count N`** — fewer than the sample size picks an even spread across
  industries/scenarios; more than the sample size appends distinct synthetic
  variants (company + signal title suffixed) rather than exact duplicates.
- **Duplicates** — the pipeline updates a matching `(company_name, signal_title,
  source_url)` in place, so re-running the seed reports `Skipped (dups)` and never
  creates duplicates.

## Reset safety

`--reset` deletes all leads and is guarded:

- It refuses unless `APP_ENV` is `development`, `test`, or `local`.
- `production` / `prod` / `staging` / **missing** env → refused.
- Without `--yes` it prompts for confirmation.

It only ever targets the configured local database — there is no path to a
production database.

## Fixtures (`tests/fixtures/synthetic_leads.py`)

Reusable synthetic builders — `hot_lead`, `warm_lead`, `nurture_lead`,
`low_lead`, `project_lead`, `hiring_lead`, `vendor_lead`,
`digital_transformation_lead`, `missing_data_lead` — exposed as pytest fixtures
in `tests/integration/conftest.py` and reused across the seed tests.

## Development workflow

```bash
# 1. backend
uvicorn api.main:app --reload            # http://localhost:8000  (docs at /docs)
# 2. seed synthetic data
python scripts/seed_database.py
# 3. frontend
cd frontend && npm run dev               # http://localhost:5173
```

Then the seeded data appears across `/dashboard`, `/leads`, `/leads/:id`,
`/companies`, `/companies/:name`, `/opportunities`, `/contacts`, `/outreach`,
`/analytics`.

## Limitations

- No persisted `is_synthetic` flag on the Lead schema (avoided a schema change).
  The whole local dev database is synthetic; `source_name` values are prefixed
  `Synthetic …` as a soft marker. A "Demo data" badge would need a real backend
  flag and is intentionally not added here.
- Analytics/derived views aggregate the top ~100 leads (documented elsewhere).

## Production-data warning

Never point the seed script at, or run `--reset` against, a production database.
Synthetic records must never be represented as real leads, companies, projects,
or evidence.
