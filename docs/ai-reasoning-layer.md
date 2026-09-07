# AI Reasoning Layer

This layer adds an **AI reasoning and prioritization** pass over data the
deterministic systems have **already collected, normalized, resolved, verified,
and scored**. It never introduces new facts.

> **The AI layer improves reasoning and prioritization; it is never a source of
> facts.**

It cannot invent companies, people, jobs, numbers, dates, values, technologies,
or intent. Every fact it presents must already exist in a real DB record with an
evidence id; anything else is labelled inference or unknown.

> **No AI provider is configured in this environment.** Status is
> `NOT_CONFIGURED` and **no live AI request has been executed**. All AI
> intelligence shown is the **deterministic grounded baseline** produced purely
> from real DB records. Do not read any of this as evidence that an LLM ran.

## Where it sits

The deterministic pipeline stays authoritative for **source data, normalization,
entity resolution, deduplication, evidence verification, signal classification,
lead score, opportunity type, and contact verification**. The AI layer is a
consumer of that output, not a replacement for any of it:

```
REAL DB RECORDS (scoring, canonical jobs, technologies, signals, tenders,
                 evidence w/ evidence_ids, decision-makers, conflicts, provenance)
  → ai/context.py     build minimized, sanitized LeadIntelligenceContext (context_hash)
  → ai/service.py     orchestrate:
        LLM path       (ai/provider.py + ai/prompts.py)  — only if configured,
                        connected, and the lead is eligible
        else           deterministic baseline (ai/deterministic.py)  ← ALWAYS available
  → ai/validator.py   ground every AI FACT claim against the real context
  → persist           versioned AIIntelligenceResult + AIAnalysisAudit
```

AI output is **data / recommendation only**. It cannot execute code, run a
shell, access credentials, make HTTP requests, modify the schema, or send
communications. High-impact actions are human-decided.

## Two paths, one output shape

### Deterministic baseline — always on (`ai/deterministic.py`)

The baseline **always works with no provider**. From real DB records alone it
produces the same structured output the LLM path would, so the product degrades
honestly rather than fabricating:

- `executive_summary`
- `verified_facts` (each with `evidence_ids`)
- `inferred_insights` (explicitly labelled as inference, using hedged language)
- `unknowns`
- `opportunity_explanation`
- `urgency_reason`
- `business_problem_hypothesis`
- `recommended_action`
- `next_best_action`
- `sales_angle`
- `risk_flags`
- AI reasoning confidence

Its output is stamped `model_name="deterministic-1.0"`, `ai_generated=false`.
This is the honest path when no LLM is configured — **AI unavailable →
deterministic intelligence with a clear indication, never fabricated content**.

### LLM path (`ai/provider.py`, `ai/prompts.py`)

When a provider is configured, connected, and the lead is eligible, the same
context is sent to the model, which returns strict JSON validated against the
Pydantic schema. Malformed output is rejected. The LLM only reasons over the
supplied context; it is not permitted to add facts.

## Input context (`ai/context.py`)

The `LeadIntelligenceContext` / company context is assembled **only from real
records**: scoring, canonical jobs, technologies, company signals, tenders,
evidence (with `evidence_ids`), decision-makers, conflicts, and provenance.

- **Sanitized** — HTML/scripts stripped, lengths capped.
- **Minimized** — no secrets, no raw source payloads, no unnecessary personal
  data.
- **Cacheable** — a `context_hash` fingerprints the assembled context.

## Fact vs inference vs unknown (`ai/schema.py`)

Every claim is an `AIClaim` carrying:

| Field | Values |
| --- | --- |
| `claim_type` | `FACT` / `INFERENCE` / `UNKNOWN` |
| `support_level` | `DIRECT` / `SUPPORTED_INFERENCE` / `UNSUPPORTED` / `CONTRADICTED` |
| `evidence_ids` | the real evidence backing the claim |

Inference and unknown are **never** presented as fact. A fact must trace to real
evidence; a plausible-but-ungrounded statement is an inference, and a gap is an
explicit unknown.

## Evidence citations

Verified facts cite the `evidence_ids` of the real records that support them, so
every fact shown in the UI is traceable back to source-backed evidence. Generated
AI text is never itself treated as evidence.

## Provider configuration & truthful status (`ai/provider.py`)

The provider layer is `BaseAIProvider` + `OpenAICompatibleProvider`, which works
with any OpenAI-compatible `/chat/completions` endpoint. It is configured **only**
from the environment — **no credentials in code**:

| Variable | Purpose |
| --- | --- |
| `AI_PROVIDER` | Provider selector |
| `AI_MODEL` | Model name |
| `AI_API_KEY` | API key (env only; never logged or committed) |
| `AI_API_BASE_URL` | OpenAI-compatible base URL (e.g. `https://api.openai.com/v1`) |
| `AI_TIMEOUT_SECONDS` | Request timeout |
| `AI_MAX_OUTPUT_TOKENS` | Output token cap |
| `AI_TEMPERATURE` | Sampling temperature |
| `AI_ENABLED` | Master on/off switch |

Status is **truthful**:

| Status | Meaning |
| --- | --- |
| `NOT_CONFIGURED` | No provider/credentials set. **Current state in this environment.** |
| `CONFIGURED` | Credentials present but not yet verified live. |
| `CONNECTED` | A **real model request** (probe) actually succeeded. |
| `AUTHENTICATION_FAILED` | Credentials rejected by the provider. |
| `RATE_LIMITED` | Provider rate limit hit. |
| `ERROR` | Provider/transport error. |
| `DISABLED` | Turned off via `AI_ENABLED`. |

`CONNECTED` is set **only after a real model request succeeds** — never inferred
from the mere presence of credentials.

## Prompt-injection defense (`ai/prompts.py`)

System rules are authoritative. All source/context text is passed inside a
**delimited UNTRUSTED block** the model is explicitly told to treat as **data,
not instructions**. Anything inside that block claiming to change the rules is
ignored. `prompt_version` is tracked so outputs are attributable to a prompt.

## Hallucination validation & claim grounding (`ai/validator.py`)

After the model responds, the validator compares each AI `FACT` claim's numbers
and named people against the **real context**. Anything not grounded is marked
`UNSUPPORTED_CLAIM`, and the offending `FACT` is **downgraded to inference** so
the UI can never render an ungrounded statement as a fact. This is the safety net
that keeps the "never a source of facts" guarantee true even when the model
strays.

## Orchestration, caching & versioning (`ai/service.py`)

1. Build the context.
2. Run the **LLM if configured + connected + eligible**, else the **deterministic
   baseline**.
3. Validate the output.
4. Persist a **versioned** `AIIntelligenceResult` recording
   `context_hash` / `output_hash` / `prompt_version` / model.

**Caching.** When `context_hash` + `prompt_version` are unchanged, the cached
result is returned — the provider is **not** called on every request.

**No fabrication on failure.** If the provider fails, the service falls back to
the deterministic baseline with status `UNAVAILABLE`; it never fabricates.

**Audit.** Every attempt writes an `AIAnalysisAudit` record (no sensitive data).

**Separate confidence axis.** AI reasoning confidence is a **distinct** axis from
`lead_score`, `evidence_confidence`, and `contact_confidence` — never collapsed
into any of them.

## Cost control

The LLM runs only for **HOT / WARM** leads (or an explicit force). Everything
else receives the deterministic baseline. Combined with `context_hash` caching,
this keeps provider calls bounded rather than per-request.

## Human review — no autonomous actions

The AI output is a recommendation, not an action. It **cannot** execute code, run
a shell, read credentials, make HTTP requests, alter the schema, or send any
communication. All high-impact actions remain human-decided.

## APIs (`api/routes/ai.py`)

No secrets are ever exposed through these endpoints. `GET` returns the cached
result (the deterministic baseline on the first call); `POST` forces a fresh
analysis.

| Method & path | Purpose |
| --- | --- |
| `GET /ai/status` | Truthful provider status (currently `NOT_CONFIGURED`). |
| `GET /leads/{id}/ai-intelligence` | Cached AI intelligence for a lead (deterministic baseline on first call). |
| `POST /leads/{id}/ai-analyze` | Force a fresh analysis for a lead. |
| `GET /companies/{id}/ai-intelligence` | Cached AI intelligence for a company. |
| `POST /companies/{id}/ai-analyze` | Force a fresh analysis for a company. |

## Testing (opt-in live)

- The default `pytest` suite makes **no external AI calls** — the deterministic
  baseline and validation logic are exercised without any provider.
- Optional live tests are opt-in via `RUN_LIVE_AI_TESTS=true`; they validate only
  **schema + safety**, not exact wording.

## Limitations

- **No provider is configured here**, so the LLM path has never executed; every
  result you see is the deterministic grounded baseline.
- The AI adds reasoning and prioritization only — it does not improve, correct,
  or extend the underlying real data.
- Inferences are hypotheses, clearly labelled as such; unknowns stay unknown.
- The deterministic systems remain the authority for all source data,
  normalization, resolution, dedup, evidence, signals, lead score, opportunity
  type, and contact verification.

> **The AI layer improves reasoning and prioritization; it is never a source of
> facts.**
