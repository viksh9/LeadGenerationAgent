# Evidence Verification & Source Confidence Engine

Answers: **"How confident are we that this business signal is real, current,
relevant, and supported by reliable evidence?"** — while keeping FOUR distinct
numbers separate. A lead can be commercially HOT yet only PARTIALLY_VERIFIED.

## The four numbers (never collapsed into one)

| Number | Question | Where |
| --- | --- | --- |
| **Source reliability** | How trustworthy is the *source itself*? | `verification/source_reliability.py` |
| **Evidence confidence** | How strongly does the *available evidence* support the claim? | `verification/signal_verification.py` |
| **Signal confidence** | How confident are we the *signal actually exists*? | `verification/signal_verification.py` |
| **Lead score** | How *commercially valuable* is it? | `intelligence/lead_scorer` / `company_pipeline` (unchanged) |

Examples from the demo: `lead_score 100 (HOT)` + `evidence_confidence 74` +
`source_reliability 45` (TIER-3 only) → VERIFIED; `lead_score 14 (LOW)` +
`evidence_confidence 39` → UNVERIFIED / DISCARD.

## Domain model

`EvidenceRecord` (references `RawSourceRecord`/`JobRecord`, no raw-payload
duplication), `EvidenceConflict`, `EvidenceClaim`. `Lead` gains
`source_reliability`, `evidence_confidence`, `freshness_score`,
`independent_support_count`, `verification_status`, `lead_readiness`,
`verification_reason`, `verified_at` — all separate from `lead_score`.

## Verification lifecycle

```
Lead (+ evidence from jobs/signals)
  → source reliability (tier) + freshness (per signal type)
  → corroboration (independence grouping — syndicated != independent)
  → conflict detection
  → verification_status + the four scores  (persist EvidenceRecords, idempotent)
  → lead_readiness
```

Wired into the company pipeline (`_verify_company`) and re-runnable via
`EvidenceVerificationService.verify_lead` / `POST /leads/{id}/verify`.

## Verification status

- **VERIFIED** — reliable source, sufficiently current, evidence supports the
  claim, no meaningful contradiction. *Never VERIFIED merely because a URL exists.*
- **PARTIALLY_VERIFIED** — some support, some uncertainty.
- **UNVERIFIED** — evidence exists but is insufficient / source too weak.
- **CONTRADICTED** — reliable evidence conflicts with another reliable source.
- **STALE** — was valid but outside the freshness window.

## Source trust tiers (configurable)

`config/evidence.py` maps sources to TIER_1 (official career page / company site /
government / tender portal) → TIER_2 (official ATS / licensed provider / reputable
publication) → TIER_3 (secondary aggregator / syndication) → TIER_4 (unknown).
Change tiers without touching verification logic.

## Freshness policy (per signal type)

Configurable windows per signal type (hiring, project, tender, expansion, …) using
`published_at` / `observed_at` / `updated_at` / closing/expiry dates / source
status. A closed job or expired tender is STALE; an old item the source marks
still-active keeps a floor. Never invents dates.

## Corroboration & syndication

**The same job on 10 sites is NOT 10 confirmations.** Syndicated copies (same
canonical job / same content hash) collapse into one `EvidenceIndependenceGroup`;
only distinct groups count as `independent_support_count`. An official source
among the independent set adds a corroboration bonus.

## Conflict handling

`verification/conflicts.py` detects active-vs-closed status, project-status,
company-identity, location, title, and date conflicts. Conflicts are recorded
(never silently discarded); the more authoritative (lower-tier) source is
preferred explicitly. A HIGH-severity conflict makes the lead CONTRADICTED.

## Lead readiness (evidence-based)

`READY` (verified + current + meaningful) · `REVIEW_REQUIRED` (commercially
interesting but insufficient evidence) · `HOLD` (stale or contradicted) ·
`DISCARD` (unsupported). Weak/unverified data can never silently become a
high-confidence production lead.

## Claims

`EvidenceClaim` supports claim-level verification (claim text + supporting /
contradictory sources). Claims are never created without evidence.

## Versioning & idempotency

`verification_version` / `VERIFIER_RULES_VERSION` allow re-verification without
losing history. Re-verifying a lead replaces its evidence for the current version
(delete-then-recreate) — repeated verification never creates duplicate evidence.
Raw data is never modified.

## Live checks (opt-in)

`verification/url_validation.py` reuses the collector SSRF/scheme guards. Default
verification makes **no network calls**; live URL checks are opt-in only, respect
robots/terms/rate limits, and never crawl arbitrary domains. No LLM, no scraping.

## API

- `GET /leads/{id}/verification` — the four scores + status + supporting sources +
  conflicts + reason.
- `GET /leads/{id}/evidence` — evidence records.
- `POST /leads/{id}/verify` — re-verify (idempotent).

## Frontend

Lead detail shows an **Evidence Verification** panel: status + readiness badges
(honest colours — not green just because a record exists), the four score meters,
independent vs syndicated source counts, supporting sources (name, tier, URL,
date, reliability), conflicts, and a human-readable reason. The dashboard shows a
**Data-trust** row (verified / partial / unverified / stale / contradicted) with a
DEMO label when only synthetic data is present.

## Real-data safety

Nothing is fabricated; UNKNOWN/NULL is preserved. Synthetic never becomes
"Verified" implicitly — provenance flows through unchanged. No real source is
connected, so current verification runs over clearly-labelled SYNTHETIC demo data.

## Limitations / TODO

- Verification currently runs on company-level leads; per-signal (BusinessSignal)
  persistence of `SignalVerificationResult` rows is a natural next step.
- Claim rows (`EvidenceClaim`) have a model + tests but are not yet auto-generated
  in the pipeline.
- Live URL reachability checks are scaffolded (opt-in) but not enabled.
- No real source/credential is configured, so no real evidence has been verified.
