# Company Context — Template

**This file is the template. Copy it to `company-context.md` (same directory) and fill in the bracketed placeholders with your own company's information.** The skill reads `company-context.md`, not this template. If `company-context.md` doesn't exist, the skill works with generic assumptions but loses the calibration that makes estimates defensible.

Delete any sections that don't apply to your company and add sections that matter for your context.

---

## Organization

- **Name**: [YOUR_COMPANY_NAME]
- **Positioning**: [e.g., "AI-first healthcare software development", "Fintech platform specialists", "Regulated industry SaaS consultancy"]
- **Founded**: [YEAR]
- **HQ**: [LOCATION]. [Optional: R&D centers / delivery locations]
- **Team size**: [e.g., "~100 specialists, ~50 in engineering"]
- **Staffing model**: [Project-based / retained teams / hybrid]
- **Specialization**: [2–4 lines on core capability areas]

## Track record

- [N]+ projects delivered
- [X]% client satisfaction (if measured)
- $[X]M in client funding secured (if your portfolio tracks this)
- [X]% repeat business
- [Other credibility metrics]

## Certifications and compliance capabilities

- [e.g., ISO 27001, ISO 9001, SOC 2, HIPAA, GDPR operational experience]

---

## Commercial parameters

### Rate card by role

Fill in the actual rates you charge. These anchor every capacity calculation the skill does.

| Role | Daily rate | Hourly rate |
|---|---|---|
| Project Manager | $[DAILY] | $[HOURLY] |
| Business Analyst | $[DAILY] | $[HOURLY] |
| UX/UI Designer | $[DAILY] | $[HOURLY] |
| QA Engineer | $[DAILY] | $[HOURLY] |
| Backend Developer | $[DAILY] | $[HOURLY] |
| Frontend Developer | $[DAILY] | $[HOURLY] |
| Mobile Developer | $[DAILY] | $[HOURLY] |
| Solution Architect | $[DAILY] | $[HOURLY] |
| [Other roles as needed] | | |

**Blended rate for capacity math**: $[X–Y]/hour depending on role mix.

When computing "budget ÷ rate → hours", use the blended rate that matches the expected role mix:
- Heavy-architecture projects push toward the higher end
- Pure-development projects push toward the lower end

### Currency

- **Primary currency**: [USD / EUR / GBP / other]
- **Secondary currency handling**: [e.g., "EUR for EU clients, converted at rate at estimate time and documented"]

### Target market

- [Customer segment 1 — e.g., Series A–C healthcare startups]
- [Customer segment 2 — e.g., Mid-market practices]
- [Customer segment 3 if applicable]

---

## AI-assisted delivery stance

**If your company uses AI-assisted delivery (Claude Code, Cursor, Copilot, etc.) as a core part of engineering, fill this section. If not, delete it.**

AI-assisted delivery is [the default standard / a client-opt-in option / not currently in use] at [COMPANY_NAME]. Implications for estimation:

- **How hour counts reflect AI**: [e.g., "Hour counts reflect AI-assisted velocity directly. We don't produce a pre-AI number and subtract."]
- **How AI savings are presented to clients**: [e.g., "Baked into the standard rate, not shown as a line item" / "Shown as a delta so client sees the saving" / "Configurable per project"]
- **How AI risk is disclosed**: [e.g., "Standard risk register entry acknowledging AI-assisted development with specific mitigations"]

### Productivity profile (internal only — do not show clients)

Use these factors when cross-checking whether a feature estimate is realistic. Different work types compress by different amounts with AI assistance:

- **Greenfield CRUD, forms, standard auth, boilerplate**: [substantial speedup — 30–40%+]
- **Custom UI, moderate business logic, standard integrations**: [meaningful speedup — 20–30%]
- **OCR/ML integration, external API integration**: [moderate speedup — 15–20%]
- **Complex enterprise integration (EHR HL7, legacy ERP)**: [limited speedup — 10–15%, bottleneck is other side]
- **Compliance documentation, security hardening**: [modest speedup — 10–20% on writing, nil on review/signoff]
- **Discovery, stakeholder interviews, pre-sales**: [human work — no meaningful speedup]
- **Production incident response, complex debugging**: [variable, often near-zero]

Adjust these based on your actual experience. These numbers are for internal calibration; they don't appear in client-facing artifacts.

---

## Cash flow and commercial reality

[Optional section — fill in if any of these factors meaningfully constrain your recommendations.]

- **Cash flow posture**: [e.g., "Constrained — compensation increases limited" / "Strong — can absorb investment bets"]
- **Pricing stance**: [e.g., "Premium positioning defended with quality, not price" / "Competitive-mid-market" / "Budget-value"]
- **Deal size targets**: [e.g., "Sweet spot $50–500K, larger deals require partner involvement"]

Implications for advisory:
- [How cash flow affects headcount recommendations]
- [How pricing stance affects competitive responses]
- [How deal size targets affect pre-sales effort allocation]

---

## Strategic priorities (ranked)

Fill with your company's actual ranked priorities. The skill uses these to sanity-check recommendations — a recommendation advancing priority #1 gets green light; one that adds overhead without touching any priority gets challenged.

1. **[Priority 1]** — [brief explanation of what this means and why it's top]
2. **[Priority 2]** — [brief explanation]
3. **[Priority 3]** — [brief explanation]
4. **[Priority 4]** — [brief explanation]
5. **[Priority 5]** — [brief explanation]

Typical categories at consultancies/agencies: knowledge management and code reuse, partnership ecosystem, internal products, recurring revenue services, IT governance and security posture. Pick what's real for you.

---

## Critical pain points

Name current organizational pain points the skill should reference when relevant. Don't sanitize — the skill works better when it knows the real constraints.

- [Pain point 1 — e.g., "No systematic estimation database"]
- [Pain point 2]
- [Pain point 3]
- [Pain point 4]
- [Pain point 5]

When a conversation touches one of these pain points, the skill should name it directly. Honest acknowledgment of operational gaps builds more trust than polished messaging.

---

## Reality-check ranges (recalibrate to your economics)

These ranges are what the estimator uses to sanity-check outputs. If an estimate falls outside these bands, the skill flags it for review.

**Fill these in based on your rates and typical project shapes.** The examples shown are illustrative only — calibrate to your actual portfolio.

| Scale | Timeline | Cost range | Typical feature hours |
|---|---|---|---|
| Discovery only | [X–Y weeks] | $[X]K–$[Y]K | (analysis, not features) |
| Extra Small | [X–Y months] | $[X]K–$[Y]K | [X]–[Y]h |
| Small | [X–Y months] | $[X]K–$[Y]K | [X]–[Y]h |
| Medium | [X–Y months] | $[X]K–$[Y]K | [X]–[Y]h |
| Large | [X–Y months] | $[X]K–$[Y]K | [X]–[Y]h |
| Very Large | [X+ months] | $[X]K+ | [X]h+ |

**Your anchor reference**: [Describe one completed project that acts as a mental anchor — e.g., "Project X: mobile MVP with 2 modules + admin portal = 600 feature hours, $80K total, 3 months. Falls in Small band."]

Anchors matter more than abstract ranges. When estimating a new project, the skill asks "how does this compare to [anchor]?" — that's more reliable than applying generic benchmarks.

---

## Contingency default

Your standard contingency applied to estimates:

- **Default**: [e.g., "+10% flat on both discovery and development" / "+15% on development, +5% on discovery" / "+20% fixed"]
- **Higher contingency triggers**: [situations where you deviate upward — e.g., unfamiliar external system integration, unclear regulatory path, high dependency on specific individuals, novel tech PoC]

Why this matters: contingency is one of the most-adjusted numbers in an estimate. Having your default locked in means the skill doesn't over-pad or under-pad out of generic caution.

---

## Capacity allocation (recalibrate)

When allocating hours across work categories in capacity-based estimates, use your actual split. The examples shown are a starting point.

| Category | % of hours |
|---|---|
| Feature development | [50–65]% |
| Testing | [15–20]% |
| Infrastructure & DevOps | [8–12]% |
| Project management | [8–10]% |
| Solution architecture / tech leadership | [10–15]% |
| Buffer | [5–10]% |

Projects with complex integrations push Infrastructure and Testing higher. Greenfield pushes Feature Development higher. Regulated industries push Testing and PM higher.

---

## Technology reference

**If your company has a preferred tech stack, default integration capabilities, or specific healthcare/fintech/industry expertise, create a `technology-reference.md` file alongside this one.** The estimator skill reads that file when the question touches stack, compliance, or integration choices.

Suggested structure for `technology-reference.md`:
- Default frontend frameworks
- Default backend languages
- Cloud preferences (AWS / Azure / GCP / multi-cloud)
- Interop standards you work with (FHIR, HL7, EDI, SWIFT, ISO 20022, etc.)
- Identity and access defaults
- Security defaults (encryption, key management)
- Infrastructure defaults (IaC, containerization, CI/CD)
- Industry-specific capabilities (EHR systems you've integrated, payment processors, etc.)
- Compliance frameworks in active operational use

The more specific this file, the better the skill's recommendations. A skill told "we integrate with Epic, Cerner, and Athena" produces sharper output than one working from generic "healthcare standards".

---

## Notes to maintainer

- Review this file at least annually. Rates drift, strategic priorities shift, and pain points change.
- When rates change, remember to also update the reality-check ranges — they're derived from rates.
- When AI-assisted delivery productivity profiles update (new tools, new patterns learned), update the productivity profile section.
- This file is the most opinionated piece of context the skill has. Keep it accurate.
