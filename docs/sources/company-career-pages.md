# Company Career-Page Collector

Second real-data collector. A generic, compliant framework for collecting real IT
job information directly from **publicly accessible** company career pages where
automated access is permitted. It produces **raw source records only** — no lead
creation, no signal detection, no LLM, no outreach.

> This is not an uncontrolled scraper. It respects robots.txt, terms of service,
> rate limits, authentication/access controls, and never executes page
> JavaScript or bypasses restrictions.

## Architecture

```
Career Source Registry (config/career_sources.yaml)
        ↓
CareerPageCollector  ──uses──▶  Adapter (generic / ATS stubs)
        ↓                              ↓
SafeHttpClient (SSRF + limits) ──▶ Parser (JSON-LD → embedded JSON → HTML)
        ↓
RawRecordDraft → RawSourceRecord   (later: normalization → dedup → signals)
```

The later intelligence stages (normalization, deduplication, signal detection,
opportunity analysis) are **not** implemented here — they already exist and
consume `RawSourceRecord`s.

| File | Responsibility |
| --- | --- |
| `collectors/company/sources.py` | `CareerSourceDefinition` + registry (career_sources.yaml) |
| `collectors/company/config.py` | Env-driven policy/safety config (`CAREER_*`) |
| `collectors/company/safety.py` | Scheme + SSRF URL validation |
| `collectors/company/http_client.py` | `SafeHttpClient`: limits, redirects, retries, content-type |
| `collectors/company/robots.py` | `RobotsPolicy` (ALLOWED/DISALLOWED/UNKNOWN) |
| `collectors/company/parsers.py` | JSON-LD / embedded-JSON / HTML parsers |
| `collectors/company/adapters.py` | Generic adapter + ATS stubs |
| `collectors/company/mapping.py` | Job dict → `RawRecordDraft` |
| `collectors/company/career_page.py` | `CareerPageCollector` + CLI |

## Supported parsing methods

Structured data is strongly preferred (fragile CSS selectors are avoided):

1. **JSON-LD** `schema.org/JobPosting` — the primary path. Extracts title,
   description, datePosted, validThrough, hiringOrganization, jobLocation,
   employmentType, baseSalary, url, identifier. Missing fields are tolerated.
2. **Embedded JSON** — `<script type="application/json">` blocks containing job
   arrays (title + a URL field). Only structured data is parsed.
3. **HTML anchors** — last-resort, low-fidelity extraction of job links.

**No JavaScript execution.** Pages that render jobs only via client-side JS are
marked `requires_js: true` / `status: NOT_SUPPORTED`; a browser-based collector
would require separate review.

## IT relevance filtering

`collectors.it_taxonomy.classify_it_relevance` tags each record `RELEVANT`,
`NOT_RELEVANT`, or `UNKNOWN` (stored on the raw payload). Borderline records are
**retained** and marked `UNKNOWN` — never silently discarded. The Signal
Detection Engine remains the authority for business classification. Technology
and role extraction reuse the existing `ingestion.normalizer` logic (backed by
`TECHNOLOGY_ALIASES`) — not duplicated.

## Robots handling

`RobotsPolicy` fetches a host's `robots.txt` (via the safe client) and evaluates
the configured User-Agent with the stdlib `robotparser`:

- `ALLOWED` — collection proceeds.
- `DISALLOWED` — collection is refused (`RestrictedError`); health = `RESTRICTED`.
- `UNKNOWN` — robots unavailable/unparseable; the collector proceeds cautiously
  and logs the status. Restrictions are never bypassed.

## Terms / compliance handling

Per-source `terms_status`: `ALLOWED` / `REQUIRES_REVIEW` / `RESTRICTED` /
`UNKNOWN`. `RESTRICTED` sources are never collected. `REQUIRES_REVIEW` stays
disabled unless the source is explicitly enabled for development/legal review. A
source is only `CONNECTED` after real end-to-end testing (access, parser,
mapping, tests, acceptable robots/terms). All shipped example sources are
`PLANNED`/disabled.

## SSRF protection

`safety.validate_public_url` runs on every request (including each redirect hop):

- Only `http`/`https` schemes.
- Blocks loopback, private ranges, link-local, multicast, reserved, unspecified.
- Blocks `localhost`, `*.internal`/`*.local`, and cloud metadata IPs
  (`169.254.169.254`, `100.100.100.200`).
- Optional DNS resolution check for hostnames (`resolve=True` in real runs).
- Private/allowlisted hosts only via explicit `CAREER_ALLOW_PRIVATE_HOSTS` /
  `CAREER_ALLOWLISTED_HOSTS` for controlled local testing.

## Response-size / redirect / content-type limits

- `CAREER_MAX_RESPONSE_SIZE_MB` (default **5 MB**) — streamed read aborts if
  exceeded (Content-Length hint + actual byte cap).
- `CAREER_MAX_REDIRECTS` (default **3**) — each hop re-validated; unlimited or
  unsafe redirects are refused.
- Content-type allowlist: `text/html`, `application/json`,
  `application/ld+json`, `application/rss+xml`, `application/atom+xml`,
  `application/xml`. Binary/other content is rejected (robots.txt is exempt).

## Pagination

Follows only clear pagination hints: `<link rel="next">`, `<a rel="next">`, or
structured next links found in JSON. Bounded by `CAREER_MAX_PAGES` (default 3)
and `CAREER_MAX_RECORDS` (default 200). Self-referential links are not followed.

## Rate limiting & retries

Conservative default of **10 requests/minute** (`CAREER_REQUESTS_PER_MINUTE`),
per source override via `requests_per_minute`. Retries reuse the shared policy:
transient only (`429`/`5xx`, honouring `Retry-After`); never `401/403/404`. A
`403` raises `RestrictedError` and marks the source restricted/unavailable.

## Incremental strategy

Career pages rarely expose reliable incremental cursors. `fetch_incremental`
uses a recency window (`CAREER_LOOKBACK_DAYS`, default 30) — filtering by
`datePosted` when present (undated jobs are kept) — and relies on `external_id` +
`content_hash` deduplication downstream to avoid re-storing known postings.

## Data model

Each job maps to a `RawSourceRecord` (`record_type = JOB_POSTING`,
`is_synthetic = false`) with: source_id, external_id (identifier or URL path),
source_url, published_at, title, description, company_name, company_domain,
normalized_company_name, location, industry, technologies, roles, salary,
contract_type (employment type), content_hash, and a small structured
`raw_payload` (job_url, dates, location breakdown, department, it_relevance,
collection_method). **No raw HTML** and **no personal data** (recruiter names,
phones, emails, private identifiers) are stored.

## Limitations

- No JavaScript rendering (JS-only sites are `NOT_SUPPORTED`).
- Only the generic adapter is implemented; ATS adapters are stubs.
- HTML fallback is low-fidelity (title + link only).
- No verified real company source ships enabled — all examples are `PLANNED`.
- Location components are parsed only when explicitly present (never inferred).

## Future ATS adapters

Interface stubs exist for **Greenhouse**, **Lever**, **Workday**, and
**SmartRecruiters** (`collectors/company/adapters.py`). They make no network
calls and are unsupported until a reviewed, permitted integration is added. See
`collectors/company/README.md` for how to add a source or adapter.
