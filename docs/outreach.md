# Outreach — Sales Pitch Generator

The `PitchGenerator` (`outreach/pitch_generator.py`) turns the analysis outputs
(signals, opportunity, POC role, score) into professional, evidence-based B2B
outreach messaging across multiple channels.

> **Phase 1 uses deterministic templates.** No LLM, no external APIs, and
> **automated sending is not implemented** — the generator only drafts messages.
> The module is independent of FastAPI, the database, the network, and LLMs; an
> LLM-based generator can be added later behind the same `generate(...)`
> interface. An earlier `generate_pitch` helper remains for backward
> compatibility.

## Channels (message types)

- **EMAIL** — `email_subject`, `opening_message`, `value_proposition`,
  `recommended_pitch` (assembled body), `call_to_action`
- **LINKEDIN** — `linkedin_message` (≤ ~500 chars)
- **CALL_TALKING_POINTS** — 3–5 bullets for a BD rep

The architecture allows additional channels later without changing the interface.

## Message strategies (per opportunity)

| Opportunity | Strategy | Focus |
| --- | --- | --- |
| NORMAL_HIRING | HIRING_SUPPORT | supplement internal hiring |
| PROJECT_DRIVEN_HIRING | PROJECT_RAMP_UP | rapid project capacity |
| LARGE_SCALE_RAMP_UP | SCALE_UP | scale teams quickly |
| STAFF_AUGMENTATION | STAFF_AUGMENTATION | flexible external capacity |
| VENDOR_OPPORTUNITY | VENDOR_ONBOARDING | partnership / vendor onboarding |
| TECHNOLOGY_IMPLEMENTATION | IMPLEMENTATION_DELIVERY | implementation & delivery |
| DIGITAL_TRANSFORMATION | TRANSFORMATION_DELIVERY | transformation engineering capacity |
| LOW_CONFIDENCE | NURTURE | conservative discovery, low-pressure |

Templates and rules live in `STRATEGY_TEMPLATES` / `TECH_SERVICE_MAP` /
`INDUSTRY_PHRASE`, separate from the generation logic.

## Service angles

Technologies map to service language (`TECH_SERVICE_MAP`), e.g. Java/Spring →
backend engineering, AWS/Kubernetes → cloud/platform engineering, Selenium/
Playwright → QA automation, Kafka/Data Engineering → data platform engineering.
Angles: STAFF_AUGMENTATION, PROJECT_SUPPORT, ENGINEERING_CAPACITY,
CLOUD_ENGINEERING, SOFTWARE_DEVELOPMENT, DEVOPS_SUPPORT, DATA_ENGINEERING,
QA_AUTOMATION, TECHNOLOGY_IMPLEMENTATION, VENDOR_SUPPORT.

## Industry personalization

Subtle wording for IT / BFSI / FMCG / Healthcare (`INDUSTRY_PHRASE`) — e.g. BFSI
emphasizes technology delivery and modernization programmes; Healthcare
emphasizes technology delivery and platform modernization — **without** any
regulatory, compliance, or security claims unless explicitly provided.

## Personalization inputs

`company_name`, `industry`, signal types, technologies, estimated hiring,
opportunity type, primary POC role (from POCFinder/POCEnricher, duck-typed), and
lead priority — used only when actually present.

## Confidence

`confidence` (0–100, label HIGH/MEDIUM/LOW) from signal strength, opportunity
confidence, scoring confidence, and availability of company / technology / POC
information. Deterministic.

## Safety / no fabrication

The generator **never invents** projects, project values, employee counts, tech
stacks, hiring numbers, decision-maker names, customers, partnerships, or
contract details. Hiring numbers appear only when supplied; technologies only
when detected. Forbidden phrasing ("we guarantee", "we know you need", "we
already work with", "your project requires", "you have a shortage") is avoided in
favour of consultative language ("We noticed…", "…may indicate…", "There may be
an opportunity…", "Would it be useful to discuss…"). LOW-confidence leads receive
a short, low-pressure discovery message rather than a hard pitch.

## Length control

Email body ~100–180 words; LinkedIn ≤ ~500 chars; 3–5 talking points; short,
specific subject.

## Phase 1 limitations

- Deterministic templates only — expressive but less varied than an LLM.
- **No sending** (email/LinkedIn), no CRM integration, no real-person discovery.
- Wired into the analysis pipeline: the pitch is stored in `Lead.recommended_pitch`
  and returned by `POST /analyze`.
