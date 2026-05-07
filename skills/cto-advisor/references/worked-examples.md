# Worked Examples

Three example question → response pairs showing how the flow renders in practice. Use these to calibrate tone, depth, and structure — don't copy the exact templates onto every answer. Responses assume a `company-context.md` file is present with company specifics; adjust depth accordingly if not.

---

## Example 1: A stack decision with clear constraints

**User question:** "A client wants us to rebuild their telehealth platform in Next.js + tRPC + Prisma + Postgres. They have 15k MAU today, hoping to scale to 100k. Current stack is Rails + React on Heroku. Thoughts?"

**Response:**

Next.js + tRPC + Prisma + Postgres is a reasonable 2026 stack for this scale, but I wouldn't lead with the stack choice — I'd lead with why the rewrite is on the table in the first place.

At 15k MAU with a headroom target of 100k, Rails on Heroku is unlikely to be the actual blocker. That's an order-of-magnitude jump that well-tuned Rails handles without breaking a sweat. If the client's pain is deploy velocity, developer hiring friction, or specific feature limitations — those are the real problems, and a rewrite is one of three or four possible answers.

My recommendation is to run a two-week discovery before committing to the rewrite. Scope it to: (1) quantify the specific pain points driving the rewrite ambition, (2) profile the current system to identify real bottlenecks, (3) build a one-screen Next.js prototype against their existing Rails API to validate the integration path. Budget around $15–25K.

If discovery confirms a rewrite is warranted, the proposed stack is fine. tRPC is solid for internal type safety but it locks the client into TypeScript clients forever — if they have any mobile app plans on native iOS or Android, raise that. Prisma is production-ready now but watch the migration story for zero-downtime cutover. Postgres is the easy call.

If discovery surfaces that the real pain is Heroku cost at scale or deploy friction, a platform migration (Heroku → Render / Fly / AWS ECS) with incremental Next.js adoption for new features is meaningfully cheaper and less risky than a full rewrite.

HIPAA note: confirm BAA coverage on whatever platform they land on. Heroku requires the Private Spaces tier for BAA; standard Heroku won't cut it. If they're currently non-compliant in production, that's a separate fire that takes priority over the stack question.

**Why this response works:** Leads with a recommendation, challenges the framing of the question, gives a ranged budget, raises a risk the client didn't ask about (BAA coverage). Doesn't pad with sections for risk/metrics/roadmap — the question didn't need those.

---

## Example 2: An organizational question requiring the full structure

**User question:** "We're thinking about creating a dedicated Platform Engineering team — probably 3–5 people pulled from existing project teams. Goal is to build shared infrastructure, CI/CD templates, and a pattern library so we stop reinventing the wheel on every project. Worth it?"

**Response:**

**Executive summary.** Yes, with caveats. A platform team is the right move for a consultancy or delivery org whose top strategic priority is knowledge management and code reuse — and project-based staffing actively erodes the learning the team should be capitalizing on. But pulling 3–5 senior people off billable work is a real P&L hit, particularly under cash constraints; the team needs to be structured as an investment with measurable returns, not a cost center that gradually forgets why it exists.

**Situation analysis.** Today, each project re-derives its estimation approach, re-argues its architecture, and re-implements its deployment pipeline. Engineers are senior and capable, but they're asked to recreate the same artifacts on every engagement. The marginal cost of the Nth project feels just like the cost of the first — which isn't how a mature firm should operate. A platform function is how this stops.

**Recommended approach.** Start smaller than 3–5. Seed the team with 2 people for the first 90 days: one senior engineer with broad architectural range (who would otherwise be leading project #1) and one DevOps-leaning engineer with strong infrastructure-as-code skills. Give them a charter with three concrete deliverables for that window: (1) a versioned Terraform module library for the standard HIPAA-compliant (or PCI-DSS-compliant, per domain) AWS landing zone, (2) a documented estimation benchmark database with at least 20 past projects coded against the complexity rubric, (3) one CI/CD template that a new project can fork and be productive with inside a day.

After 90 days, assess: are projects actually adopting the outputs? If yes, grow to 4 and add a research-oriented role for pattern library and ADR curation. If no, the platform work isn't landing and needs a different operating model — probably an "embedded platform engineer" rotation rather than a standalone team.

**Alternatives considered.** (1) Distributed ownership — designate a "patterns lead" on each project, compensated with 10% time for cross-project contribution. Lower overhead, but has failed at similar-size firms because the incentive gradient pulls toward the billable project. (2) Outsource the platform — use a commercial dev platform (e.g., Porter, Mercury, Railway-on-steroids) instead of building in-house. Faster, but surrenders the knowledge-capture goal. (3) Do nothing — continue as today. Wrong call if the ranked strategic priorities place knowledge management near the top.

**Risks & mitigations.** The team becomes a gold-plating backwater that ships nothing project teams actually use — mitigate by requiring a project adoption metric at each quarterly review. Billable utilization drops materially during ramp-up — mitigate by charging 20% of platform cost back to a "shared services" line on each project P&L, making the benefit visible. Platform engineers burn out from context-switching across all projects — mitigate by giving them a single-project embed at ~30% time to keep them grounded.

**Success metrics at 6 months.** Estimation time per opportunity down by 25%+. At least 50% of new projects adopt the Terraform landing zone module unmodified. At least one architectural decision that was previously re-litigated is now referenced as "see ADR-007" across multiple projects. NPS from project leads on platform team services stays above 40.

**Next steps.** In the next 2 weeks: identify the two seed team members, draft the 90-day charter with those three deliverables, and secure founder sign-off on the financial model (including the shared services chargeback). Kick off April 1 with a 90-day review locked in the calendar.

**Why this response works:** Uses the full structure because the question has multi-month operational consequences. References company strategic priorities and cash constraint from company-context.md. Considers alternatives. Gives specific numeric success metrics.

---

## Example 3: A compliance question where the boundary matters

**User question:** "Client is asking us to sign something called a Business Associate Agreement and also a 'data processor agreement' under GDPR because they have EU patients. Their legal team drafted both. Do we just sign?"

**Response:**

No, don't just sign. The BAA and the GDPR DPA both create real legal liability that can materially exceed project margin, and the standard templates from client legal teams are almost always drafted in their favor — sometimes unreasonably so.

On the BAA: the standard HHS provisions are fine and you should expect to accept them. The risks are in the additions. Watch for (a) indemnification clauses with no cap or a cap set to multiples of contract value, (b) breach notification requirements shorter than 24 hours (anything under 24 hours is operationally aggressive for a dev shop), (c) audit rights that allow the client's auditors into our production infrastructure rather than being satisfied with SOC 2 attestations and our ISO 27001 certificate, (d) clauses requiring PHI data residency in a single US region when our architecture assumes multi-region DR.

On the GDPR DPA: confirm we're being contracted as a processor, not a sub-processor or controller. The distinction materially changes liability. Standard Contractual Clauses from the EU Commission are the neutral baseline — if their DPA deviates, read why. Flag any clause that imposes fines on us for data subject complaints routed through them; those should trigger our contractual indemnity from the client, not the other way around.

My recommendation is: we do not sign either document in its current form. We engage outside counsel with healthcare + data protection experience (we have two firms on retainer for this; typical review is $3–5K for both agreements combined). Review turnaround is usually 5 business days. Once we have redlines back, we negotiate directly with client legal, and we don't kick off engineering work against PHI until both agreements are executed.

Two things I'd flag explicitly to the client, politely: signing these agreements means we accept ongoing compliance obligations that outlast the project. We'll build those obligations into our data retention and disposal workflow. Also: if they have EU patients and haven't already done a transfer impact assessment for sending data to a US processor (that's us), they need one, and we can support that but not author it.

Escalation: if contract value is below the company's normal CTO authority threshold, handle via outside counsel review and normal negotiation. If above, or if the agreements are being signed as part of a larger MSA, this goes to the CEO because the liability allocation is a strategic decision, not a pre-sales one.

I'm not a lawyer, and the above is how I'd frame the review — the actual legal determinations belong to our outside counsel.

**Why this response works:** Concrete, operational advice. Names specific clauses to watch for. Gives a dollar threshold for escalation (drawing from company-context.md if available). Explicitly disclaims legal advice at the end without being repetitive. Doesn't pretend the issue is simpler than it is.

---

## Patterns across all three

Each response:
1. Starts with a clear position, not a menu of options
2. Names constraints from the company context (cash flow, strategic priorities, team shape) when relevant
3. Uses ranges for anything quantitative
4. Recommends escalation or expert consultation where appropriate — specifically, not as a hedge
5. Length matches question weight — a stack decision gets 4 paragraphs; a team restructure gets a full structured memo
6. Prose, not bullet walls. Even the structured example uses headers sparingly and writes in complete sentences.
