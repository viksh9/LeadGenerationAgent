# Real Data Architecture

How LeadGenerationAgent turns real, current, relevant Indian IT job data into
reliable **company-level** hiring intelligence. The product goal is not "collect
jobs" — it is to find Indian IT companies showing strong, recent signals of
technology hiring / engineering expansion / staffing demand.

## Data flow

```
Source (permitted API / public page)
  → JobCollectionService        → RawSourceRecord  (one source's view; + CollectionRun audit)
  → JobNormalizationService     → NormalizedJob     (location, normalized_role, quality, confidence)
  → JobDeduplicationService     → JobRecord + JobSourceReference[]   (canonical, cross-source deduped)
  → CompanyHiringAggregator     → CompanyAggregate  (counts, intensity, signals, evidence)
  → company scoring             → Lead              (ONE per company; provenance REAL/SYNTHETIC)
  → Dashboard                   (company-level, REAL-only in production)
```

Real and synthetic data are processed on strictly separate tracks.

## Source registry

`config/sources.yaml` → `SourceDefinition` (no secrets). Statuses: `PLANNED`,
`AVAILABLE`, `NOT_CONFIGURED`, `REQUIRES_REVIEW`, `CONNECTED`, `DISABLED`,
`ERROR`. A source is `CONNECTED` **only** after credentials/config exist, a
connection test passes, mapping works, unit tests pass, terms/automation are
acceptable, and real data has actually been ingested. Capability flags
(`supports_search/pagination/incremental_fetch/date_filter/location/salary/
company_id/job_id`) and a `priority` (lower = preferred canonical source)
describe each source. Compliance is documented per source
(`terms_status`/`robots_status`/`commercial_use_status`, all
ALLOWED/REQUIRES_REVIEW/RESTRICTED/UNKNOWN) and never bypassed.

Current state: **no source is CONNECTED.** Adzuna is `NOT_CONFIGURED` (collector
built, no credentials); company career pages are `REQUIRES_REVIEW`; the rest are
`PLANNED` placeholders.

## Job record (canonical)

`JobRecord` is a deduplicated opening. It preserves `original_job_title` and
derives `normalized_role` (never mutates the source title), with structured
location (`country`/`state`/`city`/`remote_type`), technologies, salary,
`published_at`, `job_status` (ACTIVE/EXPIRED/UNKNOWN — a reachable URL is *not*
assumed active), `data_quality_score`, `data_provenance`, `source_count`, and a
`primary_source` (highest-priority source).

## Normalization

`JobNormalizationService`: raw → `NormalizedJob`. Location via a configurable
Indian city map (`config/locations_in.py`; "Bangalore"→Bengaluru,
"Gurgaon"→Gurugram, "HITEC City"→Hyderabad), ambiguous input left un-transformed.
Technologies reuse the existing detector. `data_quality_score` (0–100) is a
weighted presence check (company/title/date/url/description/location/tech/id) —
**independent of the lead score**. `source_confidence` reflects source
reliability (also not a lead score).

## Company identity & deduplication

Company grouping uses `normalize_company_name` ("ABC Technologies Pvt Ltd" ==
"ABC Technologies"); domain is a strong identity signal when present; similar
names are never merged on name alone.

Cross-source job dedup pairs postings by **ordinal within a content key**
`(normalized_company, normalized_role, city)`: the k-th posting of the same
content from any source maps to the same canonical opening. So N distinct
same-source requisitions stay N openings, while the same N syndicated to another
source attach as `JobSourceReference` evidence (`source_count += 1`) — never
double-counted. Same `(source, external_id)` re-fetches just refresh
`observed_at` (idempotent re-runs).

## Company-level aggregation

`CompanyHiringAggregator` (`intelligence/company_aggregator.py`) counts canonical
jobs per company: `it_job_count`, recent (7/14/30-day) counts, technology demand,
roles, cities, `hiring_intensity` (LOW/MEDIUM/HIGH/VERY_HIGH — configurable
thresholds in `config/aggregation.py`), and evidence.

## Hiring intensity & signals

Intensity considers absolute count **and** recency/breadth. Company signals are
evidence-based: `LARGE_TECH_HIRING`, `RAPID_HIRING` (only with sufficient recent
evidence — otherwise UNKNOWN, never a false growth claim), `MULTI_TECH_HIRING`,
`ENGINEERING_EXPANSION` (multi-city), `VENDOR_REQUIREMENT`, `CLOUD_MIGRATION`,
`AI_INITIATIVE`, `DIGITAL_TRANSFORMATION`.

## IT company classification

`company_type` (IT_SERVICES, SOFTWARE_PRODUCT, SAAS, CLOUD, AI_ML, CYBERSECURITY,
FINTECH_TECH, HEALTHTECH, ECOMMERCE_TECH, ENTERPRISE_SOFTWARE, IT_CONSULTING,
DIGITAL_TRANSFORMATION, OTHER_TECHNOLOGY) is derived from industry text + tech
mix. A single developer job does not make a company "IT".

## Opportunity / lead creation

A company becomes a lead only with real evidence (`min_jobs_for_lead`); a lone
old job stays a job record. Scoring is deterministic (no LLM): intensity +
recency + tech breadth + signals + multi-source + seniority → HOT/WARM/NURTURE/LOW.

> Note: `CompanyHiringProfile` and `OpportunityCandidate` as *separate* persisted
> models are intentionally deferred — a `Lead` currently is the company
> opportunity. This is a planned follow-up.

## Provenance & evidence

Every record carries `data_provenance` (REAL/SYNTHETIC). Production `/leads`
defaults to REAL-only; the dashboard shows a "Demo data" banner for synthetic and
the honest empty state ("No verified Indian IT signals available yet.") when no
real leads exist. Each lead's `evidence` + `source_count` trace back to the
canonical jobs and their `JobSourceReference`s — "found on N sources" is only
claimed when the sources are genuinely distinct.

## Collection audit

`CollectionRun` records each collection: source, started/completed, pages,
records fetched/created, duplicates, errors, duration, status
(RUNNING/COMPLETED/FAILED). Written by `JobCollectionService` (skipped on dry-run).

## Compliance & security

Only permitted public/official access — never bypass CAPTCHA, auth, paywalls,
robots, or rate limits. Collectors reuse the SSRF guard, response-size/redirect
limits, transient-only retries, and credential-free logging. Logs never contain
keys/tokens/cookies; credential-bearing URLs are redacted.

## Real vs synthetic mode

Production/default = REAL. Synthetic is opt-in (`SHOW_SYNTHETIC_LEADS`/non-prod
env) and always labelled. `scripts/build_company_leads.py` runs the real pipeline
(raw → canonical → company leads); `scripts/seed_demo_companies.py` seeds clearly
labelled synthetic demo companies. Since no real source is connected, the
production dashboard currently shows the honest empty state.

## Testing

Unit tests run fully offline (mocked HTTP, no network). Real-source integration
tests are opt-in (`ADZUNA_INTEGRATION_TEST`, `CAREER_PAGE_INTEGRATION_TEST`).
