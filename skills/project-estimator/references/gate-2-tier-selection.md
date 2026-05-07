# Gate 2 — Tier & Method Selection

## Purpose

Map the complexity and confidence scores to an appropriate estimation tier and methodology. The failure mode this gate prevents is applying a methodology whose precision claim exceeds what the inputs can support — for example, delivering a Tier E bottom-up estimate claiming ±15% accuracy on inputs that only support ±40% accuracy. That's not precision; it's false confidence.

## Trigger

User approves complexity scores from Gate 1. On Fast Track, triggered directly from Gate 0 with inline complexity assessment.

## Task

Select a tier (A–E) and an estimation method. Detect constraint type (budget-bound, timeline-bound, open). Present for user confirmation before executing in Gate 3.

## Tier selection matrix

Read as: complexity band (row) × confidence range (column) → tier.

| Complexity | <30% | 30–50% | 50–70% | 70–85% | >85% |
|------------|------|--------|--------|--------|------|
| Very Low (0–5) | A | A | B | B | B |
| Low (6–10) | A | B | C | C | D |
| Medium (11–15) | Discovery → A | C | C | D | E |
| High (16–20) | Discovery mandatory | Discovery → C | D | D | E |
| Very High (21–25) | Discovery mandatory | Discovery mandatory | Discovery → D | D + PoC | E |

"Discovery → X" means: recommend a paid discovery phase first, then produce a Tier X estimate with the discovery outputs. Don't skip to Tier X on insufficient information.

"Discovery mandatory" means: refuse detailed estimation. Recommend discovery. If the client insists, offer t-shirt sizing only with disclaimers.

## Tier quick reference

Full templates live in `tier-templates.md`. Summaries:

| Tier | Name | Pages | Accuracy | Analysis effort | Best for |
|------|------|-------|----------|-----------------|----------|
| **A** | Quick Assessment | 3–5 | ±50% | 2–4 hours | Early stage, ballpark needed, requirements unclear |
| **B** | Simple Estimation | 5–8 | ±30–40% | 4–8 hours | Small well-understood projects, standard tech |
| **C** | Standard Estimation | 10–15 | ±25–30% | 1–2 days | Medium projects, moderate complexity, some unknowns |
| **D** | Detailed Estimation | 15–25 | ±20–25% | 2–4 days | Complex projects, good requirements, meaningful risk |
| **E** | Comprehensive | 25–50 | ±10–15% | 5–10 days | Large enterprise, high confidence, investment justifies rigor |

The effort numbers are your effort producing the document, not the project effort. Don't burn 5 days on a $50K project's estimate — the analysis effort should be roughly 2–5% of project effort.

## Estimation methods

Pick the method that best matches the inputs and the tier:

### T-Shirt Sizing
Best when confidence < 30% and immediate response needed. Accuracy ±50%. Output is a size label (S/M/L) with dollar and timeline ranges. Used mostly in Tier A and as a fallback.

### Analogous / Comparative
Best when complexity 0–10 and similar past projects exist. Accuracy ±30–40%. Method: identify 2–3 comparable prior projects, document adjustment factors (+/- percentages for scope differences, tech novelty, team experience, compliance). Used in Tier B primarily.

### Parametric
Best when complexity 6–15 and requirements decompose into countable units (stories, endpoints, entities, screens). Accuracy ±25–30%. Method: classify units by complexity (Low/Med/High), apply effort benchmarks per class, sum, add project-level adjustments. Used in Tier C primarily.

Effort benchmarks for parametric (adjust based on your company's actual productivity if different):
- Low complexity unit: 8–16 hours
- Medium complexity unit: 16–40 hours
- High complexity unit: 40–80 hours

### Capacity-Based
Best when budget or timeline is fixed and requirements are flexible. Accuracy matches the tier used. Method: budget ÷ blended rate (read from company-context.md) → total hours; apply productivity coefficient; allocate across work categories; map features to the capacity envelope; create scope options (90% MVP, full, phased). Used heavily when clients come in with "we have $X".

### Three-Point PERT
Best when complexity 11–20 and you need uncertainty quantification. Accuracy ±20–25%. Method: for each component, estimate Optimistic (P20), Most Likely (P50), Pessimistic (P80).
- Expected = (O + 4M + P) / 6
- StdDev = (P − O) / 6
- 68% CI = Expected ± 1σ
- 95% CI = Expected ± 2σ

Used in Tier D primarily.

### Bottom-Up
Best when complexity > 15 and confidence > 70%. Accuracy ±10–15%. Method: decompose work to tasks of 8–40 hours each, build resource-loaded schedule, identify critical path, compute earned value projections, apply risk-based contingency at component level. Used in Tier E.

### Story Points + Velocity
Best when in an agile context with real historical velocity data from the same team. Accuracy ±20–30%. Rarely applicable in pre-sales because velocity data doesn't exist yet for a new engagement. Occasionally useful when extending an existing engagement.

## Constraint detection

Detect from how the client framed the request. The constraint type changes the deliverable structure:

**Budget-constrained** — Signal phrases: "what can we get for $X?", "we have a budget of Y", "we're looking for a solution under Z".
- Approach: capacity-based
- Output: scope options fitting the budget envelope
- Typical options: Essential MVP at 90% budget / Enhanced MVP at full budget / Phased approach with 60–70% of budget in Phase 1

**Timeline-constrained** — Signal phrases: "can you deliver by [date]?", "we need this by Q3", "launch is in 10 weeks".
- Approach: backcast from deadline
- Output: feasibility verdict (realistic / aggressive / unrealistic) + team scaling scenarios
- Typical scenarios: Standard team / Accelerated (+30–50% people, +15–25% scope cost, +20–30% total cost) / Maximum (2× people, +30–40% scope cost, +50–75% total cost)

**Open (no constraints)** — Signal phrases: "what do you recommend?", "give us your thoughts", "how would you approach this?"
- Approach: scenario-based
- Output: three scenarios — Optimal Quality / Faster Delivery (−25–35% time, +15–25% cost) / Budget-Conscious (+25–35% time, −15–25% cost) — with explicit recommendation

## Gate 2 output format

Present:

**Title:** Tier & Method Recommendation — [Project Name]

**Based on scores:** Complexity XX/25 ([Band]), Confidence XX%, Matrix result: **Tier [X] — [Name]**

**Recommended estimation method:** [Method name]

**Rationale:** 2–3 sentences on why this method fits the project shape.

**Constraint handling:** [Budget-constrained / Timeline-constrained / Open scenarios / None detected]
If a constraint is detected, brief explanation of how the approach accommodates it.

**What this means in practice:**
- Output: approximately X–Y pages
- Accuracy claim: ±X%
- Analysis effort required: X hours/days
- Any special considerations (e.g., PoC needed, discovery recommended first)

**Alternative considered:** If another tier or method was close, briefly name it and explain why you didn't pick it. This helps the user understand the decision and spot any reason to override.

Close with: "Shall I proceed with Tier [X] using [Method], or would you prefer a different approach?"

## Wait for user response

The user may:
- **Approve** → proceed to Gate 3
- **Request a different tier** ("client needs a quick answer, use Tier A") → acknowledge the accuracy trade-off and proceed
- **Request a different method** → adapt and confirm
- **Ask for an explanation** of what each tier produces → explain, then re-ask
- **Decide not to proceed** (project doesn't warrant the estimation effort) → stop cleanly

## Human override rule

If the user explicitly requests a specific tier or asks to skip gates:
1. Acknowledge the trade-off: reduced accuracy, undocumented assumptions, limited risk quantification
2. Comply
3. In the final Gate 3 output, document what was skipped and why. The deliverable should be honest about its bounds even when those bounds were chosen for speed.
