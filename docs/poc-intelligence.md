# POC / Decision-Maker Intelligence

The `POCFinder` (`enrichment/poc_finder.py`) recommends the decision-maker **role
types** most likely to own or influence a company's technology / vendor /
staffing decision, given the detected signals, the opportunity analysis, and the
lead's industry.

> **Phase 1 recommends roles only.** It does **not** discover real people, scrape
> LinkedIn or any site, collect private/sensitive personal data, call external
> APIs, or use an LLM. Real-person discovery will be added later using permitted
> public/business data sources.

The engine is deterministic, explainable, and independent of FastAPI, the
database, the network, and LLMs. All mappings live in configurable tables
(`POCFinderConfig`).

> An earlier `POCEnricher` (persona targeting + ranking of caller-supplied
> contacts) also lives in the module; this document describes `POCFinder`.

## Role categories

`TECHNOLOGY_LEADERSHIP`, `ENGINEERING_LEADERSHIP`, `DELIVERY_LEADERSHIP`,
`PROGRAM_LEADERSHIP`, `PROCUREMENT`, `VENDOR_MANAGEMENT`, `IT_SOURCING`,
`BUSINESS_LEADERSHIP`, `HR_TALENT`.

Each role in `ROLE_CATALOG` carries a category, a **decision-maker type**
(`TECHNICAL` / `BUSINESS` / `DELIVERY` / `PROCUREMENT` / `VENDOR` / `HR`), and a
base authority weight.

## Signal → role mappings

Ordered preferred/secondary roles per signal (`SIGNAL_ROLE_MAP`), e.g.:

| Signal | Preferred (top) | Secondary |
| --- | --- | --- |
| HIRING | VP Engineering, Head of Engineering, Engineering Director, CTO | Talent Acquisition Head, HR Director |
| PROJECT_AWARD | CTO, CIO, Program Director, Delivery Head | Procurement Head, Vendor Manager |
| PROJECT_EXECUTION | Delivery Head, Program Director, Engineering Director | CTO, Vendor Manager |
| DIGITAL_TRANSFORMATION | CIO, CTO, Chief Digital Officer, Head of Technology | Program Director, Delivery Head |
| TECHNOLOGY_INITIATIVE | CTO, CIO, VP Engineering, Head of Technology | Engineering Director, Program Director |
| VENDOR_REQUIREMENT | Vendor Manager, IT Sourcing Manager, Procurement Head | CTO, CIO, Delivery Head |
| CONTRACT | Procurement Head, Vendor Manager, IT Sourcing Manager | CTO, CIO, Delivery Head |

**Large technology hiring** (HIRING with volume ≥ threshold) adds a further
driver toward VP Engineering / CTO / Head of Engineering / Engineering Director.

## Industry rules

`INDUSTRY_ROLE_MAP` (IT, BFSI, FMCG, Healthcare) nudges recommendations — e.g.
BFSI → CIO, CTO, Technology Delivery Head, IT Procurement Head, Program Director.
Industry strings are normalized (bank/insurance → BFSI, etc.).

## Opportunity → role mappings

`OPPORTUNITY_ROLE_MAP` maps each opportunity type to primary/secondary roles —
the strongest driver — e.g. `VENDOR_OPPORTUNITY` → Vendor Manager / IT Sourcing
Manager / Procurement Head; `STAFF_AUGMENTATION` → VP Engineering / Head of
Engineering / Engineering Director; `LARGE_SCALE_RAMP_UP` → VP Engineering / CTO
/ Delivery Head.

## Relevance scoring

Each candidate role scores `0–100 = role authority (0–30) + evidence alignment
(0–70, capped)`. Evidence alignment is a **position-weighted** sum: opportunity
primary/secondary, each present signal's preferred/secondary, large-hiring, and
industry lists — earlier positions score higher, so the spec's ordering is
preserved. Roles are de-duplicated and sorted by relevance descending
(authority, then name, break ties) — fully deterministic. The top role is
`primary_role`; the rest are `secondary_roles`.

Each recommendation returns `role`, `role_category`, `decision_maker_type`,
`relevance_score`, and a grounded `reason`.

## Recommendation confidence

`recommendation_confidence` (0–100, label HIGH/MEDIUM/LOW) from: signal strength
(+30/+15), a non-low-confidence opportunity (+25), explicit vendor language
(+15), hiring evidence (+15), project evidence (+15), known industry (+10).

## No recommendation

If there is no usable signal/opportunity evidence, `primary_role` is `null`,
`secondary_roles` is empty, and confidence is `LOW` — nothing is guessed. A
general non-technical vacancy (e.g. office administrator) yields no strong POC.

## Limitations

- **Roles, not people** — no names, emails, or profiles are produced or fetched.
- Recommendations reflect configured mappings and the supplied evidence only;
  they do not infer facts about a specific company.
- Mappings and weights are tunable via `POCFinderConfig` for different services,
  industries, or staffing models.
- Not yet wired into the analysis pipeline (which currently uses `POCEnricher`);
  integration can follow in a later step.
