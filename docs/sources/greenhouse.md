# Greenhouse Job Board Collector

Official ATS collector for the LeadGenerationAgent. It pulls published job
postings directly from a company's own Greenhouse-hosted job board via the
[Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html) and persists
them as **raw source records** — it does **not** create leads, run signal
detection, call any LLM, or scrape web pages.

The Job Board API is **public** — no authentication and no API key. Because the
postings come straight from the hiring company's own board, they are treated as
**`TIER_1`** evidence (higher-confidence direct evidence than an aggregator's
syndicated copy).

## What it does

- Queries the documented Greenhouse Job Board API
  (`GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`,
  implemented in `collectors/ats/greenhouse.py`) for a configured **board token**.
- Parses the response
  `{"jobs": [{ id, title, updated_at, location:{name}, absolute_url, content,
  company_name, departments, offices }], "meta": {total}}` and maps each posting to
  a `RawRecordDraft` → `RawSourceRecord` (`is_synthetic = false`), preserving
  `absolute_url` as `source_url` and the Greenhouse `id`.
- Records the discovered board in the `company_career_sources` table
  (`CompanyCareerSource`) with a status of `DISCOVERY_REQUIRED` / `CONFIGURED` /
  `CONNECTED`.
- Deduplicates by `external_id` then `content_hash`, refreshing `last_seen_at` on
  records already seen.

Everything downstream (normalization → canonical dedup → company resolution →
evidence verification → signal detection → opportunity → lead scoring) is handled
by the existing pipeline, not by this collector. A single canonical job may carry
**multiple** source references across Adzuna / Jooble / ATS; syndicated copies are
one evidence group, **not** independent confirmations.

## Configuration

All configuration is via environment variables (see `.env.example`). There are no
credentials — the API is public — but the collector needs to know **which board(s)**
to fetch. Board tokens are format-validated; boards are **not** enumerated blindly.

| Variable | Default | Notes |
| --- | --- | --- |
| `GREENHOUSE_BOARDS` | _(empty)_ | Comma-separated company **board tokens** to collect. Also settable per-run with `--board` |

Until at least one board token is configured (env or `--board`), the collector's
connection status is `DISCOVERY_REQUIRED` — implemented and working, but with no
target board to run against.

## Usage

The primary ingestion path is the source-agnostic collect CLI:

```bash
# Collect one board (public request, no key).
python scripts/collect.py --source greenhouse --board <board_token>

# Or configure default boards via GREENHOUSE_BOARDS and omit --board.
python scripts/collect.py --source greenhouse

# Dry run — performs the real public request but persists nothing.
python scripts/collect.py --source greenhouse --board <board_token> --dry-run

# Real connectivity check — performs a live public request.
python scripts/source_check.py --source greenhouse
```

`--dry-run` performs the **real** API request and validates/reports counts but
persists nothing.

## Compliance

> **Commercial-use caveat.** Greenhouse's terms should be reviewed before ongoing
> or commercial reuse of the Job Board API. Being publicly reachable is **not** the
> same as approved for commercial use. This integration is provided for development
> and evaluation; review the
> [Greenhouse Job Board API docs](https://docs.greenhouse.io/job-board.html) and
> terms before enabling in production, retain only what the API returns, and
> preserve `absolute_url` attribution.

Registry posture: commercial/ongoing reuse `REQUIRES_REVIEW`. Evidence tier
`TIER_1`. Connection status is `DISCOVERY_REQUIRED` until a legitimate board token
is configured, and `CONNECTED` only once a real public request has actually
succeeded.
