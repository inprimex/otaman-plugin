# Example: Healthcare Patient App MVP — Canonical Reference

**This is an anonymized reference example showing the expected deliverable format.** Read this file when calibrating tone, structure, or level of detail. The project described is a composite / anonymized MVP estimate for a mobile-first patient app — realistic enough to teach the format without identifying any specific company.

The format itself is what matters. Your actual deliverables will use your company's rates, your customer's product name, and your domain — but the structure, column schemas, and language patterns shown here are what you match.

## Project shape at a glance

- **Client**: "ACME Health" (placeholder) — healthcare startup targeting an EU market, founder-led
- **Scope**: Mobile app (iOS + Android), 2 patient modules (medication management + blood results interpretation), clinician portal
- **Timeline**: 3-week discovery + 2-month development, target beta in month 4
- **Investment** (at illustrative rates of $60/h for most roles, $105/h for Solution Architect):
  - Discovery: $11,400 – $12,540 (with 10% contingency)
  - Development: $69,000 – $75,900 (with 10% contingency)
  - **Total: $80,400 – $88,440**
- **Team**: PM, BA, SA, UXUI in discovery; add Backend Dev, Mobile Dev, Frontend Dev, QA for development

**Scale calibration**: This is a full healthcare MVP — two patient-facing modules plus clinician portal plus HIPAA-grade infrastructure — and it comes in at ~600 feature hours, ~$80K total. Use this as your mental anchor for what a mobile healthcare MVP looks like at these economics. If you're estimating similar scope and coming in at 2–3× this, something's probably wrong with your scope or your rates.

## The proposal (5 slides)

### Slide 1 — Our understanding of ACME Health

> ACME Health is designed to help patients with chronic conditions better understand and manage their treatment, symptoms, and test results through a simple mobile-first experience.
>
> [The target market] is a strong first market: patient information is fragmented, clarity is limited, and there is clear demand for better self-management support between doctor visits.
>
> The first release should focus on practical, visible use cases such as medication understanding, treatment organization, reminders, side-effect awareness, and blood test interpretation with clinician oversight.
>
> This creates a product that is useful for real patients early, credible in investor conversations, and strong enough to validate market demand before broader expansion.
>
> The long-term vision is a scalable patient platform that can grow beyond the initial market without requiring a rebuild of the core experience.
>
> A focused first release backed by [the founding team's] vision can turn ACME Health from a strong concept into a credible product foundation with early patient relevance and long-term expansion potential.

**What to notice**: Six short paragraphs. Business framing throughout. Startup-founder language ("investor conversations", "validate market demand", "credible"). Direct reference to the client's leadership. Closing sentence is the thesis — "turn [current state] into [future state]".

### Slide 2 — Your expectations and the proposed MVP direction

**Your expectations:**
- Launch early product with clinic patients [by target date]
- Mobile app as primary patient experience on iOS + Android
- No AI-generated treatment recommendations in MVP, informational only
- Clinician oversight for any meaningful clinical interpretation
- Validate product-market fit with real patients before scaling
- Foundation that can scale beyond the first market without rebuild

**Proposed MVP direction:**
- Keep the MVP disease-agnostic
- Focus on medication understanding and organization first
- Include blood-results interpretation with conservative logic and clinician review
- Keep the scope practical, launchable, and investor-friendly

**What to notice**: Left column reflects client's stated requirements in their own language. Right column adds the shape we recommend — specific scoping choices we're making on their behalf.

### Slide 3 — Key assumptions and risks to address early

**Key assumptions:**
1. **Medication database integration** — We assume usable access to [preferred data source A] or [data source B]. If neither provides commercially viable structured access, we build a curated fallback database for the top medications relevant to your early users.
2. **Clinician review handled by your team** — [Named clinician lead], with [backup] as support, reviews the relatively small number of blood results flagged as significant. This avoids the need for an external doctor marketplace in the MVP.
3. **Technology stack enables future scaling** — Cross-platform mobile, EU-region cloud hosting, and a modular backend create a scalable foundation from day one.
4. **Investor-ready materials delivered in [month]** — The Discovery phase produces the clickable prototype, technical architecture, and development plan needed for investor conversations.

**Key risks:**
1. **Securing reliable medication data** — Medication data is central to the product's value. If [primary sources] don't work, fallback options include alternative European sources or a curated dataset covering the top medications used by your patients.
2. **Reading [target-language] medication packages and lab reports reliably** — OCR performs well in English, but [target-language] pharmaceutical packaging and lab formats must be validated on real samples. If accuracy isn't strong enough, patients can manually correct extracted text and the product still retains value through medication organization.
3. **Regulatory positioning** — The MVP should remain conservatively positioned: informational framing only, no AI-generated treatment recommendations, clinician review for anything significant.
4. **[Target date] launch is aggressive** — Timeline is achievable but tight. Scope discipline, early validation, and phased fallback path are essential.

**Closing**: "The key assumptions and risks are manageable, as long as they are addressed early and translated into clear product and delivery decisions."

**What to notice**: Every risk includes its fallback in the same bullet. Risks aren't scary — they're managed. Specific technical details ("20+ real medication packages and 10+ lab reports"), specific system/source names, specific fallback paths.

### Slide 4 — Why this approach gives ACME Health the strongest start

- **Phased approach** — Discovery & POC → Development → Support & Maintenance. You commit one phase at a time, not the full project upfront.
- **Validated technology choices** — OCR and key technical assumptions are tested during Discovery with real samples, not left unproven until development.
- **Investor-ready deliverables** — Clickable prototype, architecture documentation, and technical specifications support fundraising and technical due diligence.
- **Same team end-to-end** — The team shaping the product during Discovery stays involved in delivery, reducing handover risk and preserving context.
- **Built for launch now and scale later** — The technical foundation supports expansion without requiring a rebuild.
- **Fallback path protects momentum** — If needed, the [highest-priority module] can launch first, with remaining functionality following shortly after.

### Slide 5 — Recommended next step and phased investment

**Phase 1. Discovery & POC Phase**
- Define MVP scope, priorities, and feature boundaries
- Validate medication data access, OCR feasibility, and regulatory framing
- Deliver clickable prototype, architecture direction, and development plan
- Timeline: 3 weeks
- Estimated cost: **$11,400 – $12,540**

**Phase 2. Development Phase**
- Build the first usable product version for early clinic-patient testing
- Focus on the highest-priority modules confirmed during discovery
- Prepare for initial pilot launch and real-user feedback
- Timeline: ~2 months
- Estimated cost (ballpark): **$69,000 – $75,900**

**Closing**: "This phased approach keeps the first commitment focused while providing a clear path toward an early working product."

## The workbook — key excerpts

### Discovery & POC sheet (sample rows)

| ID | Phase | Action | Owner | Priority | Deliverable | Why? |
|---|---|---|---|---|---|---|
| D01 | Discovery Week 1 | [Data source] Technical Assessment | Solution Architect | Critical | Assessment report showing whether we can access [the primary data sources] for medication and side-effect data — what's available, under what terms, and how well it covers the target market. Includes fallback recommendations if direct access isn't viable. | Medication data is the backbone of the treatment plan module. We resolve this question in week 1 so the rest of discovery builds on verified foundations. |
| D03 | Discovery Week 1 | OCR Testing - [Target-Language] Content | Solution Architect | Critical | Working prototype showing text recognition accuracy on real [target-language] medication packages and lab reports, with a comparison of the top three and our recommendation. | Proves the most technically uncertain part of the product works before we commit to development. |
| D09 | Discovery Week 2 | Technical Specification | Solution Architect + BA | High | Complete feature specification, API contracts, and data model ready for development. | Turns discovery decisions into a buildable blueprint. Developers start day one of development productively, not reverse-engineering requirements. |

**What to notice**: "Why?" column speaks to the client's perspective ("for investor conversations", "developers start day one productively"). Not internal justification.

### Features sheet (sample rows, healthcare pattern)

| ID | Module | Feature | Description | MVP Tier | User Type | Complexity | BE/FE (h) | Mobile (h) | Total (h) | MoSCoW | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F01 | Onboarding | User Registration & Authentication | Email/phone registration, social login (Google/Apple), email verification, password reset, OTP | MVP Core | Patient | Low | 10 | 6 | 16 | Must Have | Backend: auth service, JWT, OAuth flows, OTP. Mobile: login/register screens, token storage, session handling. |
| F04 | My Treatment Plan | Medication Photo Upload & OCR | Camera capture of medication packages. OCR recognition of drug name / active substance / dosage from printed text. No handwriting. No barcode for MVP. | MVP Core | Patient | High | 25 | 20 | 45 | Must Have | Backend: OCR service integration, image processing pipeline, result parsing, confidence scoring. Mobile: camera UI, image capture/crop, OCR result review/correction screen. |
| F23 | Clinician Portal | Clinician Review Dashboard | Queue of flagged blood results. View patient results + context. Approve / add notes / flag for follow-up. Notifications. | MVP Admin | Clinician | Medium | 25 | 0 | 25 | Must Have | Backend only (web admin framework). Review queue, patient context view, action buttons, notification triggers. No mobile component. |

**What to notice**:
- Description is explicit about scope ("No handwriting. No barcode for MVP.") — prevents scope creep
- Notes column splits backend work from mobile work explicitly
- Zero in mobile column for clinician features because they're web-only
- Total hours = BE/FE + Mobile (column formula)

**Total hours**: 391h backend/frontend + 205h mobile = 596h total across ~30 features. Averages ~20h per feature. Range: 10h (simple CRUD) to 45h (OCR with complex flow).

### Assumptions sheet (sample rows)

| ID | Category | Assumption | Impact if Wrong (cost) | Verification Method | Verification Timing |
|---|---|---|---|---|---|
| A01 | Platform | We build one mobile app codebase that runs on both iOS and Android, reducing development cost and ensuring feature parity. The clinician portal is a lightweight web application using a proven admin framework. | 21000 | Confirm framework in discovery Week 1 architecture spike | Discovery Week 1 |
| A02 | Data Integration | We assume one of the two medication databases identified will provide usable access for our integration. If neither works commercially, we switch to alternative sources or build a curated dataset for priority medications. | 8000 | Discovery Week 1: technical assessment of both sources - API availability, data format, licensing, coverage | Discovery Week 1 |
| A03 | Scope | The MVP contains two patient modules plus a clinician portal. Both are disease-agnostic. No AI-generated treatment recommendations in the MVP — this keeps regulatory complexity low. | 30000 | Lock in discovery | Discovery Week 1 |

**What to notice**: Impact numbers are real cost amounts (21K, 8K, 30K in whatever currency). These are the cost of being wrong — what it would take to recover. Verification timing is concrete: almost everything gets verified in Discovery Week 1.

### Risks sheet (sample rows — note the AI-assisted development risk)

| ID | Category | Risk | Prob | Impact | Score | Impact Description | Trigger | Mitigation | Contingency |
|---|---|---|---|---|---|---|---|---|---|
| R03 | Technical | Text recognition may not work reliably on target-language content — Most text recognition technology is optimised for English. Target-language medication packaging and lab report formats need real-world testing. | Medium | Medium | High | 30-55h rework. Poor OCR undermines both modules. | OCR accuracy <85% on target-language samples during discovery testing. | We test the top three providers on 20+ real target-language medication packages and 10+ lab reports during the first week of discovery. If accuracy is insufficient, the product falls back to manual patient correction with OCR as an enhancement — the product still delivers value through the medication database and treatment organisation. | Manual entry as primary input with OCR as enhancement. Photo stored for reference. Iterate accuracy post-launch. |
| R06 | Development | AI-assisted development introduces code quality and security risks — We use AI coding tools to accelerate development. Without proper controls, AI-generated code can contain subtle bugs or security issues, particularly in authentication and data handling. | Medium | Medium | Moderate | 50-150h remediation if security audit finds issues. Reduced from High: MVP scope is predominantly standard patterns where AI tooling is most reliable. | Code review catches recurring issues in AI-generated code; security scan flags vulnerabilities in auth or data handling. | Every line of AI-generated code is reviewed by a human developer. Security-critical code (authentication, payments, patient data, GDPR) gets additional senior developer review. Automated security scanning runs on every code change. Architecture patterns and coding standards are defined upfront to guide the AI. Test coverage target: >80%. | Reduce AI tooling usage for flagged areas; hand-code security-critical paths. Accept slightly slower velocity in affected modules. |
| R10 | Compliance | Patient health data has the strictest privacy rules in the EU — Processing health data under GDPR Article 9 requires explicit consent, formal agreements with every service provider, and potentially a Data Protection Officer. Non-compliance carries fines up to €20M. | High | Medium | Medium | 15-25h implementation. Non-compliance: fines up to €20M. | Health data processing in EU triggers Article 9. | GDPR compliance is built into the product design from day one: granular patient consent during onboarding, formal data processing agreements with all service providers, EU-only data residency, one-click data export and deletion. External GDPR consultant engaged if needed. | External GDPR consultant if needed. Limit processing scope. |

**R06 is the standard AI-assisted development risk entry.** Include this in every project's risk register if your company uses AI coding tools. The wording above is the canonical version — adjust scope-specific details but preserve the structure and the mitigations. Openly naming the risk with concrete controls builds more trust than hiding it.

### Project schedule (development phase example)

| # | Role | Comments | Cost | Hours | Days | Daily Rate | WK1 | WK2 | WK3 | WK4 | WK5 | WK6 | WK7 | WK8 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Project Manager | Coordination, estimation, planning, integration | $9,600 | 160 | 20 | $480 | 20 | 20 | 20 | 20 | 20 | 20 | 20 | 20 |
| 2 | Solution Architect | Tech leadership | $18,900 | 180 | 22.5 | $840 | 40 | 20 | 20 | 20 | 20 | 20 | 20 | 20 |
| 3 | Backend Dev | Node.js | $15,000 | 250 | 31.25 | $480 | | 40 | 40 | 40 | 40 | 40 | 40 | 10 |
| 4 | Mobile Dev | React Native / Flutter | $12,600 | 210 | 26.25 | $480 | | 40 | 40 | 40 | 40 | 20 | 20 | 10 |
| 5 | Frontend Dev | React | $4,800 | 80 | 10 | $480 | | | 20 | 20 | 10 | 10 | 10 | 10 |
| 6 | QA | Testing of implemented features | $7,200 | 120 | 15 | $480 | | | 20 | 20 | 20 | 20 | 20 | 20 |
| 7 | UX/UI | Design support | $900 | 15 | 1.875 | $480 | | 5 | | 5 | | 5 | | |

**TOTAL: $69,000**
**TOTAL (with +10% contingency): $75,900**
**Timeline: 2 months**

**What to notice**:
- Week-by-week hours per role, showing delivery shape (SA front-loads, QA joins in week 3, mobile dev tapers at end)
- UAT is the last sprint (weeks 7–8) with reduced dev capacity
- Contingency is a flat +10% line, not distributed across roles
- Total cost and total hours shown per role

## Key takeaways for using this reference

1. **Hours are tight.** 596 total feature hours + ~140h discovery = a full healthcare MVP. If you're estimating a similar-scope project above ~800h, something's wrong — either scope creep or mis-rated complexity.
2. **Rates are concrete (at this example's economics).** $60/h for most roles, $105/h for Solution Architect. Your rates may differ — adjust per your company-context.md file. The structure of the schedule (role × week × hours) is what transfers, not the specific dollar figures.
3. **Contingency is flat +10%.** Tighter than 2022-era 20–30% because AI-assisted delivery reduces variance. If your company's track record supports it, use 10%. If not yet, document your current contingency default in company-context.md.
4. **Two-artifact delivery.** Proposal (5 slides) + workbook (6 sheets). Missing either is incomplete.
5. **Business language throughout.** Even in the features sheet, descriptions are written for the client to evaluate, not for engineers to implement.
6. **AI risk is openly stated.** R06 is in the risk register when AI tooling is part of delivery. Trust-building move that distinguishes professional delivery from hidden corners.

## Adapting this example to your project

When you use this as a reference for a new estimate:

- Keep the **structure** (5 slides, 6 workbook sheets, specific column schemas)
- Keep the **language patterns** (business framing, named fallbacks, quantified impacts)
- Replace the **domain specifics** (healthcare MVP details → your actual project)
- Replace the **rate figures** (this example's rates → your company's rates from company-context.md)
- Calibrate **hour ranges** against your company's actual productivity, not this example's
- Preserve the **R06 AI-assisted development risk** if your company uses AI coding tools; remove or adapt if not

The structure is the IP. The numbers and details change per project.
