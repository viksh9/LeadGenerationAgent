# Lead Analysis Pipeline

`LeadAnalysisPipeline` (`intelligence/lead_pipeline.py`) is the end-to-end
orchestrator: it turns a raw lead into a fully analyzed, scored, and persisted
business opportunity by **sequencing the existing engines** — it contains no
business rules of its own.

It is synchronous, lightweight, and independent of FastAPI (no routes/request
objects), the network, and LLMs, so a future `POST /leads/analyze` can call it
directly.

## Architecture / data flow

```
raw lead (dict / schema object)
      │
      ▼
  normalize_lead()            trim, drop-empty, de-dup technologies/roles
      │                       (original payload never mutated)
      ▼
  SignalDetector.detect()     signal_types, strength, technologies, hiring, roles
      │
      ▼
  OpportunityAnalyzer.analyze()   opportunity_type, staffing need, urgency, ...
      │
      ▼
  LeadScorer.score()          score 0-100, priority, breakdown, confidence
      │
      ▼
  POCFinder.recommend()       primary/secondary decision-maker roles
      │
      ▼
  PitchGenerator.generate()   email / linkedin / call talking points
      │
      ▼
  LeadAnalysisResult  ──────► persist (Lead, status = NEW)
```

## Execution order

1. Normalize input → 2. Detect signals → 3. Analyze opportunity → 4. Score →
5. Recommend POC roles → 6. Generate pitch → 7. Build result → 8. Persist.
Each stage's output feeds the next; no engine logic is duplicated in the pipeline.

## Result (`LeadAnalysisResult`)

Frontend-friendly and fully JSON-serializable (`model_dump(mode="json")`):
`lead_id`, `company_name`, `lead_input`, `normalized_data`, `signal_analysis`,
`opportunity_analysis`, `scoring_result`, `poc_recommendation`, `pitch_result`,
`final_score`, `priority`, `recommended_action`, `status`, `already_existed`.

## Persistence

The calculated result maps onto the flat `Lead` model (company, source, signal,
project, technology, POC, score, priority, opportunity summary, recommended
action, recommended pitch, `status = NEW`, timestamps) via the repository.
Persistence is transactional: on failure the session is rolled back, the error is
logged, and a safe `LeadPipelineError` is raised — no partial commits, no raw DB
errors surfaced.

A session may be supplied (the future endpoint passes its request session) or the
pipeline opens and closes its own. `persist=False` runs analysis only.

## Duplicate handling

Deterministic upsert: a lead matching an existing row on **(company_name,
signal_title, source_url)** UPDATES that row (refreshing derived fields, keeping
the lifecycle `status`, setting `last_verified_at`) rather than creating a new
one. `already_existed` reports which path was taken. Duplicates are never created
silently.

## Reanalysis

`reanalyze(session, lead_id)` reconstructs the raw lead from the stored record and
re-runs the pipeline against that row, refreshing signal/opportunity/score/POC/
pitch and updating `last_verified_at` + `updated_at`. Lifecycle fields such as
`status` are preserved.

## Error handling & logging

Every stage is wrapped: internal exceptions become `LeadPipelineError` with the
failed stage (e.g. "Lead analysis failed during opportunity analysis.") — the
stage is identified without leaking internal detail. Structured logs cover
`pipeline_started`, `normalization_completed`, `signals_detected`,
`opportunity_analyzed`, `lead_scored`, `poc_recommended`, `pitch_generated`,
`lead_persisted`, `pipeline_completed`, and `pipeline_failed`, with safe context
(company name, stage, lead id). Secrets/credentials/PII are never logged.

## Deterministic behavior

For unchanged input, the intelligence outputs are identical run-to-run: signal
types, opportunity type, score, priority, POC recommendation, and pitch strategy.
Only timestamps change.

## Phase 1 limitations

- Synchronous, single-lead processing (designed so async can be added later).
- No new API routes here; the existing `POST /analyze` endpoint (which uses the
  earlier `processors.analysis_pipeline.AnalysisPipeline`) is unchanged and still
  works. Wiring `POST /leads/analyze` to this richer pipeline is a follow-up.
- No collectors/scraping, real-person enrichment, LLM, CRM, or email sending.
- Dedup is a simple deterministic key match, not a distributed system.
