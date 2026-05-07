# Constraint Patterns

When Gate 2 detects a budget, timeline, or open scenario, the approach to scoping changes. These patterns extend the deliverables described in `tier-templates.md`.

---

## Budget-constrained

**Detected from**: "What can we get for $X?", "we have a budget of Y", explicit budget cap in an RFP, "here's what we've allocated".

### Approach

Capacity math:

1. Budget ÷ blended rate (from company-context.md, or generic $70–130/h mid-market estimate) → raw hours
2. Productivity coefficient (0.70–0.80 for AI-assisted delivery teams, 0.60–0.70 for traditional)
3. Effective hours available
4. Allocate per Gate 3 capacity allocation guide
5. Map features to the capacity envelope
6. Build scope options

**Worked example at $100K budget with $70/h blended:**
- Raw hours: $100,000 ÷ $70/h = 1,429h
- Effective hours at 0.75 coefficient: ~1,070h
- Feature hours (at 60% of total): ~640h
- That's roughly 30–35 features at ~20h average

### Scope options (always present 3)

**Option A — Essential MVP at 90% of budget**
- Core features only; minimum viable compliance
- Single-environment deployment
- Remaining 10% held as discovery contingency

**Option B — Enhanced MVP at full budget** ← usually recommended
- Core + priority enhancements
- Full compliance posture
- Production-ready

**Option C — Phased approach with 60–70% of budget in Phase 1**
- Phase 1 delivers essential MVP at 60–70% of budget
- Phase 2 (separate SOW) delivers enhancements based on Phase 1 learnings
- Client retains optionality; risk-optimized for new relationships

### In the proposal (slide 5)

Present Phase 1 (Discovery & POC) + Phase 2 (Development) with the scope options reflected in Phase 2. Slide 2 "Proposed MVP direction" names the scope shape that fits the budget.

---

## Timeline-constrained

**Detected from**: "Can you deliver by [date]?", "we need this by Q3", "launch is in 10 weeks", external commitments (trade shows, funding milestones, regulatory deadlines).

### Approach

Backcast:

1. Target date
2. Required calendar time: today → delivery
3. Required velocity: effort ÷ calendar time
4. Team size at standard productivity
5. Feasibility verdict: realistic / aggressive / unrealistic

### Scenarios

**Standard team**
- Normal staffing
- May miss the client's target
- Use when: timeline is aspirational, not hard

**Accelerated**
- +30–50% people
- +15–25% scope cost (coordination overhead)
- +20–30% total cost
- 2–4 weeks faster
- Use when: timeline meaningful, not absolute

**Maximum**
- 2× people
- +30–40% scope cost
- +50–75% total cost
- ~40% faster, with diminishing returns past a point
- Use when: external immovable deadline, client can absorb cost

### MoSCoW in the features sheet

Use MoSCoW column (Must / Should / Could / Won't) aggressively when timeline-constrained. Must-haves define the deliverable; Should-haves can slip to fast-follow; Could-haves explicit deferred.

### Technical debt implications

Accelerated timelines create debt. Name it:
- Expected debt categories (test coverage gaps, shortcut patterns, deferred refactoring)
- Remediation cost as separate line item (15–25% of fast-track cost)
- Timeline for remediation (typically 3–6 month Phase 2)

Clients who aren't prepared to carry debt shouldn't choose the accelerated/maximum scenarios. Naming this prevents resentment later.

### Recommended handling pattern

When presenting a timeline-constrained estimate:
- Name the timeline risk openly (e.g., "aggressive but achievable")
- Mitigate with scope discipline (hard-freeze scope after discovery, build highest-priority module first)
- Include a 1–2 week buffer in the schedule
- Offer phased fallback: if timeline slips, deliver the highest-priority module on schedule and follow-up modules shortly after
- Preferred: phased scope reduction fallback, NOT quality reduction

See `domains/examples/healthcare-mvp.md` for how this pattern is applied in the Risk R08 "aggressive timeline" entry.

---

## Open (no constraints)

**Detected from**: "What do you recommend?", "give us your thoughts", "how would you approach this?", no explicit budget or timeline signals.

### Three scenarios

**Scenario A — Optimal Quality** ← usually recommended
- Right-sized team, realistic timeline
- Full quality posture
- Adequate buffer for discovery and learning

**Scenario B — Faster Delivery**
- −25–35% time vs. A
- +15–25% cost (larger team, more coordination)
- Technical debt implications named

**Scenario C — Budget-Conscious**
- +25–35% time vs. A
- −15–25% cost (smaller team, more sequential)
- Reduced initial feature set, roadmap to parity

### Explicit recommendation

Pick one. State which. Explain why. Clients paying for pre-sales solution architecture are paying for judgment.

If specific project characteristics change the recommendation (regulatory deadline, competitive dynamics, client cash position), acknowledge in rationale.

---

## When no constraint is evident but the project is large

For projects above $300K or 7 months, default to presenting Optimal / Faster / Budget-Conscious scenarios even if the client framed the request openly. The client deserves to see the space of viable approaches.

For projects below that scale, a single recommended estimate is usually enough unless the client asks for options.
