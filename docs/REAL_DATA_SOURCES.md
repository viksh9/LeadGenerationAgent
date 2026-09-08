# Real Data Sources

The complete, **truthful** source matrix. Status reflects actual code + configuration
+ verified connectivity — never inferred. Regenerate the live view any time with
`python -m app.audit source-readiness` and `python -m app.collectors list`.

Status vocabulary: `NOT_IMPLEMENTED` (no collector) · `IMPLEMENTED` (collector exists)
· `NOT_CONFIGURED` (missing credentials/board) · `CONFIGURED` · `CONNECTED` (a real
request succeeded) · `LIVE_VERIFIED` (real request + validated response) ·
`REQUIRES_REVIEW` · `MANUAL_SOURCE_REQUIRED` · `DISABLED`.

## Source matrix

| Source | Category | Purpose | API / Access method | Credentials | India coverage | Data types | Evidence tier | License / terms | Implementation | Configuration | Live status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Adzuna** | JOB (aggregator) | IT job postings | REST search API (`api.adzuna.com/v1/api/jobs/in/search`) | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Yes (`in`) | Jobs, company, location, tech, dates, URL | TIER_2 | Commercial use REQUIRES_REVIEW; limited free quota | IMPLEMENTED | CONFIGURED | **LIVE_VERIFIED** |
| **Jooble** | JOB (aggregator) | IT job postings | REST POST API (`jooble.org/api/{key}`) | `JOOBLE_API_KEY` | Yes | Jobs, company, location, salary (when given), dates | TIER_3 | Free key ~500-request lifetime budget (enforced) | IMPLEMENTED | NOT_CONFIGURED | NOT_TESTED |
| **Greenhouse** | COMPANY / ATS | Official ATS job board | Public board API (`boards-api.greenhouse.io/v1/boards/{board}/jobs`) | none (public); board token required | Company-dependent | Jobs, dept, location, description, URL, timestamps | TIER_1 | Public postings only; no candidate data | IMPLEMENTED | DISCOVERY_REQUIRED (`GREENHOUSE_BOARDS`) | NOT_TESTED |
| **Lever** | COMPANY / ATS | Official ATS postings | Public Postings API (`api.lever.co/v0/postings/{site}?mode=json`) | none (public); site handle required | Company-dependent | Jobs, team, location, workplace type, URL, timestamps | TIER_1 | Public postings only; no candidate/recruiter data | IMPLEMENTED | DISCOVERY_REQUIRED (`LEVER_SITES`) | NOT_TESTED |
| **Official company career pages** | COMPANY / OFFICIAL_CAREER | Official careers / JSON-LD JobPosting | Permitted page fetch + JSON-LD; SSRF-safe HTTP | none | Company-dependent | Jobs, company, tech, location | TIER_1 | Per-site robots + terms (REQUIRES_REVIEW) | IMPLEMENTED (per-company) | REQUIRES_REVIEW | NOT_TESTED |
| **Company newsroom / announcements** | NEWS / COMPANY_ANNOUNCEMENT | Official press/expansion/tech announcements | Permitted RSS/feed (`base_url`) | none | Yes (source-dependent) | Announcements, projects, expansion, tech signals | TIER_2 | Per-source terms; approval may be required | IMPLEMENTED (feed-driven) | NOT_CONFIGURED (no feed set) | NOT_TESTED |
| **RSS / business news** | NEWS / NEWS_BUSINESS | Business/technology news signals | Permitted RSS/Atom feed | none | Yes (source-dependent) | Project/contract/partnership/expansion signals | TIER_3 | Feed terms RESTRICTED — verify before enabling | IMPLEMENTED (feed-driven) | NOT_CONFIGURED (no feed set) | NOT_TESTED |
| **Government procurement / tenders** | TENDER / GOVERNMENT_PROCUREMENT | Public IT tenders/RFPs | No permitted public API on CPPP; **manual import** (`scripts/import_tender.py`) | none | Yes | Tender title, org, dates, value (when published), status, URL | TIER_1 | Portal terms; anti-bot never bypassed | MANUAL_SOURCE_REQUIRED | n/a | n/a |
| **Government open data** | GOVERNMENT | Structured public datasets | Depends on dataset API/terms | dataset-specific | Varies | Varies | TIER_2 | REQUIRES_REVIEW per dataset | NOT_IMPLEMENTED | n/a | n/a |
| **Business database / contact provider** | BUSINESS_DATABASE | Company/contact enrichment | Licensed provider API | provider key | Varies | Company/contact data | TIER_2 | Commercial license REQUIRES_APPROVAL | NOT_IMPLEMENTED | n/a | n/a |

> The application's `SourceCategory` enum groups these as JOB / COMPANY / NEWS /
> TENDER / GOVERNMENT / BUSINESS_DATABASE / PROJECT / OTHER. The seven strategy
> categories map onto those groupings (ATS = COMPANY, aggregator = JOB, etc.).

## Manual collection

```bash
python -m app.collectors list                          # sources + runnable + status
python -m app.collectors run --source adzuna           # real collection (persists)
python -m app.collectors run --source adzuna --dry-run # real request, validate, persist nothing
python -m app.collectors run --all --dry-run           # every runnable source, isolated
python -m app.audit source-readiness                   # per-source readiness verdict
python -m app.audit live-sources --source adzuna       # real connectivity check
```

Government tenders are imported manually (no permitted public API):
`python scripts/import_tender.py …`.

## Guarantees

- **Failure isolation** (§35): one source failing (auth/rate-limit/error) never
  stops the others — the orchestrator runs each independently.
- **No fake fallback** (§50): source unavailable / API failure / empty / parse
  error / quota exceeded → **no data**, never fabricated records.
- **Budgets** (§31): per-source lifetime/request budgets are enforced (e.g.
  Jooble); when exhausted, collection stops cleanly.
- **Provenance**: every raw record carries source, provider, source record id,
  source URL, timestamps, content hash, and `data_provenance = REAL`.
- **Security**: outbound requests are SSRF-guarded, timed out, size-limited, and
  robots/terms-checked for permitted feeds; credentials come from the environment
  only and are never exported or logged.
