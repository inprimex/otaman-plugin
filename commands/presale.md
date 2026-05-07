---
name: presale
description: "Start a pre-sale estimation workflow — scaffolds .otaman-presale/, loads domain expert, launches SA agent"
model: opus
effort: xhigh
arguments:
  - name: artifacts
    description: "Path to client artifacts (meeting notes, RFP, etc.) or describe the project"
    required: false
---

# /otaman:presale

Start a pre-sale estimation workflow for a new project opportunity.

## Steps

### Step 0: Check for existing presale

Check if `.otaman-presale/project-meta.yaml` exists in the current directory or parent directories.

- If it exists: read it, show the current state (project code, domain, phase, prior gates completed). Ask the user if they want to continue the existing estimation or start fresh.
- If it doesn't exist: proceed to Step 1.

### Step 1: Gather project basics

Use the AskUserQuestion tool to collect:

1. **Project name**: Human-readable name for this opportunity
2. **Client name**: Who is the client (optional)
3. **Domain**: One of: healthcare, fintech, marketplace, ml-ai, saas, ecommerce, iot, general
4. **Artifacts**: Does the user have files to analyze? (meeting notes, RFP, feature list, email, etc.)

If the user provided `<artifacts>` argument, note the path for the SA agent to read.

### Step 2: Initialize presale directory

Run the init-presale script:
```bash
py "${CLAUDE_PLUGIN_ROOT}/scripts/init-presale.py" "<PROJECT-CODE>" "<project-name>" "<domain>" --client "<client>"
```

Generate the project code automatically: take the project type (2-3 letters from domain), tech hint if known (2-3 letters), "EST" for estimation, and today's date (YYMMDD). Example: `HLT-EST-260327` for a healthcare estimation on 2026-03-27.

### Step 3: Load domain expert

**First, make this direct tool call** (one call, no subagent, no Grep/Read/Bash — `ToolSearch` is a built-in tool you invoke the same way as `Read`):
- Tool: `ToolSearch`
- `query`: `select:get_domain_expert,get_project_meta,update_project_phase`
- `max_results`: `3`

Then use the MCP tool to check if a domain expert exists:
- Call `get_domain_expert("<domain>")` via the otaman-estimation MCP server
- If found: note that domain expertise is loaded and will be available during estimation
- If not found: inform the user that no domain expert template exists for this domain. Estimation will proceed but domain-specific areas will have higher uncertainty. Suggest the user provide domain-specific documentation if available.

### Step 4: Launch SA agent

Spawn the `otaman-solution-architect` agent using the Agent tool with:

```
You are starting a pre-sale estimation for:
- Project: <project-name>
- Client: <client>
- Domain: <domain>
- Project code: <code>
- Presale directory: .otaman-presale/

Load the `otaman:project-estimator` skill — it owns the Gate 0–3 methodology,
tier selection, domain library, and estimation principles. Follow its gate flow.
Your role is the otaman orchestration around it: persist outputs into
.otaman-presale/, update project-meta.yaml, pull MCP benchmarks, capture knowledge.

<If artifacts path provided>
Read the client artifacts at: <artifacts-path>
</If>

Domain knowledge comes from two sources — load both if available:
- The skill's references/domains/<domain>.md (strategic + estimation context)
- MCP get_domain_expert("<domain>") (otaman's estimation checklist)

Begin Gate 0: Intake & Information Verification.

If no artifacts were provided, ask the user to describe the project opportunity —
what problem the client wants to solve, what they've told you so far, any constraints
or requirements mentioned.
```

The SA agent loads the `project-estimator` skill which drives the gate workflow (Gate 0 → 1 → 2 → 3). The agent handles otaman-specific orchestration (artifact persistence, MCP calls, metadata updates).

### Step 5: After estimation completes

When the SA agent finishes (Gate 3 delivered), inform the user:

- Estimation document saved to `.otaman-presale/estimation/`
- Project metadata updated with estimation tier and complexity score
- Next steps:
  - Review and refine the estimation
  - If the project is won: run `/otaman:discovery` to start the discovery phase
  - If discovery is not needed: run `/otaman:handoff` to generate platform.yaml directly

## Notes

- The SA agent pauses at every gate boundary for human feedback. This is intentional — estimation is a collaborative process, not automated output.
- The SA agent uses MCP tools (search_benchmarks, get_component_estimate) to reference past project data. If benchmarks are empty, it will note this and rely on component library estimates.
- All artifacts created during estimation go into `.otaman-presale/` — this directory is temporary and gets migrated to `.agents/` during handoff.
- Re-running `/otaman:presale` on an existing project resumes from where you left off.
