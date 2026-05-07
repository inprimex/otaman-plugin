# Gate 0 — Intake & Information Verification

## Purpose

Before any scoring or estimation happens, answer one question: **does the available information actually support an estimate?** This gate exists because detailed estimation on insufficient information produces estimates that are precise-looking but wrong — which is worse than admitting you don't know. The failure mode this gate prevents is building a 20-page proposal on a foundation that falls apart when the client asks the first hard question.

## Trigger

User provides any of: project brief, client email, RFP, call notes, technical requirements, meeting transcript, forwarded slack thread, or anything else that communicates project intent.

## Task

Identify the project's domain(s), assess information completeness across six categories, and produce a verification summary. **Do not start complexity scoring or estimation yet.**

## Step A — Domain identification (do this first)

Before scoring categories, identify which domain(s) the project belongs to. Domains the skill has reference material for:

- **healthcare** — patient apps, clinician tools, EHR integrations, telehealth, medical devices
- **fintech** — payments, banking, lending, investments, KYC/AML, insurance, crypto
- **ecommerce** — storefronts, marketplaces, OMS, fulfillment, subscription commerce
- **ml-ai** — LLM applications, RAG systems, agents, custom ML platforms, AI features
- **gaming** — games (any platform), gamified products, game backends, live ops
- **drones-uav** — UAV systems, ground control, fleet management, counter-UAS, mission planning
- **embedded-iot** — connected devices, sensor networks, smart home, industrial IoT, firmware

Read `references/domains/<domain>.md` for any domain that applies. **Multi-domain projects are common** — a healthcare AI feature loads both `healthcare.md` and `ml-ai.md`; a connected medical device loads `healthcare.md` and `embedded-iot.md`. Loading more than one is fine; the gates synthesize across them.

If no domain matches, proceed in **generic mode**: skip Step A, use the standard six categories with general-software defaults, and flag to the user that domain-specific calibration isn't being applied. Generic mode estimates are still valid; they just lose the domain-specific risk additions, integration benchmarks, and anchor projects.

Each loaded domain reference will provide:
- Domain-specific compliance frameworks
- Integration effort benchmarks
- Common feature taxonomy
- Domain-specific risk register additions
- Anchor projects for scale calibration
- Domain-specific Gate 0 checks (these augment Step B's six categories)

## Step B — Information completeness assessment

Assess information completeness across six categories. The first five are universal; the sixth pulls from the loaded domain reference(s).

## Handling different input types

- **PDFs and written documents** — Extract and catalog requirements systematically. Distinguish requirements from context. Note conflicts between sections.
- **Emails and call transcripts** — Identify speaker roles. Distinguish stated requirements from conversational commentary (the client saying "it would be nice if..." is not the same as "we need...").
- **RFPs** — Map RFP sections to the six categories below. RFPs often over-specify some categories (compliance) and under-specify others (team, budget).
- **Multiple files** — Cross-reference for contradictions. When the brief says one thing and the call notes say another, flag it — don't silently pick one.

## The six categories

### 1. Business context & objectives

What you're looking for: the core problem being solved, who uses the product, what success looks like in measurable terms, why now, what revenue model or business outcome the product supports.

Red flags: objectives stated as feature lists rather than outcomes. "Build a patient portal" is not an objective; "reduce no-show rate by 15%" is.

### 2. Technical environment & constraints

What you're looking for: existing infrastructure, integration points (with system names, versions, API availability, auth methods, data formats), stated tech preferences, deployment requirements (geography, availability, DR expectations), performance requirements with specific numbers.

Red flags: "integrates with their EHR" with no system name; "scalable" with no numbers; "cloud-based" without specifying which cloud and whether they already have accounts.

### 3. Compliance & regulatory requirements

What you're looking for: applicable frameworks (HIPAA, PCI-DSS, GDPR, SOC 2, FDA, 21 CFR Part 11, state privacy laws), existing certifications on client side, data residency requirements, audit requirements, retention and disposal policies.

Red flags: healthcare project with no HIPAA mention; international user base with no GDPR consideration; "we need to be secure" without specifying to what standard.

### 4. Team & resource context

What you're looking for: client team composition, decision-making authority (who signs, who approves scope, who does UAT), stakeholder availability for reviews, existing workload, any constraints on staffing (must be onshore, can't use contractors, etc.).

Red flags: single point of contact with no clarity on whether they can actually sign; no named product owner; implied team members whose availability hasn't been confirmed.

### 5. Budget & timeline context

What you're looking for: budget range stated explicitly (not just "reasonable"), timeline expectations with a business reason (a trade show, a funding milestone, a regulatory deadline), funding availability, decision criteria, opportunity cost.

Red flags: timeline set by aspiration ("we'd like it by summer") not business need; budget stated as "we'll see"; hard deadline without explanation.

### 6. Domain-specific requirements

What matters varies by domain. Apply the **Domain-specific Gate 0 checks** section from the domain reference(s) loaded in Step A. These checks enumerate the 5–12 things that must be verified for projects in this domain.

For multi-domain projects, apply checks from each loaded domain. Some checks are independent (a connected medical device needs both the device-class question from embedded-iot and the FDA pathway question from healthcare); others may overlap (don't ask twice).

If no domain reference applied (generic mode), identify the 3–5 most critical project-specific variables and verify each.

## Confidence scoring

Score each category 0–5:

- **0** — No information. Complete clarification required before proceeding.
- **1** — Minimal information. Major gaps significantly impair estimation.
- **2** — Some information. Significant uncertainty in critical areas.
- **3** — Moderate information. Enough for a directional estimate, but notable gaps remain.
- **4** — Good information. Minor gaps can be addressed with reasonable assumptions.
- **5** — Comprehensive information. High confidence, detailed estimation possible.

### Weighted confidence

Calculate overall weighted confidence as a percentage. The weights depend on the project type — don't use flat weights.

- **Compliance-heavy domains** (healthcare with PHI, fintech with money movement, embedded-iot in regulated sectors): Compliance + Technical Environment categories = 40% combined weight
- **Integration-heavy projects** (healthcare with EHR, fintech with banking, e-commerce with OMS): Technical Environment weighted heavily
- **Internal tools / automation**: Business Context + Team Resources weighted higher; compliance typically lower
- **Greenfield product**: Business Context and Technical Environment weighted higher (the product shape isn't known yet)
- **Migration / modernization**: Technical Environment weighted heavily (the existing system's shape determines most of the work)
- **AI/ML projects**: Business Context (for cost modeling and use case clarity) + Technical Environment (for inference architecture) weighted higher; uncertainty dimension typically scores high
- **Hardware-software (embedded, drones, IoT)**: Technical Environment weighted heavily; manufacturing/certification considerations often missed in initial brief

Always document the weighting rationale in the output — the user should see why you weighted the way you did, not just the weighted number.

## Gate 0 output format

Present the following to the user:

**Title:** Information Verification Summary — [Project Name]

**Domain(s) identified:** [List of domains loaded, or "Generic mode — no specific domain reference applied"]

**Category scores table** with columns:
- Category
- Score (0–5)
- Key findings (what you have)
- Critical gaps (what's missing)

**Overall weighted confidence:** XX%

**Weighting rationale:** Explain why categories were weighted as they were, based on project type.

**Immediate assessment** (pick one):
- "Sufficient to proceed" — proceed to next gate
- "Gaps exist but manageable with documented assumptions" — proceed with assumption register
- "Critical gaps — clarification needed before estimation" — pause, ask client
- "Insufficient — recommend discovery phase" — don't estimate yet

**Priority clarification questions** (if any), grouped:
- **Blocking** — must answer before estimation. For each: context, options, impact if unknown.
- **High-value** — significantly improves accuracy. Same format.
- **Nice-to-have** — can proceed with assumption. Same format.

**Recommended next step:** one of: proceed to Gate 1 / send clarification questions to client first / recommend discovery phase / refuse detailed estimation and offer t-shirt size only.

## Wait for user response

The user may:
- **Provide answers** to clarification questions → re-score affected categories, update the summary
- **Approve proceeding** with documented assumptions → move to Gate 1 (or skip to Gate 2 on Fast Track)
- **Provide additional context** → re-assess
- **Send questions to client first** → pause the flow, resume when answers arrive
- **Override your recommendation** → acknowledge, comply, record the override

## Assumption register

When proceeding despite gaps, every assumption goes into a register:

| ID | Assumption | Confidence | Impact if wrong | Verification method |
|----|------------|------------|-----------------|---------------------|
| A01 | EHR integration is via Epic FHIR API | Med (60%) | +200h if HL7 v2 required | Confirm in kickoff meeting |
| A02 | Mobile app is iOS/Android native | Low (40%) | ±40% effort if React Native is required | Confirm in first sprint planning |

The register is a living artifact — it's delivered with the estimate and re-verified at kickoff.

## Stop conditions

Refuse detailed estimation and recommend discovery when any of these are true:

- Requirements confidence < 30% AND complexity indicators suggest > 10 points
- Critical integration points identified with zero API or data format information
- Compliance requirements mentioned but not detailed
- Client cannot articulate success metrics or acceptance criteria
- Timeline or budget constraints contradict the requirements scope by > 50%

When a stop condition triggers:
1. Explain which condition triggered and why, specifically
2. Describe the next steps that would resolve it (discovery phase, stakeholder interviews, PoC)
3. If the user insists on an estimate anyway, offer t-shirt sizing only, with heavy disclaimers about what's being assumed away

Don't invent confidence you don't have. A t-shirt size with transparent assumptions is more honest and more useful than a Tier D document built on wishes.
