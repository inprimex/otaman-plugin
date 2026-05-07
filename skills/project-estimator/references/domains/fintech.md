# Fintech — Estimation Reference

## What's distinctive about this domain

Fintech estimation is dominated by three things: PCI-DSS scope (which can multiply infrastructure cost by 5–10×), regulatory variation by jurisdiction (every country has different KYC/AML, money transmission, lending, and securities rules), and trust requirements that demand higher quality than typical SaaS (a payment bug isn't a bug, it's a financial loss). The most common pre-sales failure is treating "fintech" as one domain — a payments app, a lending platform, a wealth management tool, and a crypto exchange have almost nothing in common from an estimation perspective.

## Compliance frameworks that may apply

| Framework | When it applies | Effort impact |
|---|---|---|
| PCI-DSS Level 1 | Direct card processing >6M transactions/year | +30–60%; requires QSA, network segmentation, annual audit |
| PCI-DSS Level 2-4 | Lower volume direct card processing | +15–25%; SAQ self-assessment |
| PCI-DSS via SAQ-A | Card data fully tokenized via processor (Stripe Elements, Adyen Components) | minimal; this is the right architecture for most projects |
| KYC/AML (US: BSA, FinCEN) | Money transmission, custody, lending | +20–35%; integration with KYC vendor mandatory |
| GDPR | EU customers | +10–20%; financial data is sensitive category |
| PSD2 / Open Banking | EU/UK payment initiation or account info | +15–30% if implementing AISP/PISP; less if just consuming |
| SOX | Public company or material to public company financials | +20–40%; controls documentation, IT general controls |
| SOC 2 Type II | Required by enterprise customers | +10–15% on first year; less ongoing |
| State money transmitter licenses (US) | Funds custody across state lines | +30–80%; per-state licensing is brutal |
| MiCA (EU) | Crypto assets in EU | +15–25%; new regulatory framework, evolving |
| FFIEC guidance | US banks and credit unions | +10–20%; vendor risk management documentation |

When KYC/AML + PCI-DSS Level 1 + state money transmitter apply (typical for a US-based money movement startup at scale), expect 60–100% compliance overhead and consider whether a banking-as-a-service partner (Synapse, Treasury Prime, Unit) is a faster path than direct compliance.

## Common integrations and effort patterns

| Integration class | Typical providers | Effort range | Notes |
|---|---|---|---|
| Card processing | Stripe, Adyen, Braintree, Checkout.com | 30–80h | Stripe Elements is fastest; full Stripe Connect for marketplaces is 200h+ |
| ACH / bank transfers (US) | Plaid, Modern Treasury, Stripe Treasury, Dwolla | 60–150h | Same-day ACH adds settlement complexity |
| Open banking (EU/UK) | Tink, Yapili, TrueLayer, Plaid (EU) | 80–200h | PSD2 SCA flows; per-bank quirks |
| KYC / identity verification | Persona, Onfido, Jumio, Veriff, Alloy | 40–100h | Document + biometric verification standard; sanctions/PEP list checks |
| AML transaction monitoring | Sardine, Sumsub, ComplyAdvantage, Chainalysis (crypto) | 80–250h | Rule engine + case management; often bought, not built |
| Fraud detection | Sift, Sardine, Stripe Radar, Forter | 40–120h | ML-based; fine-tuning takes weeks of production data |
| Banking-as-a-Service | Treasury Prime, Unit, Synctera, Synapse | 200–500h | "BaaS" is its own integration category; sponsor bank relationship has its own governance |
| Stablecoin / crypto rails | Circle (USDC), Bridge, Stripe (crypto), MoonPay | 100–300h | Reg uncertainty; counterparty risk; on/off-ramp UX |
| Accounting / ledger | Treasury Prime native ledger, custom double-entry, QuickBooks/Xero sync | 80–250h | "Build a ledger" is deceptively complex; consider Modern Treasury or Fragment |
| Card issuance | Marqeta, Stripe Issuing, Lithic | 100–300h | Card programs require sponsor bank; KYB on cardholders adds to KYC burden |

## Feature taxonomy (typical modules)

- **Account Management** — registration, KYC, risk-based onboarding, beneficial owner declarations (KYB)
- **Funding Sources** — bank account linking, card vaulting, balance management
- **Money Movement** — transfers (ACH, wire, RTP), pay-ins, pay-outs, cross-border
- **Card Programs** — physical/virtual issuance, controls, transaction authorization
- **Lending** — application, decisioning, servicing, collections (each is its own subdomain)
- **Investments** — order management, custody, reporting, tax documents
- **Compliance Operations** — KYC review queue, suspicious activity monitoring, SAR filing workflow
- **Customer Support** — case management with PII access controls, transaction tracing
- **Reporting & Reconciliation** — daily settlement, treasury reporting, regulatory filings
- **Audit & Controls Infrastructure** — immutable transaction log, separation of duties, change management

## Recommended features sheet schema

For most fintech projects (web + mobile is common):
- Backend (hours)
- Frontend (hours)
- Mobile (hours)
- **Total (hours)**

For backend-heavy infrastructure (BaaS, ledger, card issuing where customer UI is minimal or partner-handled):
- Backend Core (hours)
- Backend Integrations (hours)
- Admin / Ops Tools (hours)
- **Total (hours)**

Ops tooling is often underestimated in fintech — every feature needs a back-office equivalent for compliance/customer support/reconciliation.

## Domain-specific risk register additions

### Risk: Sponsor bank relationship friction or termination

- **Category**: Commercial
- **Probability / Impact**: Medium / Critical
- **Description**: Banking-as-a-Service architectures depend on a sponsor bank that can change policies, raise fees, or terminate relationships. The Synapse 2024 collapse demonstrated downstream impact on neobanks.
- **Mitigation**: Multi-sponsor architecture from MVP if feasible; legal review of BaaS agreement termination clauses; quarterly relationship health reviews.
- **Contingency**: Migration playbook documented from start; pre-negotiated alternative BaaS provider; client communication plan.

### Risk: KYC vendor false positive rate breaks onboarding funnel

- **Category**: Operational
- **Probability / Impact**: High / Medium
- **Description**: KYC vendors typically reject 10–25% of legitimate applicants in production. The economics of the product may assume better conversion than the vendor delivers.
- **Mitigation**: Discovery includes test cohort against vendor; multi-vendor fallback (e.g., Persona primary, Veriff secondary); manual review queue staffed appropriately.
- **Contingency**: Vendor swap if false positive rate exceeds threshold; loosen risk thresholds with compensating controls; offer in-person verification alternative.

### Risk: Transaction monitoring rules generate unmanageable alert volume

- **Category**: Operational
- **Probability / Impact**: High / Medium
- **Description**: AML rule engines produce 100–1000× more alerts than true positives in early deployment. Compliance team can't triage; SAR backlogs trigger regulator scrutiny.
- **Mitigation**: Discovery includes alert-volume modeling against expected transaction patterns; tiered rule sensitivity; automated case scoring with ML augmentation post-MVP.
- **Contingency**: Vendor swap to provider with better tuning; engage external AML consultancy to refine rules; temporary slowdown of customer growth until backlog clears.

### Risk: Reconciliation breaks on edge cases (returned ACH, partial settlements, currency conversion)

- **Category**: Technical
- **Probability / Impact**: High / Medium
- **Description**: Money movement systems must reconcile to the penny across pending/settled/returned/disputed states. Edge cases (NSF returns 5 days post-transfer, partial wire settlements, FX rate at booking vs. settlement) consistently surface in production after MVP launch.
- **Mitigation**: Double-entry ledger from Day 1 (not single-entry); explicit state machine for each transaction type; daily reconciliation jobs from MVP, not added later; integration tests covering return scenarios.
- **Contingency**: Manual reconciliation support during early operations; consider buy-vs-build for ledger (Fragment, Modern Treasury) before extensive custom work.

## AI-assisted productivity profile (overrides for fintech)

- **Card processing integrations** — substantial speedup (35%+); Stripe/Adyen SDKs are well-documented and AI-trained
- **KYC/AML rule engines** — modest speedup (15–20%); business logic is highly domain-specific and nuanced
- **Ledger / double-entry accounting code** — limited speedup (10–15%); correctness matters absolutely; AI tends to produce subtly wrong rounding/balancing logic
- **Compliance documentation** — meaningful speedup (25–35%); structured frameworks lend themselves to AI assistance, but legal review still required
- **Reconciliation logic** — limited speedup; this is where money is lost or made; over-review

## Anchor projects (typical scale calibration)

### Anchor: Consumer payments app MVP, 4-month delivery

- **Scope**: Mobile-first wallet with bank linking, P2P transfers, virtual debit card, basic KYC
- **Total feature hours**: ~1,400h
- **Total cost** (at $70/h blended): ~$160K
- **Timeline**: 4-week discovery + 3-month development
- **Notable cost drivers**: KYC integration, BaaS or sponsor bank work, mobile platform parity, AML monitoring foundation

### Anchor: B2B accounts payable / spend management, 6-month delivery

- **Scope**: Web platform, card issuing for employees, ACH/wire payouts, expense capture, accounting sync
- **Total feature hours**: ~2,500h
- **Total cost**: ~$300K–$400K
- **Timeline**: 6-week discovery + 5-month development
- **Notable cost drivers**: Card issuing program (Marqeta or Stripe Issuing), KYB for businesses, accounting system integrations (QuickBooks, Xero, NetSuite each is its own work)

### Anchor: Lending origination + servicing platform, 9-month delivery

- **Scope**: Application, automated decisioning, servicing, collections, regulatory reporting
- **Total feature hours**: ~3,500h
- **Total cost**: ~$450K–$650K
- **Timeline**: 8-week discovery + 7-month development
- **Notable cost drivers**: Decisioning engine, multi-state licensing logic, collections workflow, NMLS / state regulatory reporting

## Common pitfalls in pre-sales for fintech

- "We just process payments" — clarify whether this means accepting card payments (manageable with Stripe), money movement (requires sponsor bank or BaaS), or custody (requires money transmitter licensing)
- Clients confuse PCI-DSS levels — Level 1 is dramatically more expensive than SAQ-A scope; the architecture choice determines this
- "We need to support all 50 states" — for money movement, this is a 12–24 month licensing project, not an engineering problem
- Crypto adjacent products inherit regulatory uncertainty that doesn't exist in pure fintech — quote ranges should be wider
- Banking partners take 3–9 months to onboard; if not started early, project ships but can't go live

## Domain-specific Gate 0 checks

- [ ] Identify exact product type (payments / lending / investments / banking / insurance / crypto) — each has different regulatory implications
- [ ] Identify all jurisdictions (US states, EU countries, others) — multi-state US is a major cost
- [ ] Confirm whether funds are custodied or pass-through
- [ ] Identify sponsor bank or BaaS partner (or determine that one is needed)
- [ ] Identify KYC and AML vendor preferences or constraints
- [ ] Confirm PCI-DSS scope (SAQ-A via tokenization vs. higher levels)
- [ ] Identify reporting / regulatory filing requirements
- [ ] Confirm whether data residency requirements apply (EU GDPR, state-specific)
