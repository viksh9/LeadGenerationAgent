# Company Intelligence & Entity Resolution

Answers: **"Which real company does this record belong to, and what verified
business intelligence can we aggregate about it?"** — resolving the same company
across sources without false merges, then aggregating company-level intelligence.

```
Raw source records → normalized identity → CANONICAL COMPANY
  → company source references + evidence
  → company signals + canonical-job hiring intelligence
  → company opportunity profile
```

## Company data model

`Company` (canonical entity): canonical/legal/normalized name, primary + alternate
domains, industry/sub-industry, `company_type` (+ multiple `company_types`), HQ
country/state/city, `india_presence`/`india_locations`, size band, employee count
(+ source), founded year, public flag, `parent_company_id`, identity/evidence
confidence, verification status, provenance, first/last seen. **Unknown facts stay
NULL** — never fabricated. Plus `CompanySourceReference` (every source's original
representation, never overwritten), `CompanyRelationship` (parent/subsidiary/
brand/…, evidence-backed only), `CompanyResolutionCandidate` (review queue), and
`CompanyEvent` (history). `Lead.company_id` links a lead to its company.

## Entity resolution strategy

`CompanyEntityResolver` is deterministic and explainable (no LLM). It uses
**candidate blocking** (exact domain / exact normalized name / shared leading
token — indexed, no O(N²) scan) then layered, weighted matching:

- **High-value:** exact verified domain match, official website, legal-name match.
- **Medium:** normalized name, email domain, HQ city.
- **Low:** token overlap, same city.

Statuses: `EXACT_MATCH` → `HIGH_CONFIDENCE_MATCH` → `POSSIBLE_MATCH` →
`REVIEW_REQUIRED` → `NO_MATCH` → `CONFLICT`, each with `matching_factors`,
`conflicting_factors`, and an explanation.

## How false merges are prevented

- **A name match alone never links** — only a verified domain (or legal-name)
  match yields high confidence.
- **A name match with a CONFLICTING domain → `CONFLICT`/REVIEW**, never an
  auto-merge (Scenario F).
- **Different name + different domain → `NO_MATCH`** → separate company
  (Scenario B); "ABC Technologies" and "ABC Technology Solutions" are not merged.
- Uncertain matches create a `CompanyResolutionCandidate` (PENDING) for human
  review — the system never silently decides.

Verified: same domain + name variant → `EXACT_MATCH`/LINK (Scenario A); name-only
→ never LINK.

## Parent/subsidiary relationships

`CompanyRelationship` (PARENT_OF / SUBSIDIARY_OF / BRAND_OF / DIVISION_OF /
ACQUIRED_BY / MERGED_WITH / RELATED_TO) links separate company entities — related
entities are **not collapsed into one**. Every relationship carries evidence,
confidence, and source; ownership/acquisitions are **never inferred** without
evidence.

## Canonical jobs → company hiring intelligence

`CompanyIntelligenceService` aggregates **canonical `JobRecord`s** (deduplicated —
10 aggregator copies of one job count once), producing per company: technology
demand (`active_jobs`/`recent_jobs`/`demand_strength`), role demand, hiring
locations, a **hiring trend** (RAPIDLY_INCREASING…UNKNOWN, with a sample-size
guard — small samples return UNKNOWN, never a guessed trend), company signals,
opportunity, and evidence. Location intelligence distinguishes **hiring location**
from a **confirmed office** (offices require explicit HQ evidence, not a single
remote job).

## Company-level leads & deduplication

`upsert_companies_from_jobs` groups canonical jobs by normalized company, resolves
each to a `Company`, links the existing company-level `Lead` (`company_id`), and
propagates verification confidence. Re-running is **idempotent** — repeated
ingestion updates the same company, never creating duplicates — and records
`CompanyEvent` history ("why did this become a HOT lead?").

## Source priority & evidence

Reuses the Prompt-28 source tiers / evidence verification: when company facts
conflict across sources, the more authoritative source is preferred; company
evidence confidence and verification status flow from the linked lead's verified
evidence.

## APIs

`GET /companies` (search/filter/sort/paginate), `GET /companies/{id}`,
`/companies/{id}/intelligence|jobs|signals|opportunities|evidence|history`,
`GET /company-resolution/review`, `POST /company-resolution/{id}/resolve`
(MERGE | KEEP_SEPARATE | IGNORE). Logic lives in services.

## Frontend

The Company Details page shows a **Company Intelligence (verified backend)**
panel: verification status, identity confidence, active/recent openings, hiring
trend, technology demand with strength, India locations, evidence (reliability /
evidence confidence / independent sources), and history — with an honest "No
verified backend company data available yet" fallback and a DEMO label for
synthetic data. (The Companies list still runs client-side; wiring it to the new
`/companies` API is a follow-up.)

## Real vs synthetic

Every company carries `data_provenance`; production defaults to REAL-only.
**No real source is connected**, so companies are currently built over
clearly-labelled SYNTHETIC demo data. Nothing is fabricated; unknown stays unknown.

## Limitations / TODO

- Full merge machinery on `MERGE` review relinks leads + removes the tentative
  company; deeper reference migration is a follow-up.
- Companies list page not yet wired to `/companies` (client-side grouping remains).
- No real source/credential configured — no real company data has been resolved.
