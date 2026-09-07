# Adzuna Jobs Collector

First real data collector for the LeadGenerationAgent. It pulls IT job postings
from the [Adzuna Jobs API](https://developer.adzuna.com/) and persists them as
**raw source records** — it does **not** create leads, run signal detection, call
any LLM, or scrape web pages.

## What it does

- Queries the documented Adzuna Search API (`/jobs/{country}/search/{page}`) for a
  configurable set of IT roles across configurable locations.
- Maps each result to a `RawRecordDraft` → `RawSourceRecord` (`is_synthetic = false`).
- Applies a lightweight IT-relevance pre-filter (keeps borderline records; drops
  only obvious non-IT). The Signal Detection Engine remains the authority for
  business-signal classification.
- Deduplicates by `external_id` then `content_hash`, refreshing `last_seen_at` on
  records already seen.

Everything downstream (normalization → signal detection → scoring → lead
creation) is handled by the existing pipeline, not by this collector.

## Configuration

All configuration is via environment variables (see `.env.example`). **No
credentials are ever committed.** The application starts without them; the
collector simply reports `NOT_CONFIGURED` until both the app id and key are set.

| Variable | Default | Notes |
| --- | --- | --- |
| `ADZUNA_API_BASE_URL` | `https://api.adzuna.com/v1/api` | API root |
| `ADZUNA_APP_ID` | _(empty)_ | Credential — required to run |
| `ADZUNA_APP_KEY` | _(empty)_ | Credential — required to run |
| `ADZUNA_COUNTRY` | `in` | India by default; configurable (`gb`, `us`, …). Not hard-coded |
| `ADZUNA_SEARCH_TERMS` | built-in IT list | Comma-separated override |
| `ADZUNA_LOCATIONS` | Indian IT hubs | Comma-separated override |
| `ADZUNA_LOOKBACK_DAYS` | `7` | Recency window (`max_days_old`) |
| `ADZUNA_RESULTS_PER_PAGE` | `20` | Capped at 50 |
| `ADZUNA_MAX_PAGES` | `5` | Pagination safety limit |
| `ADZUNA_REQUESTS_PER_MINUTE` | `20` | Conservative rate limit |
| `ADZUNA_DAILY_REQUEST_LIMIT` | `200` | Daily budget |
| `ADZUNA_TIMEOUT_SECONDS` | `15` | Read timeout |
| `ADZUNA_INTEGRATION_TEST` | `false` | Opt-in for the live smoke test |

## Rate limiting, retries, timeouts

- A rolling-window rate limiter enforces `ADZUNA_REQUESTS_PER_MINUTE`.
- Retries apply **only** to transient failures (`429`, `500`, `502`, `503`,
  `504`). On `429` the `Retry-After` header is honoured. Non-transient responses
  (`400/401/403/404`) are **never** retried.
- Connect/read timeouts are configurable; requests fail fast rather than hang.

## Credential hygiene

Credentials are read from the environment only, sent as query params to Adzuna,
and **never logged or serialized**. HTTP logs use a redacted URL (`...?***`), and
the `httpx`/`httpcore` loggers are quieted to `WARNING` so they cannot echo the
credential-bearing URL. Health-check messages never contain the app id/key.

## Incremental collection

Adzuna has no true cursor. `fetch_incremental()` uses a recency window
(`max_days_old`, defaulting to the configured lookback) and relies on
`external_id` + `content_hash` deduplication downstream to skip already-known
postings. It is a windowed re-scan, not a stateful cursor.

## Usage

```bash
# Dry run — calls the API and summarizes, but persists nothing.
python -m collectors.jobs.adzuna --query "Java Developer" --location Bengaluru \
    --pages 1 --results-per-page 5 --dry-run

# Real run — persists raw records (requires credentials).
python -m collectors.jobs.adzuna --query "Java Developer" --location Bengaluru --pages 1
```

Programmatic use goes through the source-agnostic service:

```python
from collectors.jobs.adzuna import AdzunaJobCollector
from collectors.service import JobCollectionService
from collectors.source_registry import get_registry

collector = AdzunaJobCollector(get_registry().get("adzuna"))
summary = JobCollectionService(session).collect(collector, collector.plan_requests())
```

## Testing

- `pytest` runs entirely offline by default — every HTTP call is served by
  `httpx.MockTransport`. No credentials or network access are required.
- The live smoke test (`test_live_adzuna_smoke`) is skipped unless
  `ADZUNA_INTEGRATION_TEST=true` **and** real credentials are present. It makes a
  single `results_per_page=1` call.

## Compliance

> **Commercial-use caveat.** Adzuna's current terms require review and approval
> for ongoing commercial use of the API. This integration is provided for
> development and evaluation; **do not treat commercial production use as
> approved.** Review the [Adzuna API terms](https://developer.adzuna.com/) before
> enabling in production, retain only what the API returns, and preserve
> `source_url` attribution.

Registry posture (`config/sources.yaml`): `terms_status: REQUIRES_REVIEW`,
`commercial_use_status: REQUIRES_APPROVAL`, `api_terms_reviewed: true`. The source
is marked `CONNECTED` only once configured and verified against the live API;
otherwise `NOT_CONFIGURED`.
