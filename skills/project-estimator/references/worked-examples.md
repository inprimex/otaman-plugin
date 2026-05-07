# Worked Examples

Two examples showing the gate flow ending in the two-artifact deliverable format (proposal + workbook excerpts). Read once to internalize how the flow lands. These examples use illustrative rates — actual rates should come from company-context.md.

---

## Example 1: Fast Track — a well-specified small project

### User's opening message

> Client brief: a boutique dermatology practice (single location, 2 dermatologists, ~4k active patients) wants a simple web app where patients can upload photos of skin concerns between visits. Doctors review during their daily admin block and either reassure/advise via secure message or schedule a visit. Client is on DrChrono EHR but doesn't need integration for this — the app stands alone with its own patient login. HIPAA compliance required. Budget $60K, timeline 4 months. Give me an estimate.

### Gate 0 — Information Verification

| Category | Score | Key findings | Critical gaps |
|---|---|---|---|
| Business context | 4 | Clear problem, specific scale (2 docs, 4k patients), concrete use case | Success metric not quantified (triage volume? wait-time reduction?) |
| Technical environment | 3 | Web app, standalone (no EHR integration), DrChrono on client side | Image storage expectations, mobile vs. web-only |
| Compliance | 3 | HIPAA stated, PHI involved (photos + messaging) | Audit depth, state-specific rules |
| Team | 2 | Two dermatologists named | Product owner, UAT ownership |
| Budget & timeline | 4 | $60K and 4 months stated | Business reason for 4 months not given |
| Domain-specific | 3 | Dermatology (photos are the primary modality) | Photo storage duration, patient consent for image use |

**Overall weighted confidence: 72%**. Healthcare + photo-heavy: Technical + Compliance weighted 40% combined.

**Assessment**: Fast Track — sufficient to proceed with documented assumptions. One high-value question worth asking: mobile app or responsive web? Changes mobile hours significantly.

### Fast Track: inline Gate 1 + Gate 2

Complexity scoring inline: Functional 2 / Technical 2 / Integration 1 (photo/PDF storage, Stripe if billing) / Compliance 3 / Uncertainty 1 = **9/25, Low band**.

Matrix: Low × 70–85% = **Tier B** (Simple Estimation).
Method: Analogous — maps closely to the healthcare-mvp-reference example in shape (mobile-first patient app, photo upload, secure messaging, HIPAA) but smaller scope (no OCR, no blood results, no external DB).
Constraint: Budget-constrained ($60K).

Proceeding with assumption: responsive web (not native mobile), based on "web app" in brief and budget envelope. Native iOS/Android would be +$40–60K — confirm with client before final proposal if they intended native.

### Gate 3 — Estimate (Tier B)

Capacity math (using illustrative $68/h blended rate — actual rate from company-context.md):
- Budget: $60,000
- Raw hours: $60,000 ÷ $68 = 882h
- At 0.75 productivity: ~660 effective hours
- Feature hours at ~60% of effective: ~395h feature hours

Credible envelope for: onboarding + photo capture + messaging + doctor dashboard + HIPAA infra.

### Proposal draft (5 slides)

**Slide 1 — Our understanding of [CLIENT]**
> [Client name] is a boutique dermatology practice serving around 4,000 patients across a single location. Patients today wait for their next scheduled visit to ask about skin concerns that arise between appointments. The proposed web app addresses this by letting patients send photos and short descriptions to their dermatologist, who can respond with reassurance, advice, or a scheduling recommendation during the daily admin block.
>
> Dermatology is well-suited to this model because visual information carries much of the clinical signal. A short image-plus-description exchange can resolve many non-urgent questions without a visit, while surfacing anything that genuinely needs in-person review.
>
> The first release should focus on the core exchange: photo upload, short message, clinician review and reply. Scheduling integration and more advanced workflows (history, trends, billing) can follow once adoption is validated.
>
> This creates a practical product that delivers visible value to patients quickly, reduces low-value visit volume, and establishes the foundation for expanded digital patient engagement.
>
> The long-term vision is a patient engagement platform that can extend to additional specialties or additional locations as the practice grows.

**Slide 2 — Your expectations and proposed MVP direction**

Your expectations:
- Web app for patients to upload skin concern photos between visits
- Doctors review during daily admin block, respond or schedule
- HIPAA compliance required
- Standalone (no EHR integration for MVP)
- Budget around $60K, timeline 4 months

Proposed MVP direction:
- Responsive web (mobile-first, no native app in MVP)
- Asynchronous review pattern (patient sends, doctor responds within agreed SLA)
- Focus on text + photo exchange; richer features (trends, history, video) as Phase 2
- HIPAA built into the foundation (BAA-capable hosting, audit logging, encryption)

**Slide 3 — Key assumptions and risks**

Assumptions:
1. **Responsive web, not native mobile** — We build a mobile-optimized web app. Patients access via browser. Native iOS/Android apps can follow in Phase 2 if adoption validates the model.
2. **Async messaging, not real-time** — Patients send, doctors respond during their review block. No live video or instant messaging in MVP.
3. **Photo storage in EU-region or US-region S3-compatible storage, encrypted at rest** — No DrChrono integration for MVP; patient records live separately in this system until/unless future integration is added.
4. **Clinician review workflow handled by the 2 dermatologists** — No nurse triage, no delegation to admin staff in MVP. Simple "my queue" model.

Risks:
1. **Photo upload reliability across devices** — Image capture on mobile browsers varies. Fallback: patients can upload from gallery; guidance on good-quality photo capture.
2. **HIPAA audit depth for messaging** — We build hash-chained audit logging from day one. Legal counsel review recommended for specific breach notification procedures (outside our scope, recommend partner firm).
3. **Low patient adoption** — Portal adoption in healthcare is typically 20–30% at launch. Mitigation: clear onboarding flow, email/SMS activation, integrated prompts at visit.

**Slide 4 — Why this approach gives the strongest start**

- Phased approach: Discovery → Development → Support
- HIPAA built in, not added later
- Mobile-first responsive web balances budget and accessibility
- Same team end-to-end
- Foundation supports Phase 2 expansion (native apps, EHR integration, video)

**Slide 5 — Recommended next step and phased investment**

Phase 1 — Discovery & POC
- Lock MVP scope, design the core exchange flow, technical decisions (hosting, storage, auth)
- Deliver clickable prototype and development plan
- Timeline: 2 weeks
- Estimated cost: **$7,200 – $7,920** (with +10% contingency)

Phase 2 — Development
- Build MVP: onboarding, photo capture, messaging, doctor dashboard, HIPAA infrastructure
- Timeline: ~10 weeks
- Estimated cost (ballpark): **$48,000 – $52,800**

Total: **~$55,200 – $60,720** — fits the $60K envelope with minimal stretch.

### Workbook excerpts

**Features sheet** (sample rows):

| ID | Module | Feature | MVP Tier | User Type | Complexity | BE/FE | Mobile | Total | MoSCoW |
|---|---|---|---|---|---|---|---|---|---|
| F01 | Onboarding | Patient Registration & HIPAA Consent | MVP Core | Patient | Low | 10 | 0 | 10 | Must Have |
| F02 | Photo Exchange | Photo Capture & Upload | MVP Core | Patient | Medium | 15 | 0 | 15 | Must Have |
| F03 | Photo Exchange | Message to Clinician with Image | MVP Core | Patient | Low | 10 | 0 | 10 | Must Have |
| F04 | Clinician | Doctor Review Queue | MVP Admin | Clinician | Medium | 20 | 0 | 20 | Must Have |
| F05 | Clinician | Clinician Response & Action (Reassure / Advise / Schedule) | MVP Admin | Clinician | Medium | 18 | 0 | 18 | Must Have |
| F06 | Infrastructure | HIPAA Auth + Audit Logging | MVP Infra | System | Medium | 30 | 0 | 30 | Must Have |

(and so on — typical ~15 features at this scope, ~280h total backend/frontend, responsive web so no separate mobile column hours)

**Project reference code**: `DERM-WEB-EST-260417`

### Why this flow works

- Gate 0 at 72% confidence → Fast Track → no separate Gate 1 pause
- Budget-constrained → capacity math drives scope
- Responsive web assumption (vs. native) flagged for client confirmation
- Healthcare MVP reference used as analogical anchor — similar shape, scaled down
- Ends in the actual deliverable format (proposal + workbook excerpt) with reference code

---

## Example 2: Stop & Redirect — an RFP asking for the impossible

### User's opening message

> Just got this RFP, they want a response by end of next week. Short summary: 'We are a regional health system with 12 clinics across Ohio seeking a technology partner to build a patient-centered digital front door with appointment scheduling, symptom checker, telemedicine integration, patient communications, billing transparency, and connection to our Cerner EHR. Proposals should include fixed-price quote and firm 12-month timeline. Respond by [date].' What's your read?

### Response

Before going into Gate 0 scoring — the RFP structure itself is a risk worth naming. The client is asking for a fixed-price quote against a firm 12-month timeline for a scope that spans six feature domains plus a Cerner integration. That's somewhere between several hundred thousand and over a million dollars of work, and no responsible firm can fix-price that against one-paragraph requirements. Bidding firms either over-contingency (price out) or under-scope (lose money). That framing needs to be part of the response, not buried.

With that said, the verification summary:

### Gate 0 — Information Verification

| Category | Score | Findings | Gaps |
|---|---|---|---|
| Business context | 2 | Regional health system, 12 clinics, Ohio, "digital front door" | No volume numbers, no success metrics, no driving business event |
| Technical environment | 1 | Cerner named, six feature domains | Cerner version (Millennium/Oracle Health), integration pattern, existing digital footprint |
| Compliance | 1 | Healthcare implies HIPAA | No explicit scope, no BAA posture, no audit requirements |
| Team | 0 | Nothing | Decision authority, IT resources, UAT ownership all blank |
| Budget & timeline | 1 | 12-month stated, no budget | Fixed-price without budget band is itself a red flag |
| Domain-specific | 1 | Six feature domains listed | Each domain has 2–5× variance depending on depth |

**Overall weighted confidence: 22%**

**Assessment**: Insufficient — this triggers three of the five stop conditions:
- Confidence < 30% with complexity indicators well above 10
- Critical integration (Cerner) with zero API/data information
- Compliance requirements implied but not detailed

**Producing a fixed-price Tier D/E document here would be fiction, not analysis.** The right response is to reframe the engagement.

### Recommended response strategy

Respond by the deadline with a **reframing document**, not a fixed-price quote:

1. **Acknowledge the RFP and deadline** — don't ghost. Regional health system RFP is a real opportunity; the shape just isn't viable.

2. **Propose paid discovery** — 4–6 weeks, $25–40K — producing the artifacts a fixed-price commitment would need: scope definition, Cerner integration assessment, compliance scope, phased plan, firm Phase 1 quote. Frame as the responsible path: protects the client from vendors who bid irresponsibly to win the RFP and then use change orders.

3. **Preliminary t-shirt range** — explicit as rough order of magnitude, not quote:
   - Scope as described, properly delivered over 18–24 months: **[high end of L / XL per company reality-check]**
   - Scope phased into a viable 12-month Phase 1 (appointment scheduling + patient comms + Cerner read): **[M / L band]**
   - Scope compressed to fixed-price-in-12-months as literally asked: **decline to bid**, with explanation

The client either engages with reframing (a better conversation than the fixed-price bidders are having) or they proceed with a vendor willing to quote the original — in which case we've avoided a deal that would damage relationship and P&L.

### Questions (internal, before drafting)

Blocking:
1. Prior relationship or warm intro with this health system? Changes the response tone.
2. Current capacity — do we want this at 18–24 months, or is this relationship/portfolio bidding?

High-value:
3. Any intel on other bidders? Determines effort level for reframing response.
4. Is Ohio a target market?

### Recommended next step

Don't proceed to Gate 1 or any further analysis. Draft the reframing response. If user agrees, produce a 2–3 page document: acknowledgment, proposed discovery engagement, t-shirt ranges with caveats, short "why this framing" section.

If the user decides to bid the original RFP as-is anyway, use Tier A t-shirt with very heavy disclaimers — and that should be an explicit decision because it's a departure from responsible risk handling.

---

## Patterns across both examples

1. **Speed matches complexity.** Example 1 collapses gates (Fast Track) because small well-specified project. Example 2 stops at Gate 0 because information doesn't support moving further.

2. **Assumptions are always quantified.** Every "proceeding on assumption" is explicit about what's being assumed and what's at risk.

3. **Ranges reflect actual confidence.** Example 1 lands within $60K budget with narrow range. Example 2 gives wide ranges because inputs don't support better precision.

4. **Deliverable format is consistent.** Example 1 ends in proposal+workbook shape with reference code. Example 2 recommends a reframing document, not a generic "we can't estimate this" response.

5. **Business language throughout.** Even internal gate outputs lean toward business-readable when about to produce client artifacts.
