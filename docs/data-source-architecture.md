# Data Source Architecture (real-data ingestion foundation)

This document describes the **foundation** for collecting real, current,
actionable business data. **No source is considered connected until its collector
is implemented, tested, and verified.** This phase performs **no external network
requests** — it defines the registry, interfaces, and internal data model only.

## Pipeline

```
Source → Collector → Raw Record → Normalization → Deduplication →
Evidence Verification → Signal Detection → Opportunity Analysis →
Lead Scoring → Enrichment → BD Intelligence
```

Collectors sit at the top and **only collect**. They contain no scoring/signal
logic; that lives in the existing intelligence engines, which read from the raw
layer downstream.

## 1. Source registry (`collectors/source_registry.py`, `config/sources.yaml`)

A `SourceDefinition` is declarative metadata — **never credentials**. Loaded from
`config/sources.yaml` into a `SourceRegistry` (`get_registry()`).

- **Categories**: JOB, COMPANY, NEWS, PROJECT, TENDER, GOVERNMENT,
  BUSINESS_DATABASE, OTHER.
- **Types**: API, RSS, PUBLIC_WEB, OPEN_DATA, THIRD_PARTY_API, MANUAL_IMPORT.
- **Status**: PLANNED, AVAILABLE, CONNECTED, DISABLED, ERROR — every entry today
  is `PLANNED` and `enabled: false`.

## 4. Collector interface (`collectors/base.py`)

`BaseCollector` (ABC): `fetch(request)`, `fetch_incremental(request)` (defaults to
`fetch` unless the source supports incremental), `health_check()`. Returns a
`CollectorResult` — never silently swallows failures.

- `FetchRequest`: `query`, `since`, `cursor`, `after_external_id`, `page`, `limit`
  — collectors honour only what the source supports (capabilities are declared on
  the `SourceDefinition`).
- `CollectorResult`: `source_id`, `fetched_at`, `records`, `page`, `next_cursor`,
  `has_more`, `total_records`, `warnings`, `errors`, `records_count`.
- `HealthCheckResult`: `source_id`, `status` (HEALTHY / DEGRADED / UNAVAILABLE /
  NOT_CONFIGURED), `checked_at`, `message` (never credentials).

## 5. Raw source records (`database/models.py: RawSourceRecord`)

The internal ingestion table, kept **logically separate** from the derived
`Lead`. Fields include provenance (`source_id`, `external_id`, `source_url`,
`content_hash`), freshness (`collected_at`, `published_at`, `updated_at`,
`last_seen_at`), content (`title`, `description`, `technologies`, `roles`,
`project_*`, …), company identity (`company_name`, `normalized_company_name`,
`company_domain`, `source_company_id`), the original `raw_payload` (JSON, data
only), `is_synthetic`, and `raw_status`. Collectors return `RawRecordDraft`
(`collectors/raw_record.py`); the repository persists it.

- **Real records**: `is_synthetic = false`. **Dev fixtures**: `is_synthetic = true`.
- **Raw payload** is stored verbatim as data and is never evaluated/executed.

## 6. Content hash

`compute_content_hash(source_id, external_id, source_url, title, company_name,
published_at)` — deterministic SHA-256 over **stable** identity fields; uses the
date (not the time) of `published_at` so intra-day re-collection yields the same
hash. Used by the future deduplication engine.

## 7. Company identity foundation

`normalize_company_name()` lowercases, strips punctuation and common legal
suffixes ("Pvt Ltd", "Inc", "LLC", …) so "ABC Technologies Pvt Ltd" and "ABC
Technologies" collapse to the same key. `company_domain` / `source_company_id`
are captured for later resolution. The full resolution algorithm is **not**
implemented here.

## 8. Freshness

`published_at`, `updated_at`, `collected_at`, `last_seen_at` are tracked so future
logic can compute `signal_age` / `freshness_score` (not implemented here).

## 9. Incremental collection

Capability is declared per source (`supports_incremental_fetch`,
`supports_date_filter`, `supports_pagination`). `FetchRequest` carries `since`,
`cursor`, and `after_external_id`; collectors use whatever the source allows.

## 10. Rate limits & 11. retries (`collectors/base.py`)

- `RateLimitConfig` (per source) + a `RateLimiter` service (rolling 1-minute
  window, injectable clock, no sleeping) that future collectors consult.
- `RetryConfig`: `max_attempts`, exponential `backoff_for(attempt)` (capped), and
  `is_retryable(status)` — retries only 429/5xx, **never** auth/authorization or
  permanent 4xx.
- `TimeoutConfig`: `connect_timeout` / `read_timeout` (no unlimited requests).

## 12. Compliance

Each source documents `compliance` (`terms_status`, `robots_status`,
`api_terms_reviewed`, `commercial_use_status`, `data_retention_notes`) using
ALLOWED / RESTRICTED / REQUIRES_APPROVAL / UNKNOWN. The system **never** bypasses
authentication, CAPTCHAs, access controls, robots restrictions, rate limits, or
platform restrictions, and does not implement unauthorized scraping.

## 13. Real-data vs synthetic-data

Synthetic data lives **only** in the test suite (`tests/fixtures/`) and is flagged
`is_synthetic = true` / `data_provenance = SYNTHETIC`. Production collection sets
`is_synthetic = false`. The app is real-data-only: synthetic records are rejected
by the production write-guards (`database/integrity.py`) and never appear in the
application database or UI. See `docs/development-data.md`.

## 14. IT industry focus

`config/industries.py` (canonical IT segments) and `config/target_signals.py`
(collection targets mapped onto the existing `SignalType` — no duplicate enum)
define what collectors should prioritise: IT staff augmentation, engineering
capacity, technology implementation, delivery support, cloud/DevOps/QA/data/AI-ML
engineering, modernization, outsourcing, and vendor partnerships.

## API keys & secrets

Real collectors read keys from the environment: `SOURCE_<SOURCE_ID>_API_KEY`
(e.g. `SOURCE_ADZUNA_API_KEY`). Keys never appear in source, `.env.example`, git,
docs, the frontend, logs, or serialized models — verified by tests.

## Data retention (documentation only)

Raw, normalized, and derived-intelligence data are kept logically separate: raw
records preserve provenance/evidence, normalization produces clean structures,
and scoring/enrichment produce BD intelligence. Nothing is auto-deleted in this
phase; retention windows per source will be configured when collectors land
(see each source's `data_retention_notes`).

## Planned sources (next steps)

All PLANNED (see `config/sources.yaml`): **Adzuna Jobs API** (first real IT
job collector candidate), company career pages, government open-data/tenders,
RSS/business-technology news, public project/contract registries, and a
third-party business/company database. The next prompt implements the first real
IT job-data collector against a permitted API using environment-based
credentials.
