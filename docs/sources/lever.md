# Lever Postings Collector

Official ATS collector for the LeadGenerationAgent. It pulls published job
postings directly from a company's own Lever-hosted board via the
[Lever Postings API](https://github.com/lever/postings-api) and persists them as
**raw source records** — it does **not** create leads, run signal detection, call
any LLM, or scrape web pages.

The Postings API is **public** — no authentication and no API key — and returns
only **published** postings. Because the postings come straight from the hiring
company's own board, they are treated as **`TIER_1`** evidence (higher-confidence
direct evidence than an aggregator's syndicated copy). Developer docs:
<https://hire.lever.co/developer>.

## What it does

- Queries the documented Lever Postings API
  (`GET https://api.lever.co/v0/postings/{site}?mode=json[&limit=N&skip=M]`,
  implemented in `collectors/ats/lever.py`) for a configured **site handle**.
- Parses the response — a **list** of
  `{ id, text, categories:{location, team, commitment, department}, hostedUrl,
  applyUrl, createdAt (epoch ms), descriptionPlain, workplaceType }` — and maps each
  posting to a `RawRecordDraft` → `RawSourceRecord` (`is_synthetic = false`),
  preserving `hostedUrl` as `source_url` and the Lever `id`.
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
credentials — the API is public — but the collector needs to know **which site(s)**
to fetch.

| Variable | Default | Notes |
| --- | --- | --- |
| `LEVER_SITES` | _(empty)_ | Comma-separated company **site handles** to collect. Also settable per-run with `--board` |

Until at least one site handle is configured (env or `--board`), the collector's
connection status is `DISCOVERY_REQUIRED` — implemented and working, but with no
target site to run against.

## Usage

The primary ingestion path is the source-agnostic collect CLI:

```bash
# Collect one site (public request, no key).
python scripts/collect.py --source lever --board <site_handle>

# Or configure default sites via LEVER_SITES and omit --board.
python scripts/collect.py --source lever

# Dry run — performs the real public request but persists nothing.
python scripts/collect.py --source lever --board <site_handle> --dry-run

# Real connectivity check — performs a live public request.
python scripts/source_check.py --source lever
```

`--dry-run` performs the **real** API request and validates/reports counts but
persists nothing.

## Compliance

> **Commercial-use caveat.** Lever's terms should be reviewed before ongoing or
> commercial reuse of the Postings API. Being publicly reachable is **not** the
> same as approved for commercial use. This integration is provided for development
> and evaluation; review the
> [Lever Postings API docs](https://github.com/lever/postings-api) (and
> <https://hire.lever.co/developer>) and terms before enabling in production, retain
> only what the API returns, and preserve `hostedUrl` attribution.

Registry posture: commercial/ongoing reuse `REQUIRES_REVIEW`. Evidence tier
`TIER_1`. Connection status is `DISCOVERY_REQUIRED` until a legitimate site handle
is configured, and `CONNECTED` only once a real public request has actually
succeeded.
