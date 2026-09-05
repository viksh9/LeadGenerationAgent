# Frontend: Outreach

## What it is

A **preparation** workspace: for every lead the pipeline produced messaging, the
Outreach page lets a BD user review the queue, read the recommended message,
edit it locally, and copy it to send **manually**. Nothing is sent from the app —
no email, LinkedIn, or call automation, no bulk send (out of scope).

## Preparation vs. sending

Phase 1 is review + copy only. There is no send/activity API, so:

- **Message status** is a documented **frontend preparation status** derived from
  the related lead status (not a persisted outreach lifecycle).
- **Message edits** live in component state — they are not saved to the backend;
  a Reset (with confirmation) restores the generated text.
- The **Follow-up queue** shows a placeholder until outreach activity tracking
  exists (no invented "contacted N days ago" data).

## Data source (Phase 1)

No backend Outreach entity. Items are derived from leads:

- Hook: `hooks/useOutreach.ts` — reuses the shared, cached `GET /leads` query.
- Adapter: `services/outreach.ts` — all mapping/parsing/derivation/queue logic.

## Mapping (`mapLeadToOutreach`)

Pass-through: company, industry, role (`poc_title`), priority, score,
recommendedAction, opportunitySummary, technologies, evidence (`signal_*`,
`source_*`, `signal_confidence`). Derived (documented):

- **Message**: `parsePitch` splits the persisted `recommended_pitch` into a
  Subject + body. Per-channel **LinkedIn message** and **call talking points** are
  not persisted → shown as "not generated", never fabricated.
- **Message strategy**: derived from the (derived) opportunity type.
- **Message status**: derived from the lead status.
- **Opportunity context** (`opportunityType`, `staffingNeed`, `urgency`): reuses
  `services/opportunities.ts`.
- **Ready vs. needs review**: `ready` = HOT/WARM + pitch + target role + not a
  weak signal; otherwise it lands in **Needs review** with reasons (missing
  pitch/role, low priority, weak signal, unclear opportunity).

## Confidence

**Pitch confidence** comes from the Pitch Generator and is **not persisted**, so
it shows "Not available" — the frontend does not compute a replacement.

## Queue, filters, sorting

- Queue split into **Ready for outreach** and **Needs review**, ordered HOT →
  WARM → … then score desc.
- Filters (URL-synced): priority, opportunity type, message status, target role,
  industry, minimum score + debounced search (company / opportunity / role /
  technology / signal). Removable chips + Clear all.
- Sort: priority (default), lead score, company, opportunity, created, signal
  date.

## Message tabs

The detail drawer has **Email / LinkedIn / Call** tabs. Email shows the editable
subject + body with copy; LinkedIn and Call show honest "not generated"
messages. Copy actions give inline "Copied" feedback (no alerts).

## Limitations

- Only the email-style pitch is available (no LinkedIn/call variants).
- No pitch confidence, no persisted outreach status/activity, no sending.
- Edits are local (not saved). Aggregation capped at the top ~100 leads.

## Future sending architecture

The UI consumes the typed `OutreachItem` shape, so a future Outreach/activity
backend (`outreach_id`, `lead_id`, `contact_id`, `channel`, `message`, `subject`,
`status`, `sent_at`, `response_at`, `follow_up_at`, `owner`, `template_id`) can
replace `useOutreach` + the derivation in `services/outreach.ts`, lighting up
persisted statuses, follow-ups, and (later) real send actions — without
rewriting the components.
