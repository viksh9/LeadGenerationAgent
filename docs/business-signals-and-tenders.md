# Business Signals & Tenders

This layer turns real business events — project awards, contracts, tenders,
expansions, partnerships, transformation programs — into structured intelligence
and combines them with hiring signals into conservative, company-level
opportunity candidates. The business-signal engine (the `BusinessSignal` model,
the deterministic detector, event deduplication, and evidence) already existed;
see [business-signal-architecture.md](business-signal-architecture.md) for that
foundation. **New** in this layer:

- a structured **tender domain** (`TenderRecord`) and a dedicated tender pipeline,
- deterministic **commercial-intent** classification (a separate axis),
- a per-company **business-event timeline**, and
- read-only **signals / tenders / timeline APIs**.

> This is B2B sales intelligence, not a news feed. A tender or news article never
> becomes a Lead on its own. A tender is classified first and is never treated as
> a sales opportunity by itself.

## Signal types

`BusinessSignalType` (`database/models.py`) is deliberately separate from the Lead
signal enum, so extending it never destabilises the existing dashboard. The
deterministic detector (`intelligence/business_signal_detector.py`,
`config/business_signals.py`) classifies text — no LLM — into types including
`PROJECT_AWARD`, `PROJECT_EXECUTION`, `CONTRACT`, `IT_CONTRACT`, `TENDER`,
`GOVERNMENT_TENDER`, `RFP`, `DIGITAL_TRANSFORMATION`, `CLOUD_MIGRATION`,
`TECHNOLOGY_MODERNIZATION`, `AI_INITIATIVE`, `CYBERSECURITY_INITIATIVE`,
`SYSTEM_IMPLEMENTATION`, `PARTNERSHIP`, `EXPANSION` (and the
`DELIVERY_CENTER_EXPANSION` / `ENGINEERING_EXPANSION` variants),
`VENDOR_REQUIREMENT`, `OUTSOURCING`, and `ACQUISITION`.

Both **news** and **tenders** now become `BusinessSignal`s: the business pipeline
(`ingestion/business_pipeline.py`) processes `RecordType.NEWS_ARTICLE` **and**
`RecordType.TENDER`. Tenders additionally produce a structured `TenderRecord`
(below). A tender's signal type flows through the **existing** evidence verifier,
which keeps the four distinct scores separate (source reliability, evidence
confidence, signal confidence, and the commercial lead score) — they are never
collapsed into one.

## Tender data model

`TenderRecord` (`database/models.py`) stores **only what the source explicitly
states**; absent values stay `NULL` and are never fabricated or computed. Fields:

| Field | Meaning |
| --- | --- |
| `title` | Tender/RFP title. |
| `organization_name` | The **issuing buyer** (not necessarily a commercial target). |
| `department` | Issuing department, if stated. |
| `organization_type` | `GOVERNMENT` / `PSU` / `PRIVATE` / `UNKNOWN`. |
| `location` | Tender location, if stated. |
| `issue_date` / `publication_date` / `closing_date` / `award_date` | Real dates from the source only. |
| `estimated_value` | Numeric value — **`NULL` if the source omits it** (never computed). |
| `currency` / `estimated_value_text` | Currency and the original value text. |
| `category` | Source-stated category. |
| `technologies` | Extracted **deterministically** from tender content. |
| `scope_summary` / `eligibility_summary` | Summaries, when present. |
| `tender_status` | Lifecycle status (see below). |
| `source_url` / `source_record_id` | Traceability back to the source. |
| `company_id` vs `target_company_id` | **Issuer** kept separate from any **named awarded vendor** (§15). |
| `evidence_confidence` / `freshness_score` | Verification outputs (separate scores). |
| `commercial_intent` | Deterministic intent band (separate axis). |
| `data_provenance` | Always `REAL`. |
| `first_seen_at` / `last_seen_at` | History markers. |

**Idempotent upsert** by `(source_id, source_record_id)`. History is **preserved**:
on a re-run the status and freshness are refreshed, but records are **never
deleted** (`ingestion/tender_pipeline.py`).

### Issuer vs. awarded vendor (§15)

The issuing organization (`organization_name` / `signal_origin_organization`,
linked via `company_id`) is kept **separate** from any named awarded/target vendor
(`target_company_id`). A tender's buyer is not conflated with the vendor that wins
it.

## Tender lifecycle & freshness

`TenderStatus`: `OPEN` / `CLOSING_SOON` / `CLOSED` / `CANCELLED` / `AWARDED` /
`UNKNOWN`. Derivation (`_derive_status` in `ingestion/tender_pipeline.py`):

1. Use the source's **explicit** status when present (mapped, e.g. `expired`→
   `CLOSED`, `withdrawn`/`retendered`→`CANCELLED`, `award`→`AWARDED`).
2. Otherwise derive from a **real** `closing_date`: past → `CLOSED`; within 7 days
   → `CLOSING_SOON`; future → `OPEN`.
3. Otherwise `UNKNOWN`.

A tender is **never** inferred `OPEN` merely because a page is reachable — only
from an explicit status or a real future closing date.

**Freshness** uses `verification.freshness` (`compute_freshness`): an expired or
closed tender is **stale**. `freshness_score` is stored on the record.

## Technology extraction

`technologies` are extracted **deterministically** from the tender's own content
(reusing the existing technology detector) — never guessed and never inferred from
the buyer's identity.

## Commercial intent (a separate axis)

`intelligence/commercial_intent.py` produces a deterministic band —
`VERY_HIGH` / `HIGH` / `MEDIUM` / `LOW` / `UNKNOWN` (`CommercialIntent`). It
answers "how likely is a real, current commercial opportunity here?" and is
**separate from** evidence confidence, source reliability, and the lead score.

Inputs are real, evidence-backed only: recency/freshness, source quality
(evidence confidence), project/tender evidence, vendor/award/RFP evidence, active
IT hiring volume, technology relevance, corroborating signal-type variety, and
whether the company identity is resolved. Not-fresh signals and unresolved
companies **dampen** the score.

Crucially: with **no** qualifying evidence (no project/tender, no vendor/award, no
active hiring) the result is **`UNKNOWN`, not `LOW`** — the absence of evidence is
reported as unknown, never as a weak-but-real signal.

## Deduplication & syndication

One real-world event = **one** `BusinessSignal`, with every corroborating source
kept as a `SignalSourceReference`. Matching uses `content_hash` (exact) plus an
`event_group_id` derived from `(normalized_company, signal_type, published_day)`.
Syndicated copies of the same story are **one evidence group — not independent
confirmations**; "confirmed by N sources" is only claimed when the `source_id`s
are genuinely distinct.

Tenders upsert idempotently by `(source_id, source_record_id)`, so re-importing
the same tender updates the existing record (refreshing status/freshness) rather
than creating a duplicate. A single canonical event may carry multiple source
references.

## Conflict handling

Because a tender is upserted in place, a later observation that changes the
lifecycle (e.g. a source now reports `AWARDED`, or the closing date has passed)
**refreshes** `tender_status` and `freshness_score` on the existing record while
preserving `first_seen_at` and history. Explicit source status wins over
date-derived status. Value is only ever stored when the source states it — a later
run never back-fills a computed value.

## Cross-signal opportunity detection

The core feature is combining independent real signals. `CompanySignalAggregator`
(see [business-signal-architecture.md](business-signal-architecture.md)) combines
per-company business signals **and** tenders **and** observed hiring (canonical IT
job counts) into an `OpportunityCandidate`. A candidate is created only with
meaningful evidence — e.g. strong hiring **plus** a live tender or a fresh
project/transformation signal is a stronger candidate than any one signal alone.
Candidates are **never** auto-promoted to Leads.

Hiring volume is always the **canonical job count**, not the sum of per-source
counts — syndicated copies across Adzuna / Jooble / ATS boards are one evidence
group.

## Company timeline

`intelligence/company_timeline.py` builds a chronological, de-duplicated timeline
for one company from **real stored records only**:

- **business signals** (each a distinct real event),
- **tenders** (published / closing / awarded, dated from real fields), and
- **observed hiring** — a single summarized event using the **canonical** current
  IT opening count (not a sum of per-source counts) plus the top technologies.

Each entry traces back to a real record with a source URL where available. The
timeline **never fabricates events**; with no data it is simply empty.

## Government-source access reality (verified 2026)

State these exactly — do not overclaim. **No live government source is connected
or executed.**

### CPPP / GeM (`eprocure.gov.in`) — `MANUAL_SOURCE_REQUIRED`

There is **no documented public developer API** for CPPP / GeM. The only
programmatic access is via third-party scrapers, which this project **does not
use** (no unauthorized scraping). The `government_procurement` source is
registered **`PLANNED` / `MANUAL_SOURCE_REQUIRED`**, `commercial_use`
`REQUIRES_REVIEW`. Tenders from these portals can enter **only** via the manual
import CLI, using data an operator obtained through a permitted method.

### data.gov.in (OGD Platform) — `NOT_CONFIGURED`

data.gov.in exposes a **legitimate open-data API**:

```
GET https://api.data.gov.in/resource/{resource_id}?api-key=<KEY>&format=json
```

under the **Government Open Data License – India (GODL)**. It requires a **free
API key** and a **specific dataset `resource_id`**, and **per-dataset field names
vary**, so the adapter must be configured **per dataset**. The
`government_open_data` source is registered **`NOT_CONFIGURED`** (env
`DATA_GOV_IN_API_KEY` + `DATA_GOV_IN_TENDER_RESOURCE_ID`), `commercial_use`
`REQUIRES_REVIEW` — **confirm the specific dataset's GODL terms before commercial
reuse**. Once configured and the per-dataset field mapping/licence are reviewed,
tenders flow through the standard tender pipeline.

## Licensing

- **CPPP / GeM**: no permitted public API; `MANUAL_SOURCE_REQUIRED`;
  `commercial_use` `REQUIRES_REVIEW`.
- **data.gov.in**: **GODL** (Government Open Data License – India);
  `commercial_use` `REQUIRES_REVIEW` — confirm the dataset's specific GODL terms
  before commercial reuse.

Being technically connectable (or a portal being publicly reachable) is **not**
the same as approved for commercial use.

## Manual tender import

For portals with no permitted public API, an operator exports tenders they
obtained through a permitted method into a JSON file and imports them:

```bash
python scripts/import_tender.py tenders.json            # ingest REAL tenders
python scripts/import_tender.py tenders.json --dry-run  # validate + report, persist nothing
```

- Input is a **JSON array** of REAL tender objects (provenance `REAL`).
- **Required** fields: `source_id`, `external_id` (or `id`), `title`.
- Optional fields (e.g. `organization_name`, `department`, `organization_type`,
  `location`, `published_at`/`publication_date`, `issue_date`, `closing_date`,
  `award_date`, `status`, `estimated_value`, `currency`, `category`,
  `scope_summary`, `source_url`) map through; **absent fields stay NULL** and are
  never inferred.
- Imported records run through the **same** business + tender pipelines
  (`run_business_pipeline`, `run_tender_pipeline`). No fabrication, no scraping.

## APIs

Implemented in `api/routes/signals.py` (read-only; empty when no real data
exists). New endpoints:

| Method & path | Purpose |
| --- | --- |
| `GET /signals` | List business signals; filters `signal_type` / `company` / `technology` / `source`; paginated. |
| `GET /signals/{id}` | One business signal. |
| `GET /tenders` | List tenders; filters `status` / `technology` / `organization` / `category`; paginated. |
| `GET /tenders/{id}` | One tender. |
| `GET /companies/{id}/tenders` | Tenders for one company (issuer or target). |
| `GET /companies/{id}/timeline` | One company's chronological business-event timeline. |

`GET /companies/{id}/signals` (a company's business signals) already existed.

## Testing / live tests

The default `pytest` suite makes **no** external network calls — every HTTP
interaction is served by mocks/fixtures. Live source tests are **opt-in** via
`RUN_LIVE_SOURCE_TESTS=true` plus the relevant per-source credentials. No live
government source has been connected or executed (CPPP has no API; data.gov.in is
`NOT_CONFIGURED`); tenders are exercised end-to-end through the manual import CLI
with real operator-supplied data.
