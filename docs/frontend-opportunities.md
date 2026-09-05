# Frontend: Opportunities

## Lead vs. Opportunity

- A **Lead** is a detected company/business signal (what `GET /leads` returns).
- An **Opportunity** is a qualified business possibility (staffing, staff
  augmentation, technology implementation, vendor engagement) inferred from a
  lead's signals.

In the current product there is **one opportunity per lead**.

## Current data source (Phase 1)

There is **no backend Opportunity entity or endpoint**. Opportunities are
derived on the frontend from the existing leads data:

- Hook: `hooks/useOpportunities.ts` — reuses the shared, cached
  `GET /leads?page_size=100&sort_by=lead_score&sort_order=desc` query (no
  duplicate requests) and maps the items to `Opportunity[]`.
- Adapter: `services/opportunities.ts` — the single place all mapping,
  derivation, filtering, sorting and aggregation live.

## Mapping logic (`mapLeadToOpportunity`)

Pass-through (unchanged from the lead):

| Opportunity field | Lead field |
|---|---|
| `leadId` | `id` |
| `company` / `industry` | `company_name` / `industry` |
| `score` / `priority` / `status` | `lead_score` / `lead_priority` / `status` (the scoring engine's output — no second frontend score) |
| `businessReason` | `opportunity_summary` |
| `estimatedHiring` | `estimated_hiring` |
| `technologies` | `technologies` |
| `pocRole` / `pocName` / `pocLinkedin` | `poc_title` / `poc_name` / `poc_linkedin_url` |
| `recommendedAction` | `recommended_action` |
| `signalType` / `signalTitle` / `signalDate` | `signal_*` |
| `sourceName` / `sourceUrl` / `signalConfidence` | `source_*` / `signal_confidence` |

Derived (documented, deterministic — **not fabricated data**):

- **`opportunityType`** — from `signal_type` (+ hiring size). e.g.
  `PROJECT_AWARD → Project Driven Hiring`, `VENDOR_REQUIREMENT → Vendor
  Opportunity`, `HIRING` with ≥10 hires → `Staff Augmentation`, any of those with
  ≥25 hires → `Large-Scale Ramp-Up`, unknown signal → `Low Confidence`.
- **`staffingNeed`** — banded from `estimated_hiring` (≥25 HIGH, ≥10 MEDIUM, ≥1
  LOW, else UNKNOWN).
- **`urgency`** — banded from **signal recency** (≤7d CRITICAL, ≤30d HIGH, ≤60d
  MEDIUM, else LOW; no date → UNKNOWN), with a human reason. `now` is injectable
  so it is unit-testable.

Never fabricated (shown as **"Not available"**):

- **`confidence`** (opportunity confidence) — always `null`; not persisted.
- **Estimated team size range** — only the single `estimated_hiring` number is
  shown (e.g. "45 engineers"), never an invented "40–45" range.
- **Secondary POC roles** and relevance scores — not persisted.

## Scoring source

The opportunity score and priority are the **lead scoring engine's** values
(`lead_score`, `lead_priority`). The frontend does not compute a second score.

## Filters, tabs, sorting

- Filters (URL-synced): opportunity type, priority, staffing need, urgency,
  industry, technology, status, plus debounced search (company / signal title /
  type / technology / business reason).
- Quick tabs: All, Hot, High staffing need, High urgency, Project driven, Staff
  augmentation, Vendor — counts derived from the dataset.
- Sort: score (default), urgency, estimated team, signal date, created date.
- Funnel + type-distribution chart are computed from the full derived set.

## Current limitations

- Aggregation is limited to the top ~100 leads (dataset cap in the hook).
- `opportunityType` / `staffingNeed` / `urgency` are frontend heuristics over
  persisted signal fields, not the backend's `opportunity_analysis`.
- No opportunity confidence, team-size range, or secondary POC roles (not
  persisted).
- Opportunity status is the related lead's status (no separate lifecycle).

## Future dedicated Opportunity API

The UI consumes the typed `Opportunity` shape only, so a future
`GET /opportunities` / `GET /opportunities/:id` (with `opportunity_id`,
`company_id`, `lead_ids`, `opportunity_type`, `estimated_value`,
`estimated_team_size`, `staffing_need`, `urgency`, `confidence`, `technologies`,
`target_roles`, `status`) can replace `useOpportunities` + the derivation in
`services/opportunities.ts` without changing the components.
