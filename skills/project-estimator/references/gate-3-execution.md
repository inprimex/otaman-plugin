# Gate 3 — Estimation Execution & Delivery

## Purpose

Produce the estimation deliverables using the approved tier and method. This is where the analysis becomes the proposal + workbook that the client actually sees. The failure mode this gate prevents is drift — producing a document that doesn't match the methodology approved in Gate 2, or delivering in a generic format instead of the structured two-artifact shape.

## Trigger

User approves tier and method from Gate 2.

## Task

Produce the two-artifact deliverable (proposal + workbook) per the templates in `tier-templates.md` and the canonical example in `domains/examples/healthcare-mvp.md`. For smaller tiers, subset of that format. Generate the assumption register, risk register, and project schedule using the specific column schemas defined in `tier-templates.md`.

## Reading your company's calibration

Before executing, read from `references/company-context.md` if it exists:

- **Rate card** — role-level daily and hourly rates; blended rate for capacity math
- **Contingency default** — typically +10% or +15%; whatever the company's standard is
- **Reality-check ranges** — the cost-to-scale mapping specific to your economics
- **AI-assisted delivery stance** — whether AI tools are baked into the estimate, and whether the R06 risk entry applies
- **Capacity allocation percentages** — how hours split across feature dev / testing / infra / PM / SA / buffer
- **Currency** — primary currency and handling for secondary

If `company-context.md` doesn't exist, use the generic fallback values listed below and flag the assumption to the user.

## Reading domain context

Also load any domain reference files identified in Gate 0 (`references/domains/<domain>.md`). These provide:

- Domain-specific integration effort benchmarks (use these instead of the generic per-feature benchmarks below where they apply)
- Recommended features sheet schema (which hour columns to use)
- Domain-specific risk register entries to add to the standard set
- AI-assisted productivity overrides for this domain
- Anchor projects to compare your estimate against

For multi-domain projects, load all relevant domain files and synthesize. When domain-specific risks overlap, deduplicate; when they're complementary, include both.

## Execution principles

**Every architectural decision traces to a requirement.** If you can't trace it, it's either unnecessary or the requirement is missing.

**Ranges with contingency built in.** Cost ranges use base + contingency pattern (e.g., "$11,400 – $12,540" for +10% contingency). Timeline ranges as appropriate.

**Visible assumptions with quantified impact.** Every assumption in the register has a quantified "Impact if Wrong" number in currency. This is the cost of being wrong, not a guess — it's what it would take to recover if the assumption fails.

**Quantified risks with full lifecycle.** Each risk has probability, impact, risk score, quantified impact description, trigger/early warning, mitigation, and contingency plan. All six fields populated.

**Business language in client-facing artifacts.** Technical detail lives in the Notes column of the features sheet, not in the descriptions. Descriptions are written for a business reader.

**AI-assisted delivery calibration (if applicable).** If company-context.md says AI tooling is standard, the numbers reflect AI-assisted velocity, and include the R06 risk entry acknowledging AI-assisted delivery with specific mitigations.

## Generic fallback reality-check ranges

Use these **only if company-context.md doesn't specify** and flag that you're using generic assumptions. These are rough industry-mid-market estimates; your actual economics may differ significantly.

| Scale | Timeline | Generic cost range | Feature hours |
|---|---|---|---|
| Discovery only | 2–4 weeks | $8K–$25K | (analysis) |
| Extra Small | 1–2 months | $20K–$60K | 200–400h |
| Small | 2–4 months | $50K–$150K | 400–900h |
| Medium | 4–7 months | $120K–$350K | 800–2,000h |
| Large | 7–12 months | $300K–$800K | 2,000–4,500h |
| Very Large | 12+ months | $700K+ | 4,500h+ |

These ranges assume blended rates in the $70–130/h range. If company-context.md specifies different economics, use those.

## Feature-hour benchmarks (generic)

These are generic benchmarks for typical feature types when no specific domain reference is loaded. **Domain reference files contain more specific benchmarks (e.g., EHR integration, payment processor integration, OTA infrastructure). Use those when applicable.**

- **Simple CRUD / list views / forms**: 10–20h
- **Standard auth (registration, login, profile)**: 15–25h
- **Standard integration (Stripe, Twilio, SendGrid)**: 15–25h per integration
- **Custom business logic with UI**: 20–30h
- **OCR / ML integration with custom flow**: 40–55h
- **External database integration**: 30–50h
- **Admin dashboard (read-heavy, standard framework)**: 12–25h per major view
- **Infrastructure baseline (auth, API gateway, CI/CD, compliance layer)**: 50–80h total

If a feature estimate lands far outside these bands, check your complexity rating and whether the feature scope is broader than it appears. For domain-specific work (EHR integration, RAG pipeline, netcode, autopilot interfaces), defer to the loaded domain reference's benchmarks.

## Contingency

**Default**: use the contingency rate from company-context.md. If not specified, use **+10%** — tighter contingencies are increasingly common where AI-assisted delivery is standard; wider contingencies (+20–30%) were more typical in 2022 and earlier.

Use higher contingency (+15–20%) only when:
- Critical integration with an unfamiliar external system
- Regulatory path is unclear and may require rework
- Client team has significant dependency on specific individuals
- Novel technology (PoC-grade) not previously exercised

When you deviate from the default, document why.

## Capacity math (for capacity-based projects)

When the client leads with a budget, the math:

1. Budget ÷ blended rate → raw hours
2. Apply productivity coefficient (0.65–0.80 depending on company's AI-assisted delivery stance — higher for AI-integrated teams, lower for traditional)
3. Allocate across categories using the capacity allocation percentages from company-context.md (or generic defaults below)

### Generic capacity allocation fallback

Use only if company-context.md doesn't specify:

| Category | % of hours |
|---|---|
| Feature development | 55–65% |
| Testing | 15–20% |
| Infrastructure & DevOps | 8–12% |
| Project management | 8–10% |
| Solution architecture / tech leadership | 10–15% |
| Buffer | 5–10% |

PM and SA run concurrent with development, so the percentages above don't necessarily sum to 100% — they overlap in the project schedule.

## Architecture diagrams

Use Mermaid for diagrams. Keep them simple — 6–12 boxes max for a main architecture diagram. `flowchart TD` for most architectures, `sequenceDiagram` for specific integration flows, `erDiagram` for data models.

Architecture detail doesn't appear in the proposal slides (slide 4 names the validated technology choices at a high level; specifics live in the workbook and a separate architecture doc for Tier D+).

## Output hygiene — the client-facing deliverables

### Proposal (slides or doc)

- Client's world first, our approach second
- Specific names and dates, not generic placeholders
- Every risk paired with its mitigation/fallback
- Phase cost ranges with contingency shown (e.g., "$11,400 – $12,540")
- No internal labels (tier names, gate references, complexity scores, etc.)
- No marketing language

### Workbook (spreadsheet)

Six sheets per `tier-templates.md`:
1. summary (four blocks: expectations / assumptions / risks / value proposition)
2. discovery & POC (ID, Phase, Action, Owner, Priority, Deliverable, Why?)
3. features (ID, Module, Feature, Description, MVP Tier, User Type, Complexity, BE/FE hours, Mobile hours, Total hours, MoSCoW, Notes)
4. assumptions (ID, Category, Assumption, Impact if Wrong, Verification Method, Verification Timing)
5. risks (ID, Category, Risk, Probability, Impact, Risk Score, Impact Description, Trigger/Early Warning, Mitigation, Contingency Plan)
6. project schedule (role × week grid with totals + contingency)

For smaller tiers, subset of sheets is appropriate — see the tier-to-deliverable mapping in `tier-templates.md`.

### File formats

When generating deliverables:
- **Proposal**: markdown for most cases (client can see structure; easy to paste into slides). Generate .pptx only if user explicitly requests.
- **Workbook**: .xlsx. Use the xlsx skill for production. Columns must match the schemas in `tier-templates.md` exactly.

## Conversational presentation vs. produced artifacts

Two different modes:

**When working with the user (internal, pre-delivery)**: produce the analysis in the chat using tables and prose. Show your reasoning.

**When producing the client-facing artifact**: call the xlsx skill to generate the workbook; produce proposal text in markdown format.

The user will typically ask for one of three things at this stage:
- "Show me what the estimate looks like" → analysis in chat, full tables, recommendation
- "Generate the workbook" → produce the xlsx file
- "Draft the proposal" → produce the proposal markdown

Don't jump to file generation until the user confirms the analysis is ready. The pre-sales process is iterative — expect refinement rounds.

## Gate 3 closing output

After producing the analysis (and artifacts if requested), present a summary:

**Title:** Estimation Ready — [Project Name]

**Quick review:**
- Total investment range: $X–$Y (with +X% contingency)
- Timeline: X weeks/months
- Confidence: ±X%
- Top risk in one sentence

**Before we finalize:**
1. Does the scope capture match your understanding?
2. Any features you'd add, remove, or re-scope?
3. Ready to generate the workbook and proposal files, or further iteration needed?

**Project reference code:** [CODE per the format in SKILL.md]

Wait for user response. The user may:
- **Approve** → generate artifacts, record reference code
- **Request adjustments** → iterate on specific sheets / sections
- **Ask for additional scenarios** → generate them
- **Flag misunderstandings** → correct and regenerate affected sections
