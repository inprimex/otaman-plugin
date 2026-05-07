# Technology Reference — Template

**Optional.** Copy this to `technology-reference.md` in the same directory and fill in with your company's actual stack, capabilities, and preferences. The skill reads this file when a question touches stack choices, compliance defaults, or integration complexity.

If you don't have strong stack opinions (or the skill should give generic recommendations), skip this file — the skill handles that gracefully.

---

## Frontend

- **Web**: [e.g., "React (primary), Vue, Angular"]
- **Mobile**: [e.g., "iOS Swift, Android Kotlin, React Native for cross-platform"]
- **When to recommend what**: [brief guidance — e.g., "default to React unless client has Vue/Angular ecosystem; native mobile when performance ceiling matters"]

## Backend

- **Primary**: [e.g., "Node.js"]
- **Secondary**: [e.g., "Python for ML-adjacent, Laravel for PHP-existing clients"]
- **Default recommendation**: [what you suggest for greenfield]

## Cloud

- **Capabilities**: [AWS / Azure / GCP / multi-cloud]
- **Decision factors**: [brief heuristic — existing footprint, compliance, cost structure]

## Standards (fill in the ones relevant to your industry)

### Interop
- [e.g., "FHIR R4 for healthcare data exchange"]
- [e.g., "HL7 v2 for legacy EHR"]
- [e.g., "ISO 20022 for financial messaging"]

### Identity and access
- [e.g., "OAuth 2.0 + OpenID Connect, SMART on FHIR for healthcare"]
- **IdP recommendations**: [e.g., "Auth0, Okta, Keycloak for cost-sensitive"]

### Security
- **At rest**: [e.g., "AES-256"]
- **In transit**: [e.g., "TLS 1.3"]
- **Key management**: [e.g., "Cloud KMS, never roll-your-own"]

## Infrastructure

- **IaC**: [e.g., "Terraform"]
- **Containers**: [e.g., "Docker + Kubernetes for multi-service"]
- **CI/CD**: [e.g., "GitHub Actions, GitLab CI, Azure DevOps depending on client context"]

---

## Industry-specific capabilities

### [Industry 1 — e.g., Healthcare]

**Integration experience**:
- [System 1 — e.g., "Epic (including SMART on FHIR)"]
- [System 2]
- [System 3]

**Standards in active use**:
- [e.g., HL7 v2, FHIR R4, EDI X12]

**Terminology experience**:
- [e.g., ICD-10, SNOMED CT, LOINC, RxNorm, CPT]

### [Industry 2 — e.g., Fintech]

**Integration experience**:
- [Payment processors you've worked with]
- [Banking core systems, if any]
- [KYC/AML providers]

**Regulatory experience**:
- [PCI-DSS levels]
- [Open banking / PSD2]
- [SOC 2 Type II support]

### [Other industries as applicable]

---

## AI/ML demonstrated capabilities

If your company has specific demonstrated outcomes, list them here — the skill uses these to ground advice in real capability:

- **[Capability 1]**: [outcome / metric, with caveat that numbers came from specific engagements]
- **[Capability 2]**: [outcome / metric]

Don't over-claim. These are talking points for "we've shipped this kind of thing before", not performance guarantees.

---

## Disaster recovery defaults

For contexts where DR is a standard consideration:

- **RTO**: [e.g., "< 4 hours for regulated workloads"]
- **RPO**: [e.g., "< 1 hour for regulated workloads"]
- **Lower/higher tolerances**: [when applicable]

---

## Compliance frameworks in operational use

List the frameworks you actively support, not aspirationally. Distinguish between your own certifications and your ability to build client systems that satisfy them.

- **[Framework 1 — e.g., HIPAA]**: [operational / self-certified / client-system experience only]
- **[Framework 2]**
- **[Framework 3]**

---

## How this file is used

When the skill needs to recommend a stack, integration approach, or compliance posture, it consults this file first. If the file names specific capabilities, the skill uses them; if the file is silent on a topic, the skill reasons from general principles and flags the gap.

The more specific this file, the sharper the skill's recommendations. Vague "we do healthcare" is much less useful than "we've integrated Epic via SMART on FHIR five times, Cerner via HL7 twice, and we have a templated HIPAA-compliant AWS landing zone in Terraform."

Keep this file current as capabilities grow.
