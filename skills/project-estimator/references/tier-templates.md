# Tier Templates — Deliverable Format

The structure of the estimation deliverables the skill produces. These match a specific two-artifact delivery model optimized for pre-sales conversations across multiple domains. The `domains/examples/healthcare-mvp.md` file is the canonical reference showing the format in practice; consult it whenever you're unsure what a section should look like.

## Two-artifact delivery model

Every significant estimate produces **two artifacts**:

1. **Proposal (slides/doc)** — 5-slide client-facing narrative covering understanding, expectations/direction, assumptions/risks, approach/value proposition, phased investment.
2. **Estimation workbook (spreadsheet)** — sheets for summary, discovery & POC, features, assumptions, risks, and project schedule.

Small estimates (early-stage conversations, budget sizing) may deliver only the proposal. Every detailed estimate delivers both.

## Proposal structure (the 5-slide narrative)

The proposal leads with business value and the client's world, not the technology. Technical detail earns its place deep in the workbook, not on slide 1.

### Slide 1 — Our understanding of [CLIENT/PRODUCT]

A single-screen framing of the client's world, in their language. Six short paragraphs:

1. What the product is for, from the user's perspective (not the tech stack)
2. Why the chosen first market makes sense (market context)
3. What the first release should focus on — specific, visible use cases
4. Why that focus is right commercially (usefulness + credibility + validation)
5. The long-term vision and how the first release protects it
6. **Closing single sentence** that summarizes the thesis: "A focused first release backed by [people] can turn [product] from [current state] into [future state]."

Tone: understanding, not pitching. You're showing the client you've absorbed what they told you and reflected it back sharper than they said it.

### Slide 2 — Your expectations and the proposed MVP direction

Two bulleted columns or sections:

**Your expectations** (what they said they want):
- 5–6 bullets reflecting back the client's stated requirements in their words
- Dates, platforms, approach specifics

**Proposed MVP direction** (what we're recommending as the shape):
- 3–4 bullets on how we'd scope the first release to deliver on those expectations
- Specific scoping choices (disease-agnostic / disease-specific, module priority, etc.)

### Slide 3 — Key assumptions and risks to address early

Grouped into two blocks:

**Key assumptions** (5–8 items):
- Each is 1 short title + 2–3 sentences in client-readable language
- Focus on the commercially or technically significant ones — not everything goes here
- Include the fallback or adjustment path if the assumption fails

**Key risks** (4–6 items):
- Same format: short title + client-readable explanation
- Each includes the mitigation or fallback path — never name a risk without addressing how it's handled
- Risks on this slide are the ones the client needs to be aware of; the full risk register is deeper in the workbook

**Closing line**: "The key assumptions and risks are manageable, as long as they are addressed early and translated into clear product and delivery decisions."

### Slide 4 — Why this approach gives [CLIENT/PRODUCT] the strongest start

The value proposition. 5–7 items, each as a short title + one-line elaboration:

- **Phased approach** — commit one phase at a time, not full project upfront
- **Validated technology choices** — key uncertainties tested during discovery, not deferred
- **Investor-ready deliverables** (if relevant) — prototype, architecture, specs that support fundraising/TDD
- **Same team end-to-end** — design-and-plan team stays through delivery, reducing handover risk
- **Built for launch now and scale later** — foundation supports expansion
- **Fallback path protects momentum** — specific fallback named if a key assumption fails

These are differentiators vs. generic consultancy offers. Pick the ones that apply.

### Slide 5 — Recommended next step and phased investment

Present the phased path:

**Phase 1. [Usually Discovery & POC, sometimes POC alone]**
- 4–6 bullets on what this phase produces
- Timeline (typical: 2–4 weeks)
- Estimated cost: **$X,XXX – $X,XXX** (always a range, base + contingency per company default)
- Link to the estimation workbook for this phase

**Phase 2. [Development, usually]**
- 4 bullets on what this phase builds toward
- Timeline (typical: 2–3 months for an MVP)
- Estimated cost (ballpark): **$XX,XXX – $XX,XXX**
- Link to the estimation workbook for this phase

**Closing line**: "This phased approach keeps the first commitment focused while providing a clear path toward an early working product."

## Workbook structure (the estimation spreadsheet)

Six sheets. Each has a specific schema that must be matched exactly.

### Sheet: summary

Four blocks, each with an H1-style header row:

**Block 1: "Your expectations"** — 5–6 bullet rows reflecting client stated requirements.

**Block 2: "Key Assumptions"** — 5–8 rows, each with:
- Assumption title (column A, bold)
- Assumption text in client-readable language (column B, wrapped)

**Block 3: "Key risks"** — 4–6 rows, same structure as assumptions.

**Block 4: "Proposal value proposition"** — 4–7 rows, each:
- Title (column A, bold) — e.g., "Phased approach", "Validated technology choices"
- Elaboration (column B) — one to two sentences

### Sheet: discovery & POC

Table with exactly these columns:

| ID | Phase | Action | Owner | Priority | Deliverable | Why? |
|---|---|---|---|---|---|---|
| D01 | Discovery Week 1 | [Action title] | Solution Architect | Critical | [What the output is] | [Why this matters / when it happens] |

**Guidance:**
- IDs use `D##` format, ordered by the sequence of execution
- Phase column uses specific week labels: "Discovery Week 1", "Discovery Week 1-2", "Discovery Week 2", "Discovery Close"
- Owner names specific roles and sometimes specific people (e.g., "Solution Architect + [Clinical Lead]")
- Priority is one of: Critical / High / Medium / Low
- Deliverable is what will exist at the end — written for the client to understand, not for internal clarity
- "Why?" answers the client's implicit "why should I pay for this?" question

A typical discovery has 8–12 rows.

### Sheet: features

Table with columns specified by the project's domain. The default schema:

| ID | Module | Feature | Description | MVP Tier | User Type | Complexity | [Hour columns per domain] | Total (hours) | Priority (MoSCoW) | Notes |
|---|---|---|---|---|---|---|---|---|---|---|

**Hour columns vary by domain.** Read the **Recommended features sheet schema** section of the loaded domain reference file for the right columns. Common patterns:

- **Mobile-first SaaS (most healthcare, fintech consumer)**: Backend / Frontend (combined), Mobile, Total
- **Web-only platform**: Backend, Frontend, Total
- **AI/ML application**: Backend, Frontend, LLM/RAG Pipeline, Eval Infrastructure, Total
- **Game project**: Engineering—Engine, Engineering—Backend, Engineering—Tools, Content—Art, Content—Audio, Design, QA, Total
- **UAV system**: Firmware, On-board, Ground Control, Cloud, Mobile/Web UI, Total
- **Embedded/IoT product**: Firmware, Cloud, Mobile, Web Admin, Manufacturing/Test, Total

If working in generic mode (no domain reference loaded), default to: Backend, Frontend, Mobile (if applicable), Total.

**Column guidance:**

- **ID**: `F##` format, sequential
- **Module**: groups features. Domain-specific module taxonomies live in each domain reference file's **Feature taxonomy** section. For multi-domain projects, use modules from the dominant domain or create a custom taxonomy.
- **Feature**: short, specific name. "User Registration & Authentication", not "Auth".
- **Description**: 1–2 sentences describing the feature at a level of detail the client can evaluate. Include specifics (what's in, what's explicitly out).
- **MVP Tier**: one of: `MVP Core` / `MVP Extended` / `MVP Admin` / `MVP Infra`
  - MVP Core = primary user-facing features that define the product value
  - MVP Extended = features that extend core but aren't strictly required for initial validation
  - MVP Admin = admin / operator / internal tool features
  - MVP Infra = backend infrastructure, auth services, compliance layer, DevOps
- **User Type**: who uses this feature. Examples by domain: "Patient/Clinician/Admin" (healthcare), "Customer/Operator/Compliance" (fintech), "Player/Designer/LiveOps" (gaming), "Operator/Pilot/Analyst" (UAV), "End User/Installer/Fleet Manager" (IoT). Or "System" for infra.
- **Complexity**: `Low` / `Medium` / `High`. Calibrate against the domain reference's anchor projects.
- **Hour columns**: per the domain-specific schema above
- **Total (hours)**: sum of the hour columns
- **Priority (MoSCoW)**: `Must Have` / `Should Have` / `Could Have` / `Won't Have`. Must Have ≠ MVP Core; you can have a Should-Have feature within MVP Core that could slip to fast-follow if needed.
- **Notes**: technical implementation notes — what each engineering stream does. This column is where technical detail lives; it's readable by engineers but not primary content for the client.

**Totals row at bottom**: sum each hour column separately. Don't sum the Total column; show the hour streams separately, because the team composition is different for each.

### Sheet: assumptions

Table with exactly these columns:

| ID | Category | Assumption | Impact if Wrong (cost) | Verification Method | Verification Timing |
|---|---|---|---|---|---|

**Column guidance:**

- **ID**: `A##` format, sequential
- **Category**: groups assumptions. Typical categories: Platform, Data Integration, Scope, Architecture, Infrastructure, Language, AI/ML, Compliance, Clinician Review, Payments, Timeline, Team. Pick categories that match the project.
- **Assumption**: written in client-readable language, explaining what we're assuming and the fallback if it doesn't hold
- **Impact if Wrong (cost)**: numeric value in the estimate's currency. The number is the cost of being wrong — additional work needed, lost time, rework. Use 0 or leave blank only for confirmed items (no risk of being wrong).
- **Verification Method**: how we'll find out if the assumption holds. "Discovery Week 1: technical assessment..."
- **Verification Timing**: when verification happens. Typical values: "Discovery Week 1", "Discovery Week 2", "End of Discovery", "Confirmed" (if already verified)

A typical project has 10–15 assumption rows.

### Sheet: risks

Table with exactly these columns:

| ID | Category | Risk | Probability | Impact | Risk Score | Impact Description | Trigger / Early Warning | Mitigation Strategy | Contingency Plan |
|---|---|---|---|---|---|---|---|---|---|

**Column guidance:**

- **ID**: `R##` format
- **Category**: Regulatory, Technical, Data, Development, Timeline, Compliance, Organisational, Commercial, Operational
- **Risk**: short title followed by em-dash and explanation. Example: "Text recognition may not work reliably on Greek content — Most text recognition technology is optimised for English. Greek medication packaging and lab report formats need real-world testing."
- **Probability**: `Low` / `Medium` / `High`
- **Impact**: `Low` / `Medium` / `High` / `Critical`
- **Risk Score**: `Low` / `Moderate` / `Medium` / `High` / `Critical`. Rough product of probability × impact.
- **Impact Description**: quantified where possible. Hours or currency of rework, days/weeks of delay. Include reduction notes ("Reduced from High: MVP scope is predominantly standard patterns...") so the client sees your thinking.
- **Trigger / Early Warning**: what observable condition signals this risk is materializing. Critical for making the risk actionable rather than theoretical.
- **Mitigation Strategy**: what we do to reduce probability or impact. Specific actions, not platitudes.
- **Contingency Plan**: what we do if the risk happens despite mitigation. Specific fallback.

**If your company's context says AI-assisted delivery is standard, include this as a standard risk entry**: "AI-assisted development introduces code quality and security risks". See the `domains/examples/healthcare-mvp.md` file for the canonical wording and mitigation pattern. Openly naming the risk with concrete controls builds client trust; hiding it doesn't.

A typical project has 8–12 risks.

### Sheet: project schedule

Two sections, one per phase.

**Section 1: Discovery & POC**

Header row: role, total cost, total hours, man days, daily rate, hourly rate, then columns for each week (WK1, WK2, [WK3]).

Typical team composition for a 3-week discovery on a mid-complexity project:

| Role | Hours | Daily Rate | Cost |
|---|---|---|---|
| Project Manager | 40h | [rate from company-context.md] | [calculated] |
| Business Analyst | 40h | [rate] | [calculated] |
| Solution Architect | 40h | [rate] | [calculated] |
| UX/UI Designer | 40h | [rate] | [calculated] |

Show hours per week per role in a grid so the client sees the delivery shape, not just totals.

Totals row:
- TOTAL
- TOTAL (with contingency per company-context.md default)
- Timeline

**Section 2: Development phase**

Same structure. Team composition varies — a typical small-to-mid mobile project has:

| Role | Weekly load |
|---|---|
| Project Manager | 20h/week |
| Solution Architect | 20–40h/week (tapers) |
| Backend Developer | 40h/week during build |
| Mobile Developer | 40h/week during build, 20h final sprint |
| Frontend Developer | 10–20h/week (admin UI) |
| QA Engineer | 20h/week during build |
| UX/UI Designer | 5h ad-hoc |

Adjust based on project shape — more complex integrations need more backend and SA; pure mobile plays need more mobile dev; healthcare needs more QA.

Same totals + contingency pattern.

## Language and tone throughout

Read the example proposal text in `domains/examples/healthcare-mvp.md` to internalize the voice. Key patterns:

- **Direct address**: "Your team", "You (the clinical lead)", "Your patients"
- **Concrete over abstract**: "20+ real medication packages and 10+ lab reports" not "a representative sample"
- **Specific people named where relevant**: the named clinician, the named founder — these are real stakeholders the client knows
- **Business framing, not architecture framing**: "Medication data is the backbone of the treatment plan module" not "the data layer requires a reliable external source"
- **Always name the fallback**: every risk has a contingency; every assumption has an alternative; every hard part has a plan B
- **Qualitative adjectives are earned**: "tight but achievable" (because we say how we mitigate), "conservatively positioned" (because we list the specific conservative choices)
- **No marketing language**: no "cutting-edge", "best-in-class", "industry-leading". Specific capabilities and track record only.

## Tier → deliverable mapping

The tier system (A–E) drives how much analysis effort to invest. In terms of what actually gets produced:

| Tier | Proposal slides | Workbook sheets | Analysis effort |
|---|---|---|---|
| A | Brief proposal (3 slides) OR 1-page email | summary only (maybe features draft) | 2–4h |
| B | Full 5-slide proposal | summary + features + lightweight schedule | 4–8h |
| C | Full 5-slide proposal | All 6 sheets, streamlined | 1–2 days |
| D | Full 5-slide proposal + supporting architecture doc | All 6 sheets, comprehensive | 2–4 days |
| E | Proposal + architecture doc + SOW + TDD-ready spec | All 6 sheets + appendices | 5–10 days |

For most pre-sales conversations, **Tier B or Tier C is the target** — a full proposal + workbook covering the six sheets at appropriate depth. Tier D and E are reserved for large enterprise engagements or projects where the client has specifically requested deep analysis (e.g., as part of an RFP with scoring criteria).

Tier A (rough ballpark for internal use or very early client conversation) is common — clients often want a rough order of magnitude before committing to a full proposal conversation.
