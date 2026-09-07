# Adzuna Collector (first real IT job-data collector)

`collectors/adzuna.py` — the first real collector, built on the `BaseCollector`
foundation. It collects IT job postings from the public [Adzuna jobs API](https://developer.adzuna.com/)
and returns `RawRecordDraft`s. It **only collects** — no scoring/signal logic;
technology/role extraction is left to the downstream normalization step.

## Status

**AVAILABLE** — implemented and unit-tested offline. It is **not** marked
CONNECTED because it has not been verified against the live API in this
environment. Set credentials and run the collector to verify.

## Credentials (environment only)

Never committed; read from the environment at runtime:

```
SOURCE_ADZUNA_APP_ID=<your app id>
SOURCE_ADZUNA_API_KEY=<your app key>
SOURCE_ADZUNA_COUNTRY=gb          # optional (default gb)
```

Placeholders live in `.env.example`. Credentials never appear in source, logs, or
serialized models (verified by tests).

## What it collects

Per job posting it maps → `RawRecordDraft`: `external_id` (Adzuna id),
`source_url` (redirect), `title`, `description`, `company_name` (+ derived
`normalized_company_name`), `location`, `industry` (category), `salary`,
`published_at` (created), full `raw_payload`, `is_synthetic = false`, and a
deterministic `content_hash`.

## Network policy

- **Rate limit**: the source's `requests_per_minute` via `RateLimiter`.
- **Timeouts**: `TimeoutConfig` (connect/read).
- **Retries**: transient **429/5xx only** with exponential backoff — never auth
  (401/403) or other 4xx. Failures surface as `CollectorError` / result errors,
  never silently.
- **Pagination**: `has_more` + `next_cursor` (next page) from Adzuna's `count`.
- **Incremental**: `fetch_incremental(FetchRequest(since=…))` adds `max_days_old`.

## Ingestion

`collectors/ingest.py:ingest_source(collector, session, request)` fetches a batch
and persists new records to `raw_source_records`, **deduplicating by content
hash** (existing records skipped). Returns fetched / created / skipped counts.

## Run it

```bash
export SOURCE_ADZUNA_APP_ID=...   SOURCE_ADZUNA_API_KEY=...
python scripts/collect_jobs.py --query "cloud engineer" --pages 2 --per-page 50
```

Without credentials the CLI exits cleanly with a "not configured" message.

## Downstream

Raw records are the internal ingestion layer. Normalization → deduplication →
signal detection → opportunity analysis → scoring (the existing engines) consume
them to produce `Lead`s. Those steps are separate from this collector.
