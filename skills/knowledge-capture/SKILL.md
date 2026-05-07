---
name: knowledge-capture
description: "Extracts reusable knowledge (facts, decisions, metrics, learnings) from artifacts processed during any phase"
triggers:
  - "meeting notes"
  - "client email"
  - "RFP"
  - "call notes"
  - "retrospective"
  - "specification"
  - "requirements"
  - "vendor documentation"
---

# Knowledge Capture

When processing any external artifact (meeting notes, RFPs, client emails, specifications, call transcripts, vendor docs, retrospective data), actively scan for reusable knowledge items worth preserving.

## What to Capture

| Type | Description | Example |
|------|-------------|---------|
| **fact** | Verified information about a client, vendor, or technology | "Client uses Epic EHR v2023 with Interconnect API" |
| **metric** | Quantitative data with attribution | "Their platform handles 50K concurrent users" |
| **decision** | Approved choice with rationale | "Chose Pulumi over Terraform because team knows Python" |
| **estimation** | Actual vs estimated data | "FHIR integration: estimated 80h, actual 120h (+50%)" |
| **learning** | Lesson from experience | "Never estimate data migration under 2x initial guess" |
| **vendor-quirk** | Specific vendor/API behavior | "Stripe Connect onboarding takes 3-5 business days" |

## Confidence Classification

Only suggest saving items with clear confidence signals. Classify each:

### HIGH confidence — suggest saving

- Client explicitly confirmed ("Client confirmed that...", "Agreed: ...")
- Written in official/signed documents (RFP, SOW, technical spec)
- Actual vs estimated data (post-project metrics)
- Tested/experienced firsthand ("We integrated and found that...")
- Vendor documentation citations
- Post-mortem/retrospective consensus

### MEDIUM confidence — suggest with caveat

- Client mentioned but didn't confirm ("Client mentioned they might...")
- Numbers without clear source or attribution
- Assumptions that weren't explicitly validated
- Second-hand information ("Their dev team reportedly uses...")

### LOW confidence — do NOT suggest

- Brainstorming ideas that weren't decided
- Speculative estimates without validation
- Casual conversation without commitment
- "We might..." / "Maybe we should..."
- Opinions without data backing

**Default: only suggest HIGH confidence items.** If user asks for more, include MEDIUM with caveat markers.

## How to Present Suggestions

After processing an artifact for its primary purpose, if you identified capturable items, present them:

```
I found {N} items worth saving to the knowledge base:

1. [FACT] Client uses Epic EHR v2023 with Interconnect API
   Source: meeting notes, stated by client CTO
   Confidence: HIGH
   Destination: domain-knowledge

2. [METRIC] Their current system handles 10K req/min peak
   Source: technical requirements doc, section 3.2
   Confidence: HIGH
   Destination: project-knowledge

3. [VENDOR-QUIRK] eClinicalWorks API requires IP whitelisting, sandbox takes 2 weeks
   Source: vendor call with integration team
   Confidence: HIGH
   Destination: revlet.ai / domain-knowledge

Save all / Select individually / Skip?
```

## How to Save

**First, make this direct tool call** (one call, no subagent, no Grep/Read/Bash — `ToolSearch` is a built-in tool you invoke the same way as `Read`):
- Tool: `ToolSearch`
- `query`: `select:save_knowledge_item`
- `max_results`: `1`

Then use `save_knowledge_item` for each approved item:

```
save_knowledge_item(
  cwd=<current directory>,
  item_type="fact" | "metric" | "decision" | "estimation" | "learning" | "vendor-quirk",
  content=<the knowledge item text>,
  confidence="high" | "medium",
  source=<where it came from>,
  destination="project" | "benchmarks" | "component-library" | "domain-knowledge"
)
```

### Routing rules

| Item type | Typical destination |
|-----------|-------------------|
| fact (project-specific) | `project` — stays in `.otaman-presale/captured-knowledge.yaml` |
| fact (reusable) | `domain-knowledge` — goes to domain expert templates (future: revlet.ai) |
| metric (project-specific) | `project` |
| metric (reusable) | `benchmarks` — adjustment factors or patterns |
| decision | `project` — also may become an ADR in `.agents/decisions/` |
| estimation | `benchmarks` — patterns or adjustment factors |
| learning | `benchmarks` — common_underestimates or patterns |
| vendor-quirk | `domain-knowledge` — future: revlet.ai knowledge pack |

## When This Skill Activates

This skill runs passively during ANY phase. You don't need to be explicitly asked — whenever you process an artifact, scan for capturable items. But:

- **Don't interrupt the primary task** — finish the main work (estimation gate, discovery validation, etc.) first, then present knowledge suggestions at the end.
- **Don't over-capture** — 2-5 items per artifact is typical. More than 10 suggests you're capturing too much.
- **Don't capture obvious things** — only capture what would be non-obvious to a future SA working on a different project.
- **Ask before saving** — always present suggestions and wait for human approval.
