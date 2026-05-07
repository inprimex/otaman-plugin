# Healthcare — Estimation Reference

## What's distinctive about this domain

Healthcare estimation is dominated by compliance overhead and integration complexity, not feature complexity. A healthcare patient app and a generic consumer app may have similar UI surface, but the healthcare version costs 30–80% more because of HIPAA controls, PHI audit logging, BAA-capable infrastructure, EHR integration patterns, and clinician workflow accommodations. The most common pre-sales failure is under-scoping the compliance and integration layer because it's invisible to the end user.

## Compliance frameworks that may apply

| Framework | When it applies | Effort impact |
|---|---|---|
| HIPAA | US PHI handling | +10–15% on greenfield, more on retrofit; requires BAA-capable hosting |
| GDPR Article 9 | EU patient health data | +10–20%; requires DPA with all sub-processors, EU data residency |
| FDA 21 CFR Part 11 | Software is a medical device or used in clinical decision-making | +40–80%; likely requires specialist partner; full V&V documentation |
| HITECH | US PHI breach notification | included with HIPAA, but increases auditing overhead |
| State privacy laws (CCPA, NY SHIELD, etc.) | US multi-state operations | +5–10% per significant state |
| 42 CFR Part 2 | Substance use disorder treatment data | +15–25% on top of HIPAA; stricter consent handling |
| EU AI Act (high-risk classification) | AI used in clinical decision-making in EU | +20–40%; conformity assessment and CE marking |

When HIPAA + GDPR + state privacy apply together, expect 30–40% compliance overhead, not the sum of individual percentages — intersections create edge cases not covered by any single framework.

## Common integrations and effort patterns

| Integration class | Typical providers | Effort range | Notes |
|---|---|---|---|
| EHR — modern FHIR | Epic (SMART on FHIR), Athenahealth, eClinicalWorks | 80–200h | Variable: Epic is well-documented but requires app review process |
| EHR — legacy HL7 v2 | Cerner (now Oracle Health), MEDITECH, older Epic deployments | 150–400h | Bidirectional often requires integration engine (Mirth, Rhapsody) |
| Lab integrations | Quest, LabCorp, regional labs | 60–150h per lab | HL7 ORU messages; each lab has format variations |
| Pharmacy / medication data | RxNorm, FDA NDC database, NIH DailyMed, First Databank, Medi-Span | 40–100h | Commercial sources cost license fees; open sources have coverage gaps |
| Telehealth video | Twilio Programmable Video, Vonage, Zoom for Healthcare, Doxy.me | 40–80h | Use BAA-capable tier; standard tiers don't cover PHI |
| eRx (e-prescribing) | DrFirst, Surescripts | 200–500h | EPCS for controlled substances adds DEA requirements |
| Imaging / DICOM | Orthanc, dcm4che, Ambra | 80–250h | Storage costs scale with image volume; PACS integration is its own discipline |
| Clinical terminologies | ICD-10, SNOMED CT, LOINC, RxNorm, CPT, HCPCS | minimal if just lookups | Significant if mapping between code systems |
| Wearables | Apple HealthKit, Google Fit, Fitbit, Oura, Withings | 40–80h per platform | OAuth flows + ongoing data sync |

## Feature taxonomy (typical modules)

- **Onboarding** — registration, identity verification, HIPAA consent capture, BAA acknowledgment for B2B
- **Patient Profile** — demographics, history, contacts, insurance, preferred pharmacy/clinician
- **Treatment / Medication Management** — medication list, dosing, reminders, side effect tracking
- **Symptom & Outcome Tracking** — patient-reported outcomes, symptom diaries, mood trackers
- **Lab Results & Diagnostics** — display, trends, clinician-mediated interpretation
- **Telehealth** — async messaging, video visits, e-consults
- **Scheduling** — appointment booking, reminders, intake forms
- **Clinician Portal / Provider Dashboard** — patient queues, review workflows, documentation
- **Billing & Payments** — copays, payment plans, insurance integration, statements
- **Compliance & Audit Infrastructure** — PHI audit logging, access controls, BAA management, data retention/disposal

## Recommended features sheet schema

For mobile-first healthcare projects:
- Backend (hours)
- Frontend / Admin Web (hours)
- Mobile (hours)
- **Total (hours)**

For web-only telehealth or clinician-facing platforms:
- Backend (hours)
- Frontend (hours)
- **Total (hours)**

The split matters because mobile work uses different staffing (mobile dev vs. web dev) and different testing cycles (device labs, App Store/Play Store review).

## Domain-specific risk register additions

### Risk: PHI handling controls fail audit

- **Category**: Compliance
- **Probability / Impact**: Medium / Critical
- **Description**: HIPAA audit identifies gaps in access controls, audit logging completeness, or BAA coverage. Result is mandatory remediation, potential breach notification, and reputational damage.
- **Mitigation**: Compliance-by-design from Day 1; all PHI access logged with hash-chained tamper-evident audit trail; quarterly internal compliance review; BAA tracking system with renewal alerts; least-privilege IAM enforced through code review.
- **Contingency**: Engage external HIPAA compliance counsel within 48 hours of finding; remediation plan within 1 week; client notification per BAA terms.

### Risk: EHR integration scope creep

- **Category**: Technical
- **Probability / Impact**: High / Medium
- **Description**: EHR integrations consistently expand beyond initial scope as edge cases emerge — new message types, additional patient cohorts, special characters in legacy systems. Initial estimate based on documentation rarely matches production reality.
- **Mitigation**: Integration spike in Discovery Week 1 with sample real data, not synthetic; explicit out-of-scope list signed by client; change request process for any integration scope additions.
- **Contingency**: Phase the integration — Phase 1 covers 80% of message volume; remaining edge cases addressed in Phase 2 with separate budget.

### Risk: Clinician adoption fails despite product working

- **Category**: Operational
- **Probability / Impact**: Medium / High
- **Description**: Healthcare software regularly ships on time, on budget, fully functional, and is then ignored by clinicians because it doesn't fit their workflow. The cost of the project is wasted regardless of technical success.
- **Mitigation**: Clinician shadowing during Discovery (not interviews — actual observation); pilot with single clinician champion before full rollout; minimize clicks-to-value; align with EHR session, not require parallel tool.
- **Contingency**: Workflow re-design sprint after pilot; if adoption stays below threshold, consider EHR-embedded delivery model instead of standalone app.

## AI-assisted productivity profile (overrides for healthcare)

- **HIPAA audit logging code** — modest speedup (15–20%); requires extra senior review for security correctness
- **HL7 v2 message parsing** — limited speedup (10–15%); training data on HL7 v2 is patchy and AI commonly produces parsers that miss legitimate variant formats
- **FHIR resource handling** — meaningful speedup (25–35%); FHIR R4 is well-documented and AI handles standard resources reliably
- **Clinical terminology mapping** — limited speedup (10–15%); AI hallucinates code mappings; always require lookup table verification
- **PHI test data generation** — substantial speedup (40%+); AI is excellent at generating realistic synthetic patient data for testing

## Anchor projects (typical scale calibration)

### Anchor: Mobile patient app MVP, 3-month delivery

- **Scope**: Mobile app (iOS + Android), 2 patient modules + clinician review portal, HIPAA-grade infrastructure
- **Total feature hours**: ~600h
- **Total cost** (at $70/h blended): ~$80K
- **Timeline**: 3-week discovery + 2-month development
- **Notable cost drivers**: Mobile cross-platform work, OCR/ML if document parsing involved, HIPAA infrastructure baseline (~80h alone)

### Anchor: Telehealth platform with eRx, 6-month delivery

- **Scope**: Web + mobile, async + video, e-prescribing (no controlled substances in MVP), 1 EHR integration
- **Total feature hours**: ~1,800h
- **Total cost**: ~$250K–$320K
- **Timeline**: 6-week discovery + 5-month development
- **Notable cost drivers**: Surescripts integration, video infrastructure (BAA-tier), state-by-state telehealth licensing logic

### Anchor: Clinical decision support / SaMD, 12-month delivery

- **Scope**: Production-grade software classified as a medical device, FDA 510(k) pathway
- **Total feature hours**: ~3,500h
- **Total cost**: ~$500K–$800K
- **Timeline**: 3-month discovery (incl. regulatory strategy) + 9-month development with V&V
- **Notable cost drivers**: FDA documentation (~30% of total effort), clinical validation studies, IEC 62304 software lifecycle compliance

## Common pitfalls in pre-sales for healthcare

- Clients say "HIPAA-compliant" without understanding what that means architecturally — assume nothing about their current infrastructure until verified
- "EHR integration" can mean anything from "embed our app in the EHR via SMART on FHIR" to "we exchange HL7 v2 messages with their on-prem instance via VPN" — ten-fold cost difference between these
- Clients underestimate clinician workflow constraints — software that adds 30 seconds per patient visit is rejected regardless of features
- Patient adoption rates are typically 20–35% even for excellent products; clients often plan for 60%+
- "Telemedicine" and "telehealth" are used interchangeably by clients but have different regulatory implications (telemedicine implies treatment; telehealth is broader)

## Domain-specific Gate 0 checks

- [ ] Identify all applicable compliance frameworks (HIPAA / GDPR / state laws / FDA pathway)
- [ ] Confirm whether software will be classified as a medical device (changes everything)
- [ ] Identify EHR system(s), version, integration pattern (FHIR / HL7 v2 / proprietary), test environment availability
- [ ] Confirm clinician availability for Discovery shadowing (not just interviews)
- [ ] Identify whether PHI is processed only or also transmitted to third parties
- [ ] Confirm BAA capability of all proposed third-party services
- [ ] Identify state-specific licensing requirements (telehealth is state-by-state in US)
