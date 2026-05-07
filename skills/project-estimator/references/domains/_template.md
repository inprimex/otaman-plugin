# [Domain Name] — Estimation Reference

**This file is loaded by the estimator skill when a brief is identified as belonging to the [Domain Name] domain.** It provides domain-specific context that augments the universal estimation methodology — compliance frameworks, integration patterns, feature taxonomy, common risks, and anchor projects.

The format below is the standard structure every domain file follows. Copy and fill in to add your own domain.

---

## What's distinctive about this domain

[2–3 sentences on what makes estimation in this domain different from generic SaaS. What's the hard part? What do clients consistently underestimate? What's the most common failure mode in pre-sales for this domain?]

---

## Compliance frameworks that may apply

| Framework | When it applies | Effort impact |
|---|---|---|
| [Framework A] | [trigger conditions] | [+X% of base effort, or specific dollar adders] |
| [Framework B] | [trigger conditions] | [impact] |

[Brief notes on intersections — e.g., "If both A and B apply simultaneously, expect non-linear cost increase because edge cases multiply"]

---

## Common integrations and effort patterns

| Integration class | Typical providers | Effort range | Notes |
|---|---|---|---|
| [Class 1 — e.g., Payment processing] | [Stripe, Adyen, Square] | [15–40h per integration] | [What drives the upper end] |
| [Class 2] | [providers] | [range] | [notes] |

---

## Feature taxonomy (typical modules)

When estimating projects in this domain, the features sheet's "Module" column typically contains some subset of:

- **[Module 1]** — [what's in it, who uses it]
- **[Module 2]** — [what's in it, who uses it]
- **[Module 3]** — [what's in it, who uses it]
- (etc.)

---

## Recommended features sheet schema

For projects in this domain, the hour columns in the features sheet should be:

- [Column 1 — e.g., "Backend (hours)"]
- [Column 2 — e.g., "Frontend (hours)"]
- [Column 3 — e.g., "Mobile (hours) — only if mobile is in scope"]
- [Column 4 — e.g., "ML/Inference (hours)"]
- **Total (hours)** — sum of the above

[Brief explanation of why these columns: e.g., "We split ML/Inference because that work uses different staffing and benchmarks differently from CRUD work"]

---

## Domain-specific risk register additions

In addition to the standard risk register entries (R06 AI-assisted development if applicable, generic technical risks), include these domain-specific entries when relevant:

### Risk: [Risk title]

- **Category**: [Regulatory / Technical / Operational / Compliance / Commercial]
- **Probability / Impact**: [typical assessment]
- **Description**: [what the risk is, in client-readable language]
- **Mitigation**: [specific controls]
- **Contingency**: [fallback if risk materializes]

### Risk: [Risk title 2]

[Same structure]

---

## AI-assisted productivity profile (overrides for this domain)

The general productivity profile in `company-context.md` applies, but this domain has specific exceptions:

- **[Work type 1]**: [adjusted speedup vs. generic — e.g., "Lower than generic due to domain-specific patterns AI hasn't been trained heavily on"]
- **[Work type 2]**: [adjusted speedup]

If no overrides apply, delete this section.

---

## Anchor projects (typical scale calibration)

Use these anchor sketches when estimating new projects in this domain. They're not full examples — for the canonical deliverable format, see `examples/healthcare-mvp.md`. These anchors give you ballpark expectations.

### Anchor: [Project type 1 — e.g., "MVP for [domain] startup, 3-month delivery"]

- **Scope**: [1-line description]
- **Total feature hours**: [X–Y]h
- **Total cost** (at typical mid-market consultancy rates of ~$70/h blended): [$X–Y]K
- **Timeline**: [X months]
- **Notable cost drivers**: [what makes this domain's MVP cost what it does]

### Anchor: [Project type 2 — e.g., "Enterprise integration for [domain], 6-month delivery"]

[Same structure]

---

## Common pitfalls in pre-sales for this domain

- [Pitfall 1 — e.g., "Clients confuse [domain term A] with [domain term B], leading to scope misalignment if not clarified in Gate 0"]
- [Pitfall 2]
- [Pitfall 3]

---

## Domain-specific Gate 0 checks

When this domain is identified, add these specific checks to Gate 0's category 6 (domain-specific requirements):

- [ ] [Specific check 1 — e.g., "Confirm regulatory framework: [list]"]
- [ ] [Specific check 2]
- [ ] [Specific check 3]
