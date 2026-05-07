# Gate 1 — Complexity & Confidence Scoring

## Purpose

Translate the information you have into a complexity score that drives tier selection. The failure mode this gate prevents is estimating complex work with a simple methodology (too optimistic) or simple work with a heavy methodology (wastes effort, looks padded). The output of this gate is a 0–25 score plus a band, reviewed and confirmed by the user before they commit to the estimation approach.

## Trigger

User approves proceeding from Gate 0 (not Fast Track).

On Fast Track (confidence > 70% AND complexity indicators ≤ 10), do this scoring inline during Gate 0's output rather than as a separate stop.

## Task

Score five dimensions, each 0–5. Total range 0–25. Present scores with rationale for user validation.

## The five dimensions

### Dimension 1 — Functional scope complexity

How many distinct user roles? How complex are the workflows? How many feature domains? How sophisticated are the business rules?

- **0** — Static website. Content presentation only.
- **1** — Simple CRUD. Basic forms and data display. Single user type.
- **2** — Standard business workflows. Single domain. Example: appointment booking system.
- **3** — Complex workflows with state machines. Multiple user types. Role-based functionality throughout.
- **4** — Multi-tenant. Complex business rules. Multiple feature domains integrated.
- **5** — Platform or marketplace. Multiple distinct stakeholder types with sophisticated functionality for each.

Assessment inputs: count distinct user roles, count workflow patterns, assess business rule density, count feature domains.

### Dimension 2 — Technical complexity

How novel is the technology? How sophisticated is the architecture? How much performance optimization is required?

- **0** — Static site. No-code tools only.
- **1** — Standard web/mobile on a well-known stack. No unusual requirements.
- **2** — Real-time features. Moderate integrations with well-documented services.
- **3** — AI/ML components. Complex data pipelines. Advanced client-side functionality (rich interactions, offline support, etc.).
- **4** — Novel technology choices. Distributed systems. High-performance optimization. Custom protocols.
- **5** — Cutting-edge research territory. Specialized algorithms. Pushing technology boundaries.

### Dimension 3 — Integration complexity

How many external systems? How well documented? How complex are the data transformations? Are test environments available?

- **0** — No external integrations beyond payment widget or analytics.
- **1** — 1–2 well-documented REST APIs from established providers (Stripe, Auth0, SendGrid).
- **2** — 3–5 standard integrations: payments, auth, email, storage, analytics.
- **3** — 5–10 integrations, some legacy systems or moderately complex enterprise.
- **4** — 10–15 integrations with data transformation requirements, complex enterprise systems, middleware.
- **5** — 15+ integrations including EHR/ERP, HL7/FHIR/EDI standards.

Additional factors that raise the score within a band: poor documentation, no test environment, real-time synchronization requirements, complex data transformations, vendor-specific quirks.

### Dimension 4 — Compliance & regulatory

- **0** — No regulatory requirements beyond basic GDPR.
- **1** — Basic GDPR only: privacy policy, consent, data portability.
- **2** — Industry standards: SOC 2, ISO 27001, moderate enterprise security.
- **3** — Single major framework: HIPAA OR PCI-DSS.
- **4** — Multiple frameworks simultaneously: HIPAA + state privacy laws, or PCI-DSS Level 1 scope.
- **5** — Healthcare + financial + international, or FDA clearance / 21 CFR Part 11 territory.

Note: compliance effort scales non-linearly. A single framework might add 10–25% to the project; multiple frameworks can add 40%+ because the intersections create edge cases that aren't covered by either framework alone.

### Dimension 5 — Requirements uncertainty

**This dimension is inverted from the others.** Low confidence = high score (more complexity, because unknowns need to be estimated conservatively or discovered).

Convert the weighted confidence from Gate 0:

- Confidence > 85% → Score **0** (minimal uncertainty)
- Confidence 70–85% → Score **1** (low uncertainty)
- Confidence 50–70% → Score **2** (moderate uncertainty)
- Confidence 30–50% → Score **3** (high uncertainty)
- Confidence 15–30% → Score **4** (very high uncertainty)
- Confidence < 15% → Score **5** (extreme uncertainty)

## Complexity bands

- **0–5** — Very Low
- **6–10** — Low
- **11–15** — Medium
- **16–20** — High
- **21–25** — Very High

## Gate 1 output format

Present:

**Title:** Complexity Assessment — [Project Name]

**Dimension scores table** with columns:
- Dimension
- Score (0–5)
- Key rationale (1–2 sentence justification)

**Final row:** TOTAL | XX/25

**Complexity band:** [Band name, from above]

**What this means:** 1–2 sentences on what drives the score and what it implies for estimation approach. Example: "The Medium band is driven primarily by compliance (HIPAA) and integration complexity (Epic FHIR plus a legacy scheduling system). Functional scope is modest; the cost and risk live in the interfaces."

**Scores I'm least confident about:** Flag any dimensions where the score could reasonably be ±1, and explain why. This signals honest calibration and invites the user to correct if they have context you don't.

Close with: "Do you agree with these scores, or would you adjust any dimension?"

## Wait for user response

The user may:
- **Agree** → proceed to Gate 2
- **Adjust specific scores** with rationale → accept, recalculate total and band
- **Provide new information** that changes the picture → re-assess affected dimensions
- **Challenge a score** → explain your reasoning, then accept the user's decision

Never argue for more than one round. The user is the decision authority; if they disagree after one explanation, accept and move on.

## Backtrack rule

If new information from the user during Gate 1 materially changes Gate 0 category scores — any category moves by ±2 or more, OR the overall weighted confidence shifts by ±15% — explicitly re-score Gate 0 and reassess whether the tier selection in Gate 2 will change.

Don't silently carry forward stale Gate 0 assumptions. If the picture changes, the paper trail should show where.
