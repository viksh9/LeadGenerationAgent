# Company → ATS Source Discovery

The official ATS collectors ([Greenhouse](sources/greenhouse.md),
[Lever](sources/lever.md)) run against a **known** board token / site handle. This
discovery layer answers the prior question — *which* official ATS (if any) a company we
already track actually uses — and verifies that company-to-ATS relationship **safely**,
without guessing board ids or crawling the open web.

Discovery is implemented in `collectors/company/career_source_discovery.py`. The
Greenhouse/Lever collectors and the `CompanyCareerSource` model already existed; this
layer adds the **discovery + verification + APIs** on top.

## Discovery flow

- **Input**: a **real company already in the DB** that has a domain/website. Discovery
  is never run against an arbitrary URL supplied by a caller.
- **Own-domain-only, deterministic probing**: the service probes **only the company's
  own domain and its declared careers URL**. The candidate URLs are deterministic:
  - the declared `{careers_url}`,
  - `https://{domain}/careers`,
  - `https://{domain}/jobs`,
  - the domain root.

  It **never** fetches arbitrary third-party URLs and **never** blindly crawls the
  internet.
- **Detection**: discovery detects a Greenhouse `board_token` or Lever site handle that
  is **found on the company's own careers page** (a link) or reached **via a redirect
  from it**.
- **Verification**: only when a board/site is found by one of those two paths is the
  relationship marked **VERIFIED**. Discovery **never fabricates a board id**. The
  `discovery_method` is recorded as either `careers_page_link` or
  `careers_page_redirect`.

## Verification evidence

An official company source is **`TIER_1`** evidence — higher-confidence **direct**
evidence than the Adzuna / Jooble aggregators (**`TIER_2`**). A verified relationship is
persisted in the `company_career_sources` table (`CompanyCareerSource`):

| Field | Meaning |
| --- | --- |
| `company_id` | Link to the company already tracked in the DB. |
| `ats_provider` | The detected official ATS (Greenhouse / Lever). |
| `board_identifier` | The Greenhouse board token / Lever site handle found on the company's own careers page. |
| `careers_url` | The company careers URL the relationship was verified from. |
| `discovery_method` | `careers_page_link` or `careers_page_redirect`. |
| `status` | Lifecycle status (below). |

### Status lifecycle

| Status | Meaning |
| --- | --- |
| `DISCOVERY_REQUIRED` | No board/site is known for the company yet. |
| `CONFIGURED` | A relationship has been discovered and verified. |
| `CONNECTED` | A real collection/health request against that board has actually succeeded. |

## Security

- **No unrestricted URL fetching is exposed.** Discovery follows **only** the company's
  own domain and declared careers URL.
- **Safe HTTP.** All requests go through the existing `SafeHttpClient`: HTTPS upgrade,
  SSRF guard, private-network block, validated redirects, response-size cap, polite rate
  limiting, and transient-only retries.
- **No credentials.** No credentials are ever sent or logged; the target APIs are
  public and no-auth.
- **Format-validated.** Discovered board tokens / site handles are format-validated
  before use; boards are **not** enumerated blindly.
- **Compliance.** robots.txt and site terms are respected. Only IT-relevant postings are
  retained downstream; provenance is `REAL`.

## APIs

Implemented in `api/routes/career_sources.py`. GET endpoints make **no** network calls
and never return credentials.

| Method & path | Purpose |
| --- | --- |
| `GET /career-sources` | List all discovered/registered company career sources. |
| `GET /career-sources/{id}` | Detail for one career source. |
| `GET /companies/{id}/career-sources` | Career sources registered for one company. |
| `POST /companies/{id}/discover-career-source` | Run the real, safe own-domain discovery for a company and register any verified relationship. |
| `POST /career-sources/{id}/check` | Real connectivity health check for that board; updates `status`. |
| `POST /career-sources/{id}/collect` | Real collection for that board through the full pipeline; returns actual counts. |

## Incremental & idempotent behavior

Discovery and collection are **incremental and idempotent**. Re-running discovery
updates the existing relationship rather than creating a duplicate; re-running collection
skips duplicate raw records (dedup by `external_id` then `content_hash`) rather than
creating duplicates.

Official-source jobs flow through the **same** pipeline as every other source (raw →
normalize → canonical dedup → company resolution → evidence verification → signal →
opportunity → lead). One canonical job may carry **multiple** source references across
the official ATS + Adzuna + Jooble. Syndicated copies of the same posting are **one**
evidence group — **not** independent confirmations. Company-level intelligence therefore
shows **canonical job counts, not the sum of per-source counts**.

## Terms & licensing

> **Commercial-use caveat.** Being publicly reachable is **not** the same as approved
> for commercial use. Review the Greenhouse and Lever terms before ongoing or commercial
> reuse. This integration is provided for development and evaluation.

Registry posture: commercial / ongoing reuse `REQUIRES_REVIEW`. Evidence tier `TIER_1`.
A relationship is `CONFIGURED` once verified from the company's own careers page, and
`CONNECTED` only once a real public request has actually succeeded.

## Testing / live tests

The default `pytest` suite makes **no** external network calls — every HTTP interaction
is served by mocks/fixtures. Live discovery tests are **opt-in** via
`RUN_LIVE_SOURCE_TESTS=true`. No live company is hard-coded as production data.
