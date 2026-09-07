# Business-Signal Architecture

Business signals are the second half of the sales-intelligence picture. Job
hiring is one signal; this layer adds **project awards, contracts, tenders,
government technology projects, expansions, partnerships, and transformation
programs**, then combines them with job intelligence into conservative
company-level opportunity candidates.

> This is B2B sales intelligence, not a news feed. A news article never becomes
> a Lead on its own.

## Data flow

```
Real source (permitted API / RSS / open data)
  → BusinessSignalCollector          → RawSourceRecord (NEWS_ARTICLE) + CollectionRun
  → BusinessSignalNormalizationService → NormalizedBusinessSignal (classify, value, dates, confidence)
  → BusinessSignalDeduplicationService → BusinessSignal + SignalSourceReference[] (event_group_id)
  → CompanySignalAggregator (+ job intelligence) → OpportunityCandidate
  → (later) Lead Scoring Engine → Lead
```

Real and synthetic are processed on separate tracks.

## Source types & registry

Reuses `SourceDefinition`/registry (`config/sources.yaml`). Business categories:
NEWS, PROJECT, TENDER, GOVERNMENT, BUSINESS_DATABASE. Only permitted access —
official APIs, RSS/Atom, government open data, official company newsrooms. Never
bypass CAPTCHA/login/paywall/robots/rate limits. Statuses are honest:
`company_newsroom` = REQUIRES_REVIEW, `rss_news` = NOT_CONFIGURED, the rest
PLANNED; a source is CONNECTED only after real access is implemented and tested.
Source `priority` prefers official/newsroom over aggregators for canonical
selection.

**Current state:** no business source is CONNECTED (no feed URLs/credentials).

## Business signal model

`BusinessSignal` (one real event) preserves the original title/description/URL,
resolves company identity (original + normalized + domain; uncertain →
`resolution_status = REVIEW`), and carries `signal_type` (BusinessSignalType,
distinct from the Lead signal enum so extending it never destabilises the
dashboard), `signal_strength` (STRONG/MEDIUM/WEAK), project fields (only when
explicit), technologies, dates + `signal_age_days`, `source_confidence`,
`evidence_confidence`, `data_quality_score`, `data_provenance`, `event_group_id`,
and `source_count`.

## Signal detection

`BusinessSignalDetector` (deterministic, no LLM) classifies text via ordered
keyword sets (`config/business_signals.py`) into PROJECT_AWARD, CONTRACT, TENDER,
DIGITAL_TRANSFORMATION, CLOUD_MIGRATION, TECHNOLOGY_MODERNIZATION, AI_INITIATIVE,
PARTNERSHIP, EXPANSION, DELIVERY_CENTER_EXPANSION, ENGINEERING_EXPANSION,
VENDOR_REQUIREMENT, OUTSOURCING, ACQUISITION. Technology extraction reuses the
existing detector.

- **Project value** is captured only when explicitly stated (`₹500 crore`,
  `$20 million`, `INR 500 Cr`) → numeric value + currency + original text. Vague
  phrases ("large project") and bare counts ("500 engineers") never yield a value.
- **Signal strength** is deterministic (explicit award/contract/tender + value or
  specific technology → STRONG). It is NOT the lead score.

## News relevance & Indian IT filter

Only IT-business-relevant items are kept: an item needs a business-signal type
**and** IT evidence (technology / IT keywords). Obvious non-IT noise (sports,
weather, celebrity) is dropped. A global company remains relevant when the signal
concerns its Indian technology/delivery footprint. IT-company classification
reuses the existing `company_type` architecture; `it_company_status` /
`it_company_confidence` are recorded, and a single generic mention does not make
a company "IT".

## Source & evidence confidence

`source_confidence` reflects source reliability (official/government high,
aggregators lower). `evidence_confidence` is separate — it combines source
quality, claim explicitness, date, company identification, and genuine
multi-source corroboration. Neither is the lead score.

## Event deduplication & cross-source matching

The same event across a company newsroom, a newspaper, and a partner announcement
becomes ONE `BusinessSignal`. Matching uses `content_hash` (exact) and an
`event_group_id` derived from `(normalized_company, signal_type, published_day)`.
Each source is kept as a `SignalSourceReference` (PRIMARY / SUPPORTING).
"Confirmed by N sources" is only claimed when the sources are genuinely distinct
(`source_count` counts distinct `source_id`s). Similar stories are not blindly
merged.

## Company aggregation & job+business combination

`CompanySignalAggregator` computes per company: total/recent/strong business
signals, project/contract/transformation/expansion counts, last signal date,
supporting sources — and combines them with the job-intelligence layer
(it_job_count, recent jobs, top technologies, hiring intensity) into an
`OpportunityCandidate`. The combination is the core feature: **40 Java/AWS/DevOps
openings + a new digital transformation project = a STRONG opportunity candidate**,
stronger than either signal alone.

## Opportunity candidate rule (conservative)

A candidate is created only with meaningful evidence — strong hiring, a strong
business signal (award/contract/tender), or a job+business combination. A lone
old job or a bare partnership does not become a strong candidate (status REVIEW,
or skipped). Candidates carry the inputs the existing Lead Scoring Engine
consumes (`job volume, freshness, technology match, project/business signals,
source/evidence confidence`) — no new scoring algorithm is introduced here, and
candidates are never auto-promoted to Leads.

## Provenance, evidence & transparency

Every record carries `data_provenance` (REAL/SYNTHETIC). Production defaults to
REAL; synthetic is opt-in and always labelled. Traceability is preserved end to
end: Company → OpportunityCandidate → BusinessSignals + Jobs → SourceReferences.
Because no real business source is connected, the production dashboard shows the
honest empty state ("No verified Indian IT opportunities available yet.").

## Safety & compliance

Reuses the single safe HTTP client: URL scheme + SSRF host validation, response
content-type allowlist (rss/atom/xml/json/html), max response size, bounded
redirects, robots.txt policy, transient-only retries, and credential-free
logging. No page JavaScript is executed and no binaries are downloaded.

## Limitations

- No real business source is connected — this is architecture + mocked tests.
- Company extraction from free-text news is limited (feeds must provide it, or the
  signal is flagged REVIEW).
- Keyword classification can misorder overlapping cues (e.g. "engineering team" +
  "staff augmentation"); ordering is configurable.
- `OpportunityCandidate` is not yet promoted into a `Lead` or surfaced in the
  frontend — planned follow-ups.

## Next recommended source

A single official **company newsroom RSS** for a known Indian IT company (permitted
terms) — implement one feed URL, run `python -m collectors.business.collect
--source company_newsroom --url <feed> --dry-run`, verify classification, then
promote that one source to CONNECTED.
