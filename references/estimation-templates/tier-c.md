# Tier C — Standard Estimation Template (10-15 pages)

**Methods**: Parametric (decompose into countable units) or Capacity-Based (budget ÷ rate => scope options).
**Accuracy**: ±25-30%

## Sections

1. **Executive Summary** (1 page)
2. **Project Understanding** (1-2 pages) — business context, personas, success criteria
3. **Requirements Analysis** (2-3 pages) — functional by domain with complexity ratings, NFRs with measurable criteria, 3-5 architecturally significant requirements
4. **Architecture Recommendation** (2-3 pages) — Mermaid diagram, tech stack with rationale, integration approach, infrastructure overview
5. **Effort Estimation** (3-4 pages) — methodology explanation, feature-by-feature breakdown, phase breakdown with milestones, team composition, min-max range
6. **Risk Assessment** (2 pages) — top 5-7 risks with quantified impact, mitigation, contingency 20-30%
7. **Options Comparison** (1-2 pages, if applicable) — MVP vs full, build vs buy, phased vs big-bang
8. **Investment Summary** (1 page) — total range, payment milestones
9. **Next Steps** (1 page)

### Parametric Method

Decompose into countable units: stories, endpoints, entities, screens. Classify by complexity. Apply effort benchmarks from `component-library.yaml`:
- Low: 8-16h
- Medium: 16-40h
- High: 40-80h
Sum + project-level adjustments.

### Capacity-Based Method

Budget ÷ blended rate => total hours => productivity coefficient (0.65-0.70) => allocate:
- Feature development: 50-60%
- Testing: 15-20%
- Infrastructure & DevOps: 10-15%
- Project management: 5-10%
- Buffer: 10-15%
