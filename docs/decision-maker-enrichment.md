# Decision-Maker & Contact Enrichment

This engine answers *"who should we talk to at a company, and do we have a real,
verified way to reach them?"* — while keeping **three distinct concepts** apart and
never letting one silently become another.

> **Role recommendation ≠ person identification ≠ contact verification ≠ outreach
> permission.**

## Three distinct concepts

State this explicitly, and re-state it wherever the data is displayed:

1. **Recommended stakeholder ROLE (no person).** A role *type* likely to own or
   influence the decision (e.g. "VP Engineering"). Deterministic and **always
   available**. No person is named, no email is produced, no network is touched.
2. **Verified real PERSON.** A named individual, present **only** when found in a
   permitted, traceable source. Otherwise it stays **NULL** — a person is never
   assumed, guessed, or fabricated.
3. **Verified business CONTACT.** A *published business* email/contact (e.g. a
   role-based address), never a personal or guessed one.

A recommended role is never presented as a person; a person is never presented as a
verified contact; and none of the three implies that outreach is permitted.

## Role recommendation (roles only)

- **Engine**: `enrichment/poc_finder.py` (existing `POCFinder`), wrapped by
  `enrichment/stakeholder.py`.
- **Drivers**: opportunity analysis, detected signals, hiring, and industry.
- **Output**: recommended role(s), each with a **category**, a **relevance** score,
  and a grounded **reason**.
- **Guarantees**: deterministic; **no person, no email, no profile, no network, no
  LLM**. If there is no usable evidence, nothing is guessed.

See [poc-intelligence.md](poc-intelligence.md) for the role catalogue, signal /
opportunity / industry mappings, and relevance scoring.

## Person & contact enrichment (official-source only)

- **Enricher**: `enrichment/person_enricher.py` (`OfficialCompanySourceEnricher`),
  implementing `BasePersonEnricher` and `BaseContactEnricher`.
- **What it fetches**: **only** the company's own official pages — `/`, `/about`,
  `/leadership`, `/team`, `/management`, `/contact` — through the existing
  `SafeHttpClient` (HTTPS, SSRF guard, private-network block, response-size cap, no
  credentials). No arbitrary third-party URLs; no open-web crawling.
- **Real people**: extracted from schema.org JSON-LD `Person` entries — name +
  jobTitle.
- **Real business contacts**: extracted from published `mailto:` addresses that are
  **role-based** (`info@`, `sales@`, `careers@`, `procurement@`, …) or on the
  **company's own domain**.
- **Absent data stays NULL** — nothing is filled in by inference.

### The no-guessing policy (explicit prohibitions)

The enricher **NEVER**:

- fabricates a person, email, phone, or profile;
- guesses addresses such as `firstname.lastname@company.com` from a person's name;
- constructs a LinkedIn or other profile URL from a name (e.g.
  `linkedin.com/in/first-last`);
- scrapes third-party or private profiles, or bypasses authentication or robots;
- accepts personal-looking addresses — a random `someone@gmail.com`-style address
  is **rejected**;
- performs SMTP probing or credential verification — email is **format-validated
  only**.

If the official pages publish nothing extractable, the result is honestly **empty /
NULL**. Real careers and leadership pages are frequently JS-rendered SPAs whose
people are not present in the server HTML; there is **no browser automation** by
policy, so people are found only when published as JSON-LD.

## Person resolution & de-duplication

Persistence and resolution live in `enrichment/enrichment_service.py`, which stores
`DecisionMaker` rows. Resolution is **deterministic**:

- **Name alone NEVER merges two distinct people.**
- The **same person observed under a different role** → `REVIEW_REQUIRED` (never a
  silent overwrite).
- **Idempotent upsert** — re-running updates the existing row rather than creating
  duplicates.
- **Corroborating sources** are accumulated in `source_references`; **history is
  preserved**.

## Verification, freshness & confidence axes

`DecisionMaker` rows carry **distinct confidence axes — never collapsed into one**:

| Axis | Question |
| --- | --- |
| `identity_confidence` | How confident are we this is a real, correctly-identified person? |
| `role_confidence` | How confident are we in the observed role/title? |
| `company_confidence` | How confident are we this person belongs to this company? |
| `contact_confidence` | How confident are we in the business contact (if any)? |
| `evidence_confidence` | How strongly does the available evidence support the record? |

Each row also carries:

- **`verification_status`**: `VERIFIED` / `PARTIALLY_VERIFIED` / `UNVERIFIED` /
  `STALE` / `CONTRADICTED`.
- **`freshness_score`**: reuses `verification.freshness` — a person or contact is
  **not** assumed current forever.
- **`provenance = REAL`**.

**Evidence tier.** An official company source is `TIER_1` — stronger than
aggregators.

## Outreach readiness (separate axis)

`enrichment/outreach.py` computes a deterministic readiness state, **separate from**
`lead_score`, `evidence_confidence`, and `contact_confidence`:

| State | Meaning |
| --- | --- |
| `READY` | A verified, current way to reach an appropriate stakeholder exists. |
| `ROLE_ONLY` | Only a recommended **role** is available — no verified person/contact. **A recommended role alone is never `READY`.** |
| `RESEARCH_REQUIRED` | Some signal, but not enough verified contact information yet. |
| `HOLD` | Stale or contradicted data — do not act. |

## Provider architecture

Enrichers are pluggable behind `BasePersonEnricher` / `BaseContactEnricher`.
`config/sources.yaml` registers two providers:

| Provider | Status | Key | Notes |
| --- | --- | --- | --- |
| `official_company_people` | **IMPLEMENTED**, `REQUIRES_REVIEW` | none | The `OfficialCompanySourceEnricher` above; pending a privacy/terms review before enabling. |
| `business_contact_provider` | **`PLANNED` / `NOT_IMPLEMENTED`** | (would require credentials) | Placeholder for a licensed B2B contact provider — requires a commercial licence + credentials + usage policy; commercial use `REQUIRES_APPROVAL`. **No paid provider is wired.** |

Provider credentials are never exposed through the API.

## Privacy & data minimization

- **Business contacts are preferred over personal data.**
- **No** personal home address, family, private account, or private phone is
  collected.
- Only publicly published, business-relevant, source-linked, **minimized** data is
  stored.
- No SMTP probing; no credential verification; email is format-validated only.

## APIs

Read-only over stored real data, plus one action endpoint that runs the real, safe,
official-source fetch. **Provider credentials are never exposed.**

| Method & path | Purpose |
| --- | --- |
| `GET /contacts` | List verified contacts; filters `company` / `role_category` / `verification_status` / `people_only`; paginated. |
| `GET /contacts/{id}` | One contact / decision-maker record. |
| `GET /companies/{id}/decision-makers` | Decision-maker rows for one company. |
| `GET /companies/{id}/contacts` | Verified contacts for one company. |
| `GET /leads/{id}/stakeholders` | Recommended roles + verified people/contacts + outreach readiness for a lead. |
| `POST /companies/{id}/enrich` | Run the real, safe, official-source fetch for a company (own official pages only). |

## Testing (opt-in live)

- The default `pytest` suite makes **no external network calls**: the enricher is
  unit-tested with **real-shaped HTML over a mocked transport**, and no credentials
  are required.
- **No live enrichment has been run against a real company** in this change.
- Live enrichment is **opt-in only**, subject to the same `SafeHttpClient` safety
  guards and the `REQUIRES_REVIEW` privacy/terms gate — own-domain official pages
  only, robots/terms respected, no credentials logged.

## Real-data safety

Nothing is fabricated; UNKNOWN/NULL is preserved. No person is ever claimed without
a permitted, traceable source, and no business contact is ever guessed. Absent data
stays NULL, and `provenance` flows through unchanged as `REAL`.
