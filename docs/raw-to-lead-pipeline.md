# Raw → Lead Normalization Pipeline

Bridges the raw ingestion layer (`raw_source_records`) to analyzed `Lead`s using
the existing intelligence engines. It performs normalization only — signal
detection, opportunity analysis, scoring, POC and pitch generation stay in
`LeadAnalysisPipeline`.

## Flow

```
RawSourceRecord (NEW)
   → normalize_raw_record()  -> LeadAnalyzeRequest
   → LeadAnalysisPipeline.analyze(persist=True)
   → Lead   (+ raw.lead_id link, raw.raw_status = PROCESSED)
```

## Normalization (`ingestion/normalizer.py`)

`normalize_raw_record(raw)` maps a raw record onto a validated
`LeadAnalyzeRequest`:

- Pass-through: company, industry, location, title→signal_title,
  description→signal_description, published_at→signal_date, source_url,
  project_name/value; source label from `source_id` (e.g. `adzuna` → "Adzuna").
- Extraction (free text → structured; reuses the detector's canonical
  `TECHNOLOGY_ALIASES` — no duplicated data):
  - `extract_technologies()` — canonical tech mentioned in title+description.
  - `extract_roles()` — canonical IT hiring roles (singular/plural).
  - `extract_estimated_hiring()` — largest explicit headcount ("hiring 30", "30
    … engineers").
- Returns `None` (→ raw marked `INVALID`) when there's no company name or no
  usable signal text, or when request validation fails.

## Processing (`ingestion/processor.py`)

- `process_raw_record(session, raw, pipeline)` — normalizes, persists the derived
  technologies/roles back onto the raw record, runs the pipeline, sets
  `raw.lead_id` and `raw.raw_status`, and returns a `ProcessResult`
  (`processed` / `invalid` / `failed`).
- `process_pending(session, *, limit, include_synthetic, pipeline)` — processes
  all `NEW` raw records and returns a `RunSummary` (processed / invalid / failed,
  leads created vs. existing, priority distribution, errors). **Idempotent**:
  processed records leave `NEW`, so re-running does nothing new.

## Deduplication

Two levels, reusing existing behaviour:

- **Raw layer**: the ingest service skips raw records whose `content_hash`
  already exists.
- **Lead layer**: `LeadAnalysisPipeline` upserts on `(company_name, signal_title,
  source_url)`, so multiple raw records for the same posting map to one `Lead`
  (`RunSummary.leads_existed` counts these).

## Status lifecycle

`RawStatus`: `NEW` → `NORMALIZED` (extraction done) → `PROCESSED` (lead created/
linked); `INVALID` when it can't become a lead. `raw.lead_id` is a soft link (no
FK) so raw provenance survives lead deletion.

## Run it

```bash
python scripts/collect_jobs.py --query "cloud engineer"   # collect -> raw
python scripts/process_raw.py                              # raw -> leads
python scripts/process_raw.py --real-only                 # skip synthetic raw
```

## Limitations

- Extraction is keyword/regex-based (deterministic, no LLM); it complements the
  detector rather than replacing it.
- Company-identity resolution is still name-normalization only (foundation).
- New `raw_source_records.lead_id` column is created by `init_db` on fresh DBs
  (no migration framework).
