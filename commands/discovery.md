---
name: discovery
description: "Execute the discovery phase — validate assumptions, mitigate risks, produce real specifications"
model: opus
effort: xhigh
arguments:
  - name: action
    description: "Action: status, validate, update (default: status)"
    required: false
---

# /otaman:discovery

Manage the discovery phase of a project. Discovery follows pre-sale estimation and precedes development.

## Purpose

During discovery, the team:
1. Validates or declines each assumption from the pre-sale estimation
2. Deep-dives into requirements (functional + non-functional)
3. Produces real specifications (not estimates)
4. Develops risk mitigation plans
5. Updates the estimation with ±10-15% contingency
6. Produces C4 Container + Component architecture diagrams

## Steps

### Step 0: Find project context

Look for `.otaman-presale/project-meta.yaml` by walking up directories.

- If not found: tell the user to run `/otaman:presale` first.
- If found but `current_phase` is not `discovery`: make this direct tool call first (one call, no subagent, no Grep/Read/Bash — `ToolSearch` is a built-in tool you invoke the same way as `Read`):
  - Tool: `ToolSearch`
  - `query`: `select:update_project_phase,get_project_meta`
  - `max_results`: `2`

  Then use `update_project_phase` to transition to discovery phase. Ask user to confirm.
- If found and `current_phase` is `discovery`: show current status.

### Step 1: Show discovery status (default action)

Read `.otaman-presale/` and present:

1. **Assumptions status**: Read `assumptions.yaml` (or `discovery/validated-assumptions.yaml` if exists). Show:
   - Total assumptions count
   - Confirmed / Declined / Modified / Pending counts
   - Any assumption with HIGH impact that's still pending → flag as blocking

2. **Risks status**: Read `risks.yaml` (or `discovery/updated-risks.yaml`). Show:
   - Total risks count
   - By status: identified / mitigating / accepted / resolved
   - Any HIGH probability + HIGH impact risks without mitigation → flag

3. **Architecture**: Check if `architecture/c4-container.md` exists. If not, note it's needed.

4. **Estimation update**: Check if `estimation/estimate-v2.md` exists (post-discovery re-estimation).

5. **Knowledge audit**: Check if `knowledge-audit.yaml` exists. If not, suggest running `/otaman:audit-knowledge`.

Present a discovery readiness score:
- All assumptions validated + all high risks mitigated + architecture done + estimation updated = **Ready for handoff**
- Some gaps = **In progress** (list gaps)
- Critical gaps = **Blocked** (list blockers)

### Step 2: Validate assumptions (when action = "validate")

Read `assumptions.yaml` and present each pending assumption to the user:

For each assumption:
1. Show: ID, description, confidence, impact if wrong
2. Ask user: **Confirm** / **Decline** / **Modify** / **Skip**
3. If confirmed: update status, add validation_date and notes
4. If declined: update status, flag affected estimation stories for re-estimation
5. If modified: update description and confidence, add notes

Save results to `.otaman-presale/discovery/validated-assumptions.yaml`.

After validation, if any assumptions were declined:
- Calculate impact on estimation (sum of "impact if wrong" hours)
- Suggest re-estimation of affected components
- Flag for SA agent to re-run PERT on affected stories

### Step 3: Update risks (when action = "update")

Read `risks.yaml` and for each risk:
1. Show current status, probability, impact, mitigation
2. Ask user to update: status, add mitigation plan, adjust probability/impact
3. Identify NEW risks discovered during discovery
4. Save to `.otaman-presale/discovery/updated-risks.yaml`

### Step 4: Suggest next steps

Based on the discovery status, recommend:
- If assumptions still pending: "Run `/otaman:discovery validate` to validate assumptions"
- If knowledge audit not done: "Run `/otaman:audit-knowledge` to assess tech stack readiness"
- If architecture missing: "Create C4 Container diagram in `.otaman-presale/architecture/c4-container.md`"
- If estimation not updated: "Re-run estimation with validated data for ±10-15% contingency"
- If all complete: "Ready for handoff. Run `/otaman:handoff` to generate platform.yaml"

## Notes

- Discovery is iterative — run `/otaman:discovery` multiple times to track progress
- The discovery phase typically takes 2-4 weeks depending on project complexity
- All discovery artifacts stay in `.otaman-presale/` until handoff
- The SA agent can be re-invoked during discovery for specific tasks (re-estimation, architecture review)
