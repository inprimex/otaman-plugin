# Estimation Principles

The core principles, with reasoning. When a principle feels abstract, this is where the justification lives.

## 1. AI-assisted delivery calibration (if applicable)

If your company uses AI coding tools (Claude Code, Cursor, Copilot, similar) as standard — see `company-context.md` for the specific stance — the implications for estimation:

- **Hour counts reflect AI-assisted velocity directly.** A feature that required 60 engineer-hours in 2022 may require 35–40 today. The estimate uses the new number.
- **Don't show the delta to clients (usually).** The number the client sees is the real cost of how the team works. Some companies show savings as a line item; others bake it in silently. Follow the stance in company-context.md.
- **Disclose AI use in the risk register.** A risk register entry ("AI-assisted development introduces code quality and security risks") is the responsible handling. Mitigations are real: human code review, senior review for security-critical paths, automated scanning, high test coverage target.

The reason openly disclosing AI use works: sophisticated clients (especially healthcare and fintech) are increasingly asking direct questions about AI. Firms that hide it look evasive; firms that disclose it with a credible risk-management framework look professional.

Not all work compresses equally. The productivity profile in company-context.md calibrates the expected speedup by task type.

## 2. Contingency matches company track record

2022-era consultancy contingencies of 20–30% made sense when estimation uncertainty was higher. Teams with a track record of disciplined discovery and (often) AI-assisted delivery are increasingly running +10% standard. Teams with less predictable delivery or less AI leverage may still need +15–25%.

Use whatever company-context.md specifies. Use higher contingency only when:
- Critical integration with unfamiliar external system
- Regulatory path unclear, may require rework
- Client team has high dependency on specific individuals
- Novel technology not previously exercised

Document the reason when you deviate.

## 3. Compliance overhead is visible, not hidden

Healthcare projects need HIPAA (US), GDPR Article 9 (EU), audit logging, BAAs, and associated infrastructure. Fintech projects need PCI-DSS, SOX, KYC/AML. Clients under-estimate these because they aren't visible to users.

The right move is to build compliance in explicitly as infrastructure features (Auth, API Gateway, Compliance Layer, CI/CD, audit logging backend). These appear as regular features with regular hour estimates, not as a separate "compliance tax" line.

Compliance scope guidelines:
- Baseline (GDPR operational / HIPAA operational): +10–15% of base effort, built into features
- Moderate depth (formal audit trails, penetration testing, risk assessment): +15–25%
- Multi-framework (HIPAA + state privacy, or GDPR + EU AI Act): +20–30%
- FDA 21 CFR Part 11 scope: +40–80%, likely requires specialist partner
- PCI-DSS Level 1: +30–60%, may be out of scope for in-house alone

## 4. Discovery is the cheapest scope insurance available

Discovery typically costs $8–20K for 2–4 weeks. Overrun on an under-scoped project typically costs $20–100K+, plus schedule slippage, plus relationship damage. The return on a $15K discovery investment is often 5–10× in avoided overrun.

**When to skip discovery:**
- Client provides genuinely detailed RFP + technical spec
- Project is a clear extension of a prior engagement
- Scope is small enough that discovery investment is disproportionate (<$50K projects)

**Red flag**: clients who actively resist discovery usually have unrealistic expectations or insufficient commitment. Surface this before contract, not after.

## 5. Technology stack decisions create 10–100% cost variations

Same requirements, different stack, radically different cost. Examples:
- Content site: static generator ($5K) vs. custom CMS ($50K) — 10× delta
- Internal dashboard: Metabase/Superset integration ($10–20K) vs. custom React build ($40–80K) — 2–4× delta
- Mobile app: responsive web / PWA ($30K) vs. cross-platform React Native ($60–80K) vs. native iOS + Android ($120K+) — 2–4× delta

Over-engineering for unvalidated requirements is expensive. Clients build for the load they hope to have in 3 years, not what they have today.

**Advisor move**: when a client insists on over-spec stack, explain the cost implication in specific numbers. Don't just say "that's more than you need" — show the delta.

## 6. Budget-scope mismatches need diplomatic education, not rejection

A client walking in with $50K for a $200K project is common. Wrong moves:
- "That's way too low" — client feels dismissed, the relationship is damaged
- Pretend to agree — lose money or over-promise

Right move: educate. Show what $50K actually buys (MVP, single integration, limited compliance). Identify what's driving their number (previous quote for simpler project, internal political number, misunderstanding). Offer phased approach: Phase 1 at their budget delivering real value, with path to full scope later.

Clients often need a guide through this conversation, not a verdict.

## 7. Phased delivery is the default

Waterfall "scope everything, build it all" is almost always wrong. Exceptions: regulated workflows where partial delivery isn't viable, migrations with hard cutover, fixed-scope contracts that can't renegotiate.

For most projects: MVP (2–4 months, validates core value) → V1 (3–6 months, production expansion based on learnings) → V2+ (feature expansion based on usage data).

Cheaper (validated spending), faster (time-to-market), less risky (smaller bets). Clients who resist phased delivery often have political reasons (hard date tied to funding/board) or misunderstanding about how software delivers value.

**Advisor move**: even when a client asks for full-scope estimate, offer the phased alternative in the scope options.

## 8. Business language leads; technical language earns its place

The client reads the proposal and the workbook. Both audiences — commercial and technical — need to find what they need.

- Proposal: exclusively business language. "Medication data is the backbone of the treatment plan module" not "the data layer requires a reliable external source."
- Workbook summary, assumptions, risks, discovery: still client-readable. Written for someone to evaluate the project, not build it.
- Workbook features sheet: description in business language, Notes column holds technical implementation detail.
- Workbook project schedule: role-based, with comments explaining what each role does.

A commercial reader should be able to read the proposal and summary sheet and understand what they're buying. A technical reader should be able to go into features + notes and architecture and understand what gets built.

## 9. You're a translator

Pre-sales sits between engineering and commercial. Every estimate is a communication artifact:

- Technical complexity → hours → dollars
- Risk → contingency numbers and mitigation costs
- Architecture decisions → trade-offs the business can evaluate

Every estimate is read by (at least) an engineering reader and a commercial reader. The proposal speaks to the commercial reader first; the workbook accommodates both.

## 10. Legal and audited financial determinations aren't yours to make

You can speak to: compliance strategy, effort estimates, cost implications of regulatory postures, risk exposure in rough terms, recommendations for partner consultation.

You can't speak to: whether an implementation satisfies a specific regulation (lawyer's call), audited financial projections (CFO work), binding legal advice.

When questions cross into those territories: say so and recommend consultation. A crisp "I'm the CTO, not the lawyer — here's how I'd frame the review; the determinations belong to counsel" is honest and professional.

## 11. The gate structure prevents specific failure modes

The gates aren't bureaucracy. Each one prevents a specific estimation failure:
- **Gate 0**: prevents estimating on information too thin to support it
- **Gate 1**: prevents miscalibrated methodology for project complexity
- **Gate 2**: prevents claiming precision the inputs don't support
- **Gate 3**: prevents drift from approved methodology during production

When the user suggests skipping a gate, name the failure mode being risked — don't refuse. User is authority; they can accept risk. Risk should be named, not invisible.

## 12. Name the fallback for every hard part

Every risk in the register has a contingency plan. Every assumption has an alternative path. Every hard dependency has a plan B.

Clients don't want a list of things that could go wrong — they want confidence that the team has thought through what happens if something goes wrong. The pattern is: "We think X. If X doesn't work, we do Y. If Y doesn't work, we do Z." Three levels deep on every risk area.

This also prevents analysis paralysis in pre-sales. When a client raises "what if [thing]", you can answer with the fallback rather than restructuring the whole estimate.

## 13. Ranges widen when confidence drops — they don't narrow for client comfort

An estimate like "$80K–$88K at +10%" says: "We're confident the real answer is in this band." A client asking you to "narrow it to $75K" is asking you to reduce uncertainty, which you can only do by getting more information (discovery) or accepting more risk (taking on the band you're removing).

Explain this trade-off when it comes up. Clients who push for narrower ranges often don't understand that the range width is a feature, not a bug. A narrow range on thin inputs is false precision — more useful to no one than an honest range.
