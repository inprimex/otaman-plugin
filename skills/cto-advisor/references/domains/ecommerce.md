# E-commerce — Strategic Advisory Reference

## What's distinctive about advising in this domain

E-commerce CTO conversations are dominated by build-vs-buy decisions because the ecosystem is mature and well-componentized — almost every problem has a solid SaaS solution. The strategic question is rarely "can we build this" but "what's worth building vs. composing." Push back on engineering-led ambitions to build commerce infrastructure from scratch; the right answer is almost always to compose existing platforms (Shopify ecosystem, headless commerce backend, best-of-breed services) and concentrate engineering investment on what's actually differentiating.

## Vendor landscape

### Commerce platforms

- **Shopify (Basic / Advanced / Plus)**: Default for D2C, especially apparel, beauty, food. Plus tier handles enterprise.
- **Adobe Commerce / Magento**: Strong B2B; aging tech; expensive total cost.
- **BigCommerce**: Strong API; B2B and B2C; smaller ecosystem than Shopify.
- **WooCommerce**: WordPress-anchored; SMB; significant DevOps required for scale.
- **Headless commerce backends**: Commercetools (enterprise), Saleor (open-source / managed), Medusa (open-source), Shopify Hydrogen, Vendure
- **Marketplace platforms**: Mirakl, Sharetribe, custom Stripe Connect builds

### Search & discovery

- **Algolia**: Default for hosted; great DX; expensive at scale.
- **Typesense**: Open-source alternative; managed cloud option.
- **Elasticsearch / OpenSearch**: For self-hosted; significant ops burden.
- **Meilisearch**: Lighter-weight alternative; simpler use cases.
- **Bloomreach, Constructor**: Enterprise commerce-specific search with personalization.

### CMS (for content + commerce)

- **Contentful, Sanity, Storyblok**: Headless CMS for content alongside commerce
- **Builder.io**: Visual page-building; hybrid CMS
- **Native platform CMS**: Shopify's content tools, etc.

### Marketing & engagement

- **Email/SMS**: Klaviyo (default for D2C), Attentive (SMS strength), Postscript (Shopify SMS), Iterable (mid-market)
- **Loyalty**: LoyaltyLion, Smile.io, Yotpo Loyalty
- **Reviews**: Yotpo, Okendo, Stamped, Trustpilot
- **CDP**: Segment, Klaviyo CDP, Tealium, mParticle

### Order management & fulfillment

- **OMS**: NetSuite (enterprise), Shopify Plus OMS, Cin7, Brightpearl, Fishbowl, ShipHero
- **3PL connectors**: ShipBob, Flexport, ShipMonk, Stord
- **Shipping**: ShipStation, EasyPost, Shippo

## Hiring patterns

- **First hire profile**: Senior full-stack engineer comfortable with at least one commerce platform's quirks. Pure commerce-platform expertise (Shopify dev, Magento dev) is hireable but limits flexibility; prefer T-shaped engineers.
- **Common gaps**:
  - Performance / SEO engineer — page load and SEO directly drive revenue; specialized expertise pays for itself
  - Data engineer / analyst — commerce generates rich data that's underused without dedicated capability
  - Customer experience designer — UX directly impacts conversion in measurable ways
- **Specialist roles**: Merchandising tech (often product manager–merchandiser hybrid), conversion rate optimization, paid media tech (pixel implementation, attribution)
- **Outsourcing patterns**: Theme development frequently outsourced; one-off integration work often outsourced; performance work usually in-house once scale matters; data/analytics increasingly in-house.

## Common architectural debates

### "Stay on Shopify vs. go headless"

Default position for most: stay on Shopify. The platform is mature, the ecosystem is broad, and headless rarely pays off below significant scale or specific differentiation needs.

Flip when: SEO and performance requirements demand custom frontend; multi-brand or multi-region needs that Shopify doesn't handle elegantly; very high catalog or transaction volumes; B2B with complex pricing logic.

### "Build vs. buy specific features"

Almost always buy for: search, recommendations, reviews, loyalty, email, SMS, tax, shipping, fraud detection.

Build for: pricing/promotion engine if it's truly differentiated; checkout if you've identified specific UX wins; product configurator if your products have meaningful customization.

### "Native mobile app vs. PWA / responsive web"

Default position for most: skip native app, invest in mobile web performance. Native apps require ongoing maintenance, app store overhead, and rarely outperform a fast mobile site for transactional commerce.

Flip when: you have genuine app-only features (loyalty card, scan-and-go, enriched notifications, AR try-on); you have a brand strong enough that customers will install; B2B with employee usage where install friction is acceptable.

### "Real-time inventory vs. eventual consistency"

Default position: eventual consistency with safety stock buffers and oversell protection at checkout. Real-time inventory across channels is hard and rarely necessary.

Flip when: limited inventory items where overselling causes serious customer harm; live drops or scarcity-driven product strategies.

### "Marketplace platform vs. multi-vendor add-on to Shopify"

If marketplace is core to the business model, build on a marketplace platform (Sharetribe, Mirakl, custom) rather than retrofitting Shopify. Shopify Markets and multi-vendor apps work for tactical use cases but break down when marketplace dynamics dominate.

## Regulatory bottlenecks

- **Tax registration in new states**: 4–12 weeks per state once threshold triggered
- **EU VAT registration / OSS scheme**: 4–12 weeks
- **Age-restricted product compliance**: 6–12 weeks for full age-verification setup (alcohol, tobacco)
- **Marketplace seller onboarding (KYB) at scale**: per-seller days to weeks; aggregate timelines significant
- **Accessibility compliance retrofits**: 3–6 months for WCAG 2.1 AA on existing site

## Common pitfalls in advisory for e-commerce

- Building when buying serves better — engineering teams chronically over-estimate the cost of buying and under-estimate the cost of building
- Underestimating peak load — Black Friday / launch events at 50–100× normal traffic catch teams unprepared
- Conversion-rate decisions made without data — recommend hiring the analyst/CRO function before making major UX changes
- B2B and B2C in one platform — usually requires separate strategy; treat as two products
- Performance treated as engineering polish rather than revenue lever — page speed directly affects conversion
- International expansion underestimated — currency, language, tax, payment methods, fulfillment all multiply

## Escalation triggers specific to e-commerce

- PCI scope changes (introducing card vaulting, etc.) require security + compliance review
- Marketplace dynamics shifts (vendor takes, fee structures) require business + legal review
- Major channel additions (Amazon, retail wholesale) are GTM strategy, not engineering — escalate to CEO/COO
- Returns/exchange policy changes affect margin materially — escalate to CFO
- Fraud rate spikes outside normal bands require treasury + risk simultaneously
