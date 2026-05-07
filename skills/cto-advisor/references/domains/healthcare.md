# Healthcare — Strategic Advisory Reference

## What's distinctive about advising in this domain

Healthcare CTO conversations are dominated by compliance economics and the tension between innovation pace and clinical/regulatory caution. The core question is rarely "what's the best technology" but "what's the cost of moving carefully versus the risk of moving fast." Push back hard when clients frame compliance as an engineering problem — it's a business strategy problem (risk appetite, audit readiness, regulator relationship) that engineering implements.

## Vendor landscape

### Hosting & infrastructure

- **AWS**: Has BAA, broadest service coverage with HIPAA-eligible services. Default for most US healthcare. 
- **Azure**: Strong if Microsoft-shop client; good for hospital integrations (Epic on Azure increasingly common).
- **GCP**: BAA available; good if leveraging Google Health AI services or genomics workloads.
- **Healthcare-specific**: Aptible (compliance-focused PaaS), Datica, ClearDATA — quicker time-to-compliance, higher per-unit cost.
- **On-prem / hybrid**: Still common for legacy hospital integrations; reluctantly accepted, not recommended unless required.

### Compliance & audit tooling

- **Audit logging**: Datadog (with BAA), AWS CloudTrail, custom hash-chained logs in PostgreSQL/Supabase
- **Vulnerability management**: Vanta, Drata, Secureframe (compliance automation); Qualys, Tenable (technical)
- **SIEM**: Splunk, Datadog, Sumo Logic (all BAA-capable in their healthcare tiers)
- **Pen testing**: Cobalt, HackerOne, Bishop Fox, smaller HIPAA-experienced firms

### EHR integration

- **Direct EHR API access**: Epic SMART on FHIR (App Orchard / Showroom listing), Athenahealth Marketplace, Cerner CODE
- **Integration platforms**: Redox (most popular abstraction layer), Particle Health, Health Gorilla, Zus Health
- **HL7 integration engines**: Mirth Connect (open-source), Rhapsody, InterSystems Ensemble

### Clinical content & terminologies

- **Drug data**: First Databank, Medi-Span (commercial); RxNorm, NIH DailyMed (open)
- **Medical coding**: ICD-10, SNOMED CT, LOINC, CPT (mix of free and licensed)
- **Clinical decision support**: Wolters Kluwer (UpToDate), Elsevier ClinicalKey, IBM Micromedex

## Hiring patterns

- **First hire profile**: Senior backend engineer with prior healthcare experience preferred, or willing to commit to 6 months of HIPAA upskilling. Compliance instincts cannot be retrofitted to a senior who's never worked under PHI handling.
- **Common gaps**:
  - Clinical informatics — someone bilingual in clinical workflow and software (often a clinician with technical bent or a software person who's done a healthcare informatics master's)
  - Compliance / Privacy Officer — usually one person dual-hatted with security; required for HIPAA covered entities
  - Integration specialists — HL7/FHIR is its own discipline; one engineer dedicated to integrations is common at >100 employees
- **Specialist roles**: Clinical Lead (often part-time or fractional clinician), DPO if EU operations, Patient Advocate (rare but valuable for product), Quality / Regulatory Affairs (mandatory for SaMD)
- **Outsourcing patterns**: Mobile development frequently outsourced; integration work often outsourced; compliance consulting and clinical review almost always external; backend infrastructure should be in-house once material PHI is handled.

## Common architectural debates

### "Build our own EHR integration vs. use Redox/Particle/Zus"

Default position: use an integration platform unless you have specific reasons not to. The platforms abstract away dozens of EHR variants, handle auth flows, give you a single API surface, and bring institutional knowledge of edge cases. Direct integration costs 3–10× more in engineering time and creates maintenance burden indefinitely.

Flip when: you need real-time bidirectional flows that platforms don't support; you're large enough that platform per-transaction pricing exceeds in-house build cost (typically >$500K/year platform spend); you're integrating with one specific EHR repeatedly and have built deep expertise.

### "Native mobile vs. React Native vs. Flutter for patient app"

Default position: React Native. Mobile teams in healthcare are usually small; one codebase serving both platforms is realistic. Native is justified when you need deep platform integration (HealthKit deep features, Apple Health record import, complex BLE for medical devices).

### "Self-host vs. SaaS for sensitive components"

Healthcare clients often want to self-host. Default position: SaaS with appropriate BAA is usually right; self-hosting puts compliance burden on you and rarely improves security in practice.

Flip when: data residency requirements rule out major SaaS; client is large enough to have real ops capability; specific regulatory requirement.

### "How quickly should we pursue SOC 2 / HITRUST?"

SOC 2 Type II is now table stakes for selling to mid-market and enterprise healthcare. Start the process before the first enterprise prospect, not after. HITRUST is heavier and only needed for specific contracts; pursue when a real opportunity demands it, not speculatively.

## Regulatory bottlenecks

- **FDA pathway timelines**: 510(k) typically 6–9 months from submission; PMA can be 2+ years. Pre-submission meetings extend timelines but improve approval odds. Plan project schedules around these realities.
- **EHR vendor approval processes**: Epic App Orchard / Showroom listing review can take 6–12 months. Cerner / Oracle Health is similar.
- **Hospital procurement**: Even after technical and security review, procurement can take 6–18 months. This is rarely engineering-blocked.
- **State telehealth licensing**: Each US state has different rules; multi-state launches require legal work.
- **BAA negotiation with hospital**: 2–6 months typical with health systems.

## Common pitfalls in advisory for healthcare

- Treating HIPAA as a checklist rather than a posture — covered entities pass technical checklists then leak via untrained staff or weak vendor controls
- Underestimating integration heterogeneity — even within "FHIR-compliant" EHRs, real-world implementations vary significantly
- Recommending speed over rigor when stakes are clinical — for SaMD, the right advice is often "go slower"
- Conflating B2B (hospital sales) and B2C (patient apps) — radically different sales cycles, compliance footprints, integration patterns
- Underestimating clinician change management — even excellent software fails if it adds friction to clinician workflow

## Escalation triggers specific to healthcare

- Any commitment to FDA pathway should involve CEO, board, and Chief Medical Officer
- PHI breach or near-miss requires immediate counsel involvement (not just engineering response)
- Decisions affecting clinical workflow should involve the clinical team, not just product
- Multi-jurisdiction expansion (US + EU, multi-state US) requires regulatory counsel before architecture commitments
- Connected medical device classification ambiguity should escalate to specialized regulatory counsel before development decisions
