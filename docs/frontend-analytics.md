# Frontend: Analytics

## What it is

A data-driven analytics workspace summarizing lead quality, opportunity
distribution, technology demand, outreach readiness, and recent activity. Every
metric is derived from real lead data — nothing is fabricated. Sections without
enough data show "Not enough data yet".

## Data source (Phase 1)

No backend analytics/aggregate endpoint exists. Metrics are derived from the
leads already fetched:

- Hook: `hooks/useAnalytics.ts` — reuses the shared, cached `GET /leads` query
  (one request, capped at ~100 leads — **no per-chart fetch**).
- Layer: `services/analytics.ts` — all calculations live here (`calculateLeadStats`,
  `calculatePriorityDistribution`, `calculateSignalDistribution`,
  `calculateOpportunityDistribution`, `calculateIndustryStats`,
  `calculateTechnologyDemand`, `calculateLeadTrend`, `calculateOutreachReadiness`,
  `calculateSourceStats`, `buildAnalytics`). No aggregation lives in JSX.

Because of the ~100-lead cap, the page labels analytics **"based on available
lead data"** and shows "top N of M leads" when the dataset is truncated — it does
not present partial data as complete company-wide analytics.

## Metrics

- **KPIs**: total leads, hot leads, qualified (status QUALIFIED/PROPOSAL/WON),
  average score, high staffing need, ready for outreach.
- **Distributions**: priority (donut), business signal, opportunity type, and
  **lead status** (bar). Opportunity type reuses `services/opportunities`.
- **Trends**: average lead score over time and new leads over time, bucketed by
  `signal_date` (falling back to `created_at`), needing ≥2 dates to render.
- **Industry** and **Technology** tables (lead count, hot, avg score, high
  staffing / top opportunity).
- **Outreach readiness**: ready / needs review / missing POC / missing pitch /
  low confidence.
- **Leads by source** (only when `source_name` exists) — counts only.
- **Recent high-value signals** and **Top opportunities** → `/leads/:id`.

## Status distribution ≠ conversion (important)

The lead-status section is a **current status distribution**, not a historical
conversion rate. The pipeline stores only the lead's *current* status, not its
transition history, so no conversion rate is computed. There are likewise no
revenue metrics — none exist in the data.

## Filtering

URL-synced filters (`/analytics?range=30d&industry=BFSI&priority=HOT&...`): date
range (all / 7d / 30d / 90d), industry, priority, signal type, opportunity type.
All charts and tables recompute from the filtered set. **Custom date range** is
not implemented in Phase 1 (documented limitation) — the four presets cover the
common cases without a date picker.

## Export

**Export CSV** performs a client-side export of the derived industry analytics
table (no backend export endpoint, no private/personal data).

## Limitations

- Derived from the top ~100 leads (dataset cap).
- No conversion rates, no revenue, no source "effectiveness" ranking.
- Trends use one date field consistently; sparse data shows an empty state.
- Custom date range not implemented.

## Future analytics API

A future `GET /analytics` aggregate endpoint (server-side distributions, trends
over the full dataset, and true status-transition history for conversion) can
replace `useAnalytics` + the calculations in `services/analytics.ts` without
changing the components, which consume the typed `AnalyticsData` shape.
