# E-commerce — Estimation Reference

## What's distinctive about this domain

E-commerce estimation is dominated by two factors most clients underestimate: peak-load handling (Black Friday traffic can be 50–100× normal) and the operations tail behind every customer-facing feature (an order isn't done at checkout — it has fulfillment, returns, exchanges, refunds, customer support cases, fraud review, accounting). The most common pre-sales failure is scoping the customer-facing storefront without scoping the order management, customer service, and warehouse/fulfillment back-office that makes the storefront actually work commercially.

## Compliance frameworks that may apply

| Framework | When it applies | Effort impact |
|---|---|---|
| PCI-DSS via SAQ-A | Card data tokenized via Stripe/Adyen/Shopify | minimal; baseline requirement |
| GDPR | EU customers | +10–15%; consent capture, data portability, right to erasure |
| CCPA / CPRA | California consumers | +5–10%; do not sell, opt-out flows |
| ADA / WCAG 2.1 AA | US public-facing commerce | +10–15%; lawsuit-bait if ignored; retrofit is more expensive than build-in |
| EU Accessibility Act (June 2025+) | EU public-facing commerce >10 employees | +10–15%; similar to WCAG enforcement |
| EU DSA / DMA | Large platforms in EU | +15–25%; transparency obligations, content moderation |
| Sales tax (US Wayfair) | Selling across state lines | minimal with Avalara/TaxJar/Stripe Tax; significant if rolling own |
| EU VAT (OSS / IOSS) | Selling cross-border in EU | +5–10%; OSS scheme is mandatory above thresholds |
| Age verification | Alcohol, tobacco, firearms, gambling | +20–40%; identity verification, geo-restrictions |
| Product safety (CPSC, REACH, etc.) | Specific product categories | varies; usually documentation overhead |

## Common integrations and effort patterns

| Integration class | Typical providers | Effort range | Notes |
|---|---|---|---|
| Payment processing | Stripe, Adyen, Braintree, Square, Shopify Payments | 30–80h | Multi-currency adds; Apple Pay / Google Pay add per platform |
| Buy-now-pay-later | Klarna, Afterpay, Affirm, Sezzle | 20–40h per provider | Each adds checkout flow variant |
| Tax calculation | Avalara, TaxJar, Stripe Tax, Vertex | 40–80h | Geographic complexity drives effort |
| Shipping rate / labels | EasyPost, Shippo, ShipStation, ShipBob, native UPS/FedEx/USPS | 60–120h | Multi-carrier shopping is more work than single |
| Order management (OMS) | Shopify Admin, NetSuite, Cin7, Fishbowl, Brightpearl | 100–300h | If not adopting an OMS, building one is 800h+ |
| Warehouse / 3PL integration | ShipBob, ShipHero, Flexport, custom WMS via EDI | 80–250h | EDI 850/856/810 set is its own discipline |
| Search & discovery | Algolia, Typesense, Elastic, Meilisearch | 80–200h | Faceting, synonyms, "did you mean" — depth varies wildly |
| Recommendations | Klaviyo native, Algolia Recommend, Bloomreach, custom ML | 40–250h | Off-the-shelf is fast; custom ML is its own project |
| Email / SMS marketing | Klaviyo, Attentive, Postscript, Mailchimp | 40–100h | Event-based triggering, segmentation, suppression list management |
| Reviews | Yotpo, Okendo, Trustpilot, Stamped | 20–40h | Display + collection flows |
| Loyalty / rewards | LoyaltyLion, Smile.io, Yotpo Loyalty, custom | 40–250h | Custom is expensive; off-the-shelf usually wins |
| CDN / image optimization | Cloudflare, Cloudinary, Imgix, native (Next.js Image) | 20–60h | Often the difference between 2s and 0.5s page loads |
| Analytics | GA4, Mixpanel, Amplitude, Heap, Segment as router | 20–80h | Cookie consent compliance adds work |
| Subscription management | Recharge, Bold Subscriptions, Stripe Billing, custom | 80–250h | If subscription is core, this can be the entire backend |
| Returns / exchanges | Loop Returns, Happy Returns, native | 40–150h | Often forgotten in initial scope; high-impact on UX |
| Fraud detection | Signifyd, Riskified, Stripe Radar, native rules | 40–120h | Chargeback liability shift services cost more but reduce ops burden |

## Feature taxonomy (typical modules)

- **Storefront** — browse, search, filter, product detail, reviews, recommendations
- **Cart & Checkout** — guest checkout, address book, payment, shipping selection, gift options
- **Account** — registration, login, order history, addresses, payment methods, preferences
- **Order Management** — order processing, fulfillment workflow, shipping confirmation, tracking
- **Returns & Exchanges** — return initiation, RMA, refund processing, restocking
- **Customer Service** — case management, order lookup, refund authorization, customer history
- **Catalog Management** — product creation, variants, pricing, inventory, media management
- **Inventory & Fulfillment** — stock levels, multi-location, allocation rules, low-stock alerts
- **Marketing & Promotions** — discounts, coupon codes, gift cards, email/SMS campaigns
- **Loyalty & Rewards** — points accrual, tier management, redemption
- **Reporting & Analytics** — sales, conversion, inventory, customer cohorts
- **Admin Dashboard / Back Office** — staff users, permissions, audit log, configuration

## Recommended features sheet schema

For most e-commerce projects:
- Backend (hours)
- Frontend (hours)
- Mobile (hours) — only if mobile is in scope (PWA usually replaces native today)
- **Total (hours)**

For headless commerce with significant integration work:
- Backend (hours)
- Frontend (hours)
- Integrations (hours) — broken out because integration work is often 30%+ of total
- **Total (hours)**

## Domain-specific risk register additions

### Risk: Peak-load capacity insufficient on launch event

- **Category**: Technical
- **Probability / Impact**: Medium / High
- **Description**: Major launches (Black Friday, product drops, marketing-driven traffic) generate 50–100× normal load. Sites that work fine in normal operation crash under peak, losing direct revenue and customer trust.
- **Mitigation**: Load testing during Discovery against realistic peak (not 2× normal); CDN-first architecture; queue-based order processing; database read replicas; explicit capacity planning per channel.
- **Contingency**: Throttling / queueing rather than crashing; communications plan if degraded; auto-scaling configured well above expected peak.

### Risk: OMS integration is more work than the storefront

- **Category**: Technical
- **Probability / Impact**: High / Medium
- **Description**: Clients fixate on the customer-facing site and underestimate the order management, fulfillment, and back-office integration. The OMS is often where 40–60% of the actual work lives.
- **Mitigation**: Discovery includes OMS scope explicitly; if no OMS exists, recommend buying one rather than building; integration scope documented sheet-by-sheet.
- **Contingency**: Phased delivery — manual order processing (with Shopify Admin or similar) for Phase 1, automated OMS integration for Phase 2.

### Risk: Tax calculation errors trigger audit and back-tax exposure

- **Category**: Compliance
- **Probability / Impact**: Low / High
- **Description**: Sales tax calculation across US states (post-Wayfair) and EU VAT is genuinely complex. Errors compound over months and surface in audits with penalties.
- **Mitigation**: Use a tax calculation service (Avalara, TaxJar, Stripe Tax) — never roll own; test against known transaction scenarios per jurisdiction; daily reconciliation reports.
- **Contingency**: Voluntary disclosure agreement if errors found; tax service vendor provides audit support per contract.

### Risk: Returns and exchanges are an afterthought, eroding margin

- **Category**: Operational
- **Probability / Impact**: High / Medium
- **Description**: Apparel returns rates run 20–40%; even non-apparel categories are 5–15%. Manual returns processing eats margin and creates customer service load that wasn't budgeted.
- **Mitigation**: Returns/exchanges scoped in MVP, not Phase 2; integration with returns service (Loop, Happy Returns) considered seriously; self-service returns from Day 1.
- **Contingency**: Spike in customer service hiring during ramp; tighten return policy with clear communication; partial restocking fees.

## AI-assisted productivity profile (overrides for e-commerce)

- **Storefront UI components** — substantial speedup (35%+); standard patterns are AI-trained extensively
- **Checkout flows** — meaningful speedup (25–30%); but every variation (BNPL, gift cards, subscriptions) needs review for edge cases
- **OMS / fulfillment business logic** — limited speedup (15–20%); domain-specific rules vary too much
- **Tax / shipping calculation logic** — modest speedup (15–20%); correctness matters absolutely; use vendor APIs
- **Search relevance tuning** — limited speedup; this is iterative experimentation, not greenfield code
- **Marketing event tracking / pixel implementation** — substantial speedup (40%+); patterns are well-known

## Anchor projects (typical scale calibration)

### Anchor: Shopify Plus build-out with custom features, 4-month delivery

- **Scope**: Custom theme + 5–10 custom apps (subscriptions, loyalty, custom fulfillment integration), 1 OMS integration
- **Total feature hours**: ~1,200h
- **Total cost** (at $70/h blended): ~$140K
- **Timeline**: 3-week discovery + 3-month development
- **Notable cost drivers**: Custom apps within Shopify ecosystem, theme development, third-party integrations

### Anchor: Headless commerce platform, 6-month delivery

- **Scope**: Next.js storefront + commerce backend (Commercetools, Saleor, or custom), full integration suite (search, CMS, CDP, OMS), B2B and B2C variants
- **Total feature hours**: ~2,800h
- **Total cost**: ~$320K–$420K
- **Timeline**: 6-week discovery + 5-month development
- **Notable cost drivers**: Headless integration architecture, multi-language/currency, CMS integration, performance engineering

### Anchor: Marketplace platform (multi-vendor), 9-month delivery

- **Scope**: Two-sided marketplace, vendor onboarding, split payments (Stripe Connect or similar), shared cart, dispute resolution
- **Total feature hours**: ~3,500h
- **Total cost**: ~$450K–$620K
- **Timeline**: 8-week discovery + 7-month development
- **Notable cost drivers**: Stripe Connect integration, vendor portal, transaction routing complexity, fraud across both sides

## Common pitfalls in pre-sales for e-commerce

- "Just like Amazon" — Amazon's catalog, search, and personalization represent thousands of person-years; clients quoting this benchmark need education
- "We'll add returns later" — returns are a tax on revenue if not built in; deferring them is more expensive than including them
- Underestimating internationalization — currency, language, tax, address formats, payment methods all multiply
- "We can use Shopify Basic" then needing features that require Plus or custom — pricing tier shifts mid-project are common
- Black Friday / launch performance not tested until launch week
- B2B and B2C in the same platform — these have different commerce requirements (POs, net terms, role-based pricing); treat as two products

## Domain-specific Gate 0 checks

- [ ] Confirm platform direction (Shopify ecosystem / Adobe Commerce / headless / custom)
- [ ] Identify all sales channels (web, mobile app, marketplaces like Amazon/Walmart, retail POS)
- [ ] Confirm geographic scope (countries, states, currencies, languages)
- [ ] Identify OMS / ERP / WMS integration requirements
- [ ] Confirm peak-load expectations (vs. baseline, with timing)
- [ ] Identify all third-party integrations (loyalty, reviews, marketing, BNPL, etc.)
- [ ] Confirm B2B vs B2C scope (or both)
- [ ] Identify subscription/recurring revenue scope (changes architecture significantly)
