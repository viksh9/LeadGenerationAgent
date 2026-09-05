# Frontend: Contacts / Decision-Maker Intelligence

## Role, not person

Phase 1 is **role intelligence**, not verified-person discovery. The pipeline
recommends a decision-maker **role** per lead (`poc_title`, e.g. "VP of
Engineering", "CIO"). It does **not** identify a real person — `poc_name` is
currently always empty.

The UI therefore shows **"Recommended Role"** and **"Person not identified
yet"**. It never fabricates names, emails, phone numbers, or LinkedIn URLs. A
person is only ever shown if the backend actually provides `poc_name` /
`poc_linkedin_url`.

## Current data source (Phase 1)

No backend Contact/Person entity exists. Recommendations are derived on the
frontend from the existing leads data:

- Hook: `hooks/useContacts.ts` — reuses the shared, cached
  `GET /leads?page_size=100&sort_by=lead_score` query (no duplicate requests).
- Adapter: `services/contacts.ts` — the single place all mapping, derivation,
  filtering, sorting and aggregation live.

## Mapping (`mapLeadToContactRecommendations`)

A lead with a recommended role (`poc_title`) produces one
`ContactRecommendation` (an array is returned to match the future multi-role
shape). Pass-through fields: company, industry, location, role (`poc_title`),
personName (`poc_name`), linkedinUrl, publicContact, recommendedAction, priority,
status, and all evidence (`signal_*`, `source_*`, `signal_confidence`).

Derived (documented, deterministic):

- **`decisionMakerType`** — keyword mapping of the role text →
  TECHNICAL / BUSINESS / DELIVERY / PROCUREMENT / VENDOR / HR.
- **Opportunity context** (`opportunityType`, `staffingNeed`, `urgency`) — reuses
  `services/opportunities.ts` so context matches the Opportunities page.

## Relevance & confidence

- **Relevance** reuses the **related lead's score** (`lead_score`) as the Phase-1
  proxy, banded HIGH (≥80) / MEDIUM (≥60) / LOW. The POC engine's per-role
  relevance/confidence is **not persisted**, so we reuse the existing lead score
  rather than inventing a new one (`§9/§10/§20` — no second scoring system).
- **Confidence** is the band label of that relevance.
- **Reason** (the POC engine's explanation) is not persisted → shown as
  "Not available" rather than generic frontend text.

## Filters, sorting, grouping

- Filters (URL-synced): decision-maker type, priority, opportunity type,
  confidence, role, industry, minimum relevance, plus debounced company/role
  search. Removable chips + Clear all.
- Sort: relevance (default), company, lead score, priority, updated.
- Views: **Table** and **By company** (primary = highest-relevance role,
  secondary = the rest). **Top target roles** ranks the most-recommended roles by
  count + average relevance.

## Limitations

- Role recommendations only exist for leads whose pipeline stored a `poc_title`.
- No verified people, emails, phones, or profile URLs (not collected).
- Relevance/confidence are the lead score and its band, not per-role POC metrics.
- Aggregation is capped at the top ~100 leads.
- No Send Email / LinkedIn / Call actions — those belong to the Outreach phase.

## Future person enrichment

The UI consumes the typed `ContactRecommendation` shape, so a future backend
Contact entity (`contact_id`, `company_id`, `person_name`, `job_title`,
`linkedin_url`, `business_email`, `phone`, `source`, `verified_at`, `confidence`)
can replace `useContacts` + the derivation in `services/contacts.ts` without
changing the components. Verified-person fields would light up the "Verified
person" / "Open profile" affordances that currently show "Person not identified
yet".
