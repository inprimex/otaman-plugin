# Fintech — Strategic Advisory Reference

## What's distinctive about advising in this domain

Fintech CTO conversations live at the intersection of regulatory strategy, banking partnerships, and engineering correctness in ways no other domain combines. The most common framing to push back on is "we're a tech company that does finance" — for any product moving money, custody, or extending credit, you're a financial company that uses tech, which has profound implications for licensing, risk, hiring, and operating model. Decisions about sponsor banks and BaaS partners shape architecture for years.

## Vendor landscape

### Banking-as-a-Service (BaaS)

- **Treasury Prime**: API-first, multi-bank model (good for sponsor bank diversification). Mid-market focus.
- **Unit**: Strong product, well-funded, broad capability. Common neobank infrastructure.
- **Synctera**: Card-issuing strength; programmatic BaaS.
- **Synapse**: **Avoid** — collapsed in 2024 leaving downstream neobanks with reconciliation crises. Cautionary tale for sponsor diversification.
- **Direct sponsor bank partnerships**: Column, Lead Bank, Stearns Bank, Sutton Bank, Pacific West Bank — for clients with scale and willingness to manage relationships directly.

### Payment processing

- **Stripe**: Default for online card processing; broadest geographic and feature coverage.
- **Adyen**: Enterprise-grade, often better for omnichannel and high-volume merchants.
- **Braintree** (PayPal): Good if PayPal acceptance is meaningful.
- **Checkout.com**: International strength; growing presence.
- **Square**: For commerce that includes physical POS.

### KYC/AML

- **Persona**: Most flexible for custom flows; good developer experience.
- **Onfido**: Strong document + biometric; widely used in EU.
- **Alloy**: Identity decisioning across multiple data providers.
- **Sumsub**: International coverage strong.
- **ComplyAdvantage / Sardine**: Transaction monitoring and fraud focus.

### Card issuing

- **Marqeta**: Most established; good for complex programs.
- **Stripe Issuing**: Faster start for Stripe customers; capability gap for sophisticated card programs.
- **Lithic**: Developer-focused; growing capability.

### Ledger / accounting infrastructure

- **Modern Treasury**: Treasury operations + ledger; strong for fintech infrastructure.
- **Fragment**: Purpose-built immutable ledger; growing adoption.
- **Custom double-entry**: Don't build unless you have specific reasons; the "build a ledger" conversation usually loses.

## Hiring patterns

- **First hire profile**: Senior backend engineer with prior money-movement experience strongly preferred. Familiarity with double-entry accounting, idempotency patterns, and reconciliation is non-negotiable for the senior who anchors money-movement work.
- **Common gaps**:
  - **Compliance / BSA Officer** — usually first dedicated hire after engineering in money transmission businesses
  - **Risk / Fraud Analyst** — humans-in-the-loop on rule tuning and case review; first analyst usually hired alongside MVP launch
  - **Bank Relations Manager** — for businesses with sponsor bank relationships, this role is critical and underestimated
- **Specialist roles**: Treasury operations (reconciliation), regulatory affairs, AML investigators, card program manager (if issuing)
- **Outsourcing patterns**: Customer support frequently outsourced (with PII access controls); KYC operations often outsourced via vendor; treasury operations always in-house at scale; engineering core systems should be in-house.

## Common architectural debates

### "BaaS partner vs. direct sponsor bank relationship"

Default position for early-stage: BaaS partner. Direct sponsor bank relationships require regulatory expertise, capital, and operational maturity that early-stage companies don't have.

Flip when: scaled enough that BaaS per-transaction or fixed fees exceed direct relationship costs (typically >$5M ARR for money-movement businesses); product requires bank capabilities BaaS doesn't expose; multiple sponsor banks needed for risk diversification.

The Synapse 2024 collapse changed this conversation — even when picking BaaS, multi-sponsor architecture from the start is now standard advice.

### "Build our own ledger vs. use one"

Default position: don't build. Use Modern Treasury, Fragment, or your BaaS provider's ledger. The "build a ledger" path looks tractable and turns into a multi-year correctness nightmare.

Flip when: regulatory requirements force specific implementation; existing offerings can't model your transaction types; you have deep accounting expertise on the team and a multi-year horizon to invest.

### "Stripe Connect vs. custom marketplace payment routing"

Default position: Stripe Connect (or equivalent from Adyen, Braintree). Multi-party payment routing has significant compliance overhead.

Flip when: international complexity Stripe Connect doesn't handle; volume large enough that platform fees justify build cost; specific payment flows not supported.

### "PostgreSQL vs. specialized financial database"

Default position: PostgreSQL with rigorous transactional patterns. Use Postgres for ledger, customer data, transactions. Add Kafka/Kinesis for event streaming if needed. Specialized "financial databases" are usually unnecessary complexity.

### "When to pursue our own money transmitter licenses"

Money transmitter licensing across US states is typically 18–36 months and several million dollars. Default position: defer as long as possible by riding sponsor bank rails; pursue when scale justifies cost and you've validated the business model.

## Regulatory bottlenecks

- **Sponsor bank onboarding**: 3–9 months typical; longer if novel product
- **BSA/AML program build-out**: 6–12 months for adequate maturity
- **State money transmitter licensing**: 18–36 months for US-wide coverage
- **PCI-DSS Level 1 audit**: 6–12 months from start of remediation
- **SOC 2 Type II**: 6 months observation period after controls implemented
- **EU PSD2 / Open Banking authorization**: 6–18 months depending on member state

## Common pitfalls in advisory for fintech

- Underestimating the "second business" you're building — every fintech is also building a compliance and operations business that's larger than the engineering organization at scale
- Treating regulatory frameworks as one-time work — they require continuous program management
- Recommending speed when correctness should dominate — money bugs are real losses, not bugs
- Assuming neobank model is the goal — many fintech businesses (B2B SaaS for finance, vertical fintech, embedded finance) don't need full banking infrastructure
- Underestimating customer support requirements — financial customers have higher expectations and more regulated dispute processes
- Crypto / fiat overlap creates compliance complexity often underestimated

## Escalation triggers specific to fintech

- Any product change affecting funds custody requires legal + compliance review before engineering
- New jurisdictions require regulatory analysis before commitment
- Sponsor bank or BaaS provider changes are CEO-level decisions
- AML alert volumes outside expected ranges require Compliance Officer immediate involvement
- Customer-impacting reconciliation errors require treasury + legal + product simultaneous response
- Regulator inquiry of any kind requires immediate counsel involvement
