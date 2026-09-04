# Lead Scoring

The `LeadScorer` (`intelligence/lead_scorer.py`) assigns every lead a **0–100
score** and a **priority**, using deterministic, explainable rules. It consumes
the detected signals, the opportunity analysis, and the lead's own fields — no
LLM, no network, no database, no FastAPI. All weights live in `ScoringConfig`.

> An earlier buying-stage scorer (`score_lead`) also lives in the module for
> backward compatibility; this document describes the current `LeadScorer`.

## Scoring categories

The score is the sum of eight categories whose maximums total 100, so the
breakdown **always sums to the final score** and each category is capped.

| Category | Key | Max | Basis |
| --- | --- | --- | --- |
| Large technology hiring | `large_technology_hiring` | 20 | `estimated_hiring` volume |
| New project / contract | `new_project_or_contract` | 20 | PROJECT_AWARD / CONTRACT / PROJECT_EXECUTION |
| Enterprise / government | `enterprise_project` | 15 | industry, company size, gov keywords, project value |
| Multiple relevant openings | `multiple_openings` | 15 | breadth of distinct roles/technologies |
| Expansion / transformation | `expansion_or_transformation` | 10 | EXPANSION / DIGITAL_TRANSFORMATION / TECHNOLOGY_INITIATIVE |
| Technology stack match | `technology_match` | 10 | detected technologies ∩ relevant set |
| Identifiable decision-maker | `decision_maker` | 5 | POC name / title / profile |
| Recency | `recency` | 5 | `signal_date` age |

### Hiring volume (max 20)

Banded on the reliably-known hiring count (`0` if missing — never invented):
`0–2 → 0–5`, `3–9 → 6–10`, `10–19 → 11–15`, `20+ → 20`.

### Project evidence (max 20)

Contributions: `PROJECT_AWARD = 20`, `CONTRACT = 16`, `PROJECT_EXECUTION = 12`.

### Enterprise / government (max 15)

Additive from explicit evidence — government keywords (+8), large company size
≥1000 (+5), enterprise industry (+5), project value ≥ ₹1M (+5), a large
transformation opportunity (+3) — capped at 15. Not every company is assumed to
be an enterprise.

### Technology match (max 10)

`round(matches × 3)`, capped at 10, against a **configurable** relevant-tech set
(Java, Spring, Python, React, AWS, Azure, Kubernetes, DevOps, …). This set is
meant to be tailored to the actual services being sold.

### Recency (max 5)

From `signal_date` vs current UTC: `0–7d → 5`, `8–30d → 4`, `31–90d → 2`,
`90d+ → 0`, missing → 0. **Future dates are ignored** (0 points).

## Priority thresholds

`80–100 = HOT`, `60–79 = WARM`, `40–59 = NURTURE`, `0–39 = LOW`
(reuses the `LeadPriority` enum).

## Anti-double-counting

- **Project evidence** takes the single strongest signal (max of AWARD /
  CONTRACT / EXECUTION), never their sum.
- **Hiring** (category A, *volume*) and **multiple openings** (category D,
  *breadth of distinct roles/technologies*) measure different axes, so they do
  not reward the same evidence twice.
- **Duplicate technologies** are de-duplicated before the technology-match count.
- Every category is independently capped at its maximum.

## Scoring confidence

Separate from the score, `scoring_confidence` (0–100, label HIGH/MEDIUM/LOW)
measures how much quality information backs the score: source present (+15),
signal strength (+20/+10), project evidence (+20), hiring info (+15),
technologies known (+15), signal date present (+15).

## Output

`LeadScoreResult`: `score`, `priority`, `score_breakdown` (per-category dict),
`positive_signals`, `negative_signals`, `explanation`, `scoring_confidence`,
`scoring_confidence_label` — all derived only from the supplied inputs.

## Configuration

`ScoringConfig` centralizes every weight, cap, contribution, threshold, and the
relevant-technology / enterprise-industry sets, so the model can be retuned for
different industries, service offerings, staffing models, or priorities without
touching the scoring logic.
