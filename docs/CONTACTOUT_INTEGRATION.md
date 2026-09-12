# ContactOut Integration (POC / Decision-Maker Enrichment)

Real POC discovery and contact enrichment for **company-level opportunities**. Every
person, title, email, phone, and LinkedIn URL shown is one **ContactOut actually
returned and validated** — nothing is fabricated. When ContactOut is not configured
or returns nothing, the app shows **role-only recommendations**, never a fake person.

## Company-level flow (never once per job)

```
REAL job / business signals
  → company-level Opportunity (Lead)
  → recommended POC roles (deterministic, from the opportunity — enrichment/poc_finder.py)
  → ContactOut Decision Makers  (GET /v1/people/decision-makers)
  → [insufficient?] targeted People Search (POST /v1/people/search, scoped to the company)
  → rank candidates + validate CURRENT employment
  → enrich only the best few (POST /v1/people/enrich)  — credit-capped
  → persist DecisionMaker rows (source = ContactOut, provenance = REAL)
  → Target POC Details → Lead/Opportunity UI → Excel export
```

ContactOut is **never** a source of hiring signals — signals come from real
job/project/business sources. It is applied **after** signal detection, opportunity
analysis, lead scoring, and POC-role recommendation.

## Configuration (environment only)

| Variable | Default | Purpose |
|---|---|---|
| `CONTACTOUT_API_TOKEN` | _(unset)_ | API token. **Unset ⇒ NOT_CONFIGURED, no calls.** Never exposed. |
| `CONTACTOUT_BASE_URL` | `https://api.contactout.com` | Configurable for testing. |
| `CONTACTOUT_ENABLED` | _(derive)_ | Explicit off-switch. |
| `CONTACTOUT_PEOPLE_SEARCH_RATE_PER_MINUTE` | `60` | People Search client-side limit. |
| `CONTACTOUT_OTHER_RATE_PER_MINUTE` | `1000` | Other APIs client-side limit. |
| `CONTACTOUT_MAX_POC_SEARCHES_PER_OPPORTUNITY` | `3` | Credit cap (searches). |
| `CONTACTOUT_MAX_ENRICHMENTS_PER_OPPORTUNITY` | `2` | Credit cap (enrichments). |
| `CONTACTOUT_CACHE_TTL_HOURS` | `168` | Reuse recent POCs instead of spending a credit. |

**Authentication:** the documented `token: <API_TOKEN>` header (centralized in the
client, never a query param). The token is never logged, returned, stored in the DB,
written to Excel, or placed in audit payloads.

## Code layout

- `integrations/contactout/` — `client.py` (typed `ContactOutClient`: `get_decision_makers`,
  `search_people`, `enrich_person`, `check_connection`; retry/backoff honouring
  `Retry-After`; dual rate limiters), `models.py`, `mapper.py` (defensive parsing —
  never invents a value), `exceptions.py`, `ranking.py` (deterministic ranking +
  company-match validation + contact trust).
- `enrichment/contactout_poc.py` — company-level orchestration (discovery, credit
  control, caching, dedup, persistence, audit, observability).
- `api/routes/pocs.py` — endpoints (below).

## APIs used (official contract)

`GET /v1/people/decision-makers` (company identifier: domain → verified LinkedIn →
name), `POST /v1/people/search` (job_title/job_function/seniority/company/location/
skills/current_titles_only/page/page_size; current titles by default), `POST
/v1/people/enrich` (strongest available real identifiers only).

> Response field spellings differ by ContactOut plan/version; the mapper reads several
> documented spellings and tolerates list-or-scalar values. The connectivity-check
> endpoint path (`/v1/stats`) should be confirmed against your live ContactOut docs.

## Application endpoints

- `GET /leads/{id}/pocs` — real POCs + role-only recommendations + config status.
- `POST /leads/{id}/pocs/discover` — run discovery (SALES role, rate-limited).
- `POST /pocs/{id}/enrich` — re-enrich one POC (SALES role, rate-limited).
- `GET /pocs/{id}` — one POC.
- `GET /integrations/contactout/status` — config status for Settings (no token).
- `POST /integrations/contactout/test` — real, **credit-free** connectivity check →
  `CONNECTED` / `AUTHENTICATION_FAILED` / `RATE_LIMITED` / `NOT_CONFIGURED` /
  `UNAVAILABLE`. Never claims connected without actually contacting ContactOut.

## Ranking & Contact Trust

Ranking precedence (deterministic): **current company match > current title relevance
> seniority > opportunity relevance > contact availability**. Contact Trust
(`VERIFIED` / `LIKELY` / `UNVERIFIED` / `NO_CONTACT_DATA`) measures *contact
reliability* and is **kept separate from the business lead score** — a ContactOut
contact never raises the lead score.

## No-fabrication rules

- A person is attached only when ContactOut returns them **and** their current
  company is validated (domain or strong name match + current employment). Name
  similarity alone never attaches a POC.
- Missing work email / phone / LinkedIn stay empty (UI shows "Not Available"). Work
  email is preferred for business outreach; a personal email is never presented as
  the primary business contact. Phone/LinkedIn are the exact returned values.
- On any ContactOut failure (`400/401/403/429/5xx`/timeout/empty), POC discovery is
  reported as unavailable — a failure never produces a fake POC.

## Credit-aware & scheduled

Discovery reuses recent verified POCs within `CONTACTOUT_CACHE_TTL_HOURS`; only the
best candidates lacking a business contact are enriched, bounded by the per-opportunity
caps. The scheduler's `COMPANY_ENRICHMENT` job re-enriches only HOT/WARM real leads
with a recent material change, and skips entirely when ContactOut is not configured.

## Excel export

The fixed **16-column** export is unchanged in shape. **Target POC Details** shows the
real person(s) (`Jane Doe — VP Engineering`, up to two) or the role-only
recommendation; **Contact Number** / **Email** carry the real business phone/work
email or stay blank; **Source** notes `ContactOut` when it backs the contact.

## Testing

Fully mocked (`httpx.MockTransport`) — no network, no token required:
`tests/unit/test_contactout_config.py`, `tests/unit/test_contactout_ranking.py`,
`tests/integration/test_contactout_client.py`, `tests/integration/test_contactout_poc.py`,
`tests/integration/test_pocs_api.py`, plus the ContactOut Excel-mapping case in
`tests/integration/test_export.py`. Frontend: `TargetPOCPanel.test.tsx`,
`ContactOutSection.test.tsx`.

## Security

Token stored only in the environment; never in the frontend, logs, database, Excel,
or audit payloads. POC discovery/enrichment/test endpoints require the SALES role
(when `ADMIN_API_KEY` is set) and are rate-limited.
