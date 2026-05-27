---
name: propose
description: "Propose a spec change — creates a spec-change-request on the bus for human approval"
model: opus
effort: high
arguments:
  - name: title
    description: "Short title for the proposal (e.g., 'add user pagination')"
    required: true
  - name: description
    description: "Detailed description of what to change and why"
    required: false
---

# /otaman:propose

Propose a spec or feature change. This creates a `spec-change-request` message on the bus that requires human approval via `/otaman:approve` before any specs are modified.

**Key principle**: Agents actively participate in spec evolution by proposing changes they discover during implementation, but humans retain approval authority.

## Step 0: Find the project root

**CRITICAL**: You are likely running inside a repo subdirectory, but `platform.yaml` and `.agents/` live in the **parent project root**.

To find the project root, try reading `platform.yaml` at increasing parent levels using the **Read tool** (NOT bash):
1. Read `./platform.yaml` — if found, project root = current directory
2. Read `../platform.yaml` — if found, project root = `..`
3. Read `../../platform.yaml` — if found, project root = `../..`
4. Continue up to 5 levels

Once found, resolve to an **absolute path**. All paths below are relative to the project root.

## Steps

### 1. Determine agent identity

Read from `$PROJECT_ROOT/.agents/current-agent`, or from the repo's CLAUDE.md otaman block, or ask the user.

### 2. Gather proposal details

If `description` is not provided, ask the agent/user to explain:
- **What** needs to change in the specs
- **Why** — what triggered this discovery (implementation gap, new requirement, missing endpoint, etc.)
- **Which repos/specs** are affected
- **Suggested approach** — how the spec should change

### 3. Create spec-change-request on the bus

Write a message to `$PROJECT_ROOT/.agents/bus/active/`:

**Filename**: `{timestamp}-{agent}-to-human-spec-change-request.md`

Use this format:
```markdown
---
id: {timestamp}-{short-hash}
from: {agent-name}
to: human
priority: high
type: spec-change-request
timestamp: {ISO-8601}
status: pending
---

## Subject: Spec change request: {title}

### What needs to change
{Description of the proposed spec change}

### Why this is needed
{What the agent discovered during implementation that triggered this}

### Affected specs
{Which spec files/areas need updating — reference specs_dir from platform.yaml}

### Affected repos
{Which repos will need implementation changes after the spec updates}

### Suggested spec changes
{Concrete suggestions for what the spec should say}
```

### 4. Record blocked task

After creating the proposal, record what is blocked. Write a file in the project root:

**File**: `$PROJECT_ROOT/.agents/blocked/{agent-name}.md`

Create the directory if it doesn't exist. Append to the file if it already exists:

```markdown
## Blocked: {title}
- **Proposal**: {msg-stem} (the message filename without .md)
- **Blocked since**: {ISO-8601 timestamp}
- **Depends on**: spec-change-approved + spec-change notification
- **Task to resume**: {brief description of what to implement once unblocked}
```

This file serves as a persistent reminder of what the agent is waiting for. It survives session restarts.

### 5. Instruct the agent to stop and wait

Tell the agent clearly:

> Your spec-change-request has been submitted. **You MUST NOT implement the feature that depends on this spec change until it is approved and the specs are committed.**
>
> What to do now:
> 1. Switch to other tasks that do not depend on this proposed spec change
> 2. If all your tasks are blocked, inform the human and wait
> 3. Periodically run `/otaman:check` to look for:
>    - `spec-change-approved` — your proposal was approved
>    - `spec-change` — specs were actually committed in the specs repo (spec-agent authored and committed the artifacts)
>    - `task-assignment` — your specific implementation tasks from the mapped tasks.md
> 4. Once you see a `task-assignment` addressed to you from the new change, read the spec files it references and implement the assigned tasks **in your own repo**. You do NOT author spec artifacts — spec-agent does that. Your job resumes as implementation work.
> 5. If you see `spec-change-rejected`, read the rejection reason and adapt
>
> Proposal message: `{msg-stem}`
> Blocked task recorded in: `.agents/blocked/{agent-name}.md`

## Important

- **Do NOT directly modify specs or delegate to `/opsx:new`** — that's what `/otaman:approve` does after human review
- **Do NOT create files in `.agents/proposals/`** — the bus message IS the proposal
- **Do NOT implement features that depend on a pending spec change** — wait for approval + spec commit
- The `to: human` field ensures this shows up when the human checks the bus
- In both openspec and fallback mode, the flow is the same: propose → block → wait → resume
- If the agent is the spec-agent itself (working in the specs repo), it still must go through the approval flow
- Messages go to `bus/active/`, NOT directly to `bus/`
- **spec-agent authors all spec artifacts** after approval — `proposal.md`, `design.md`, `tasks.md`, spec files, ADRs. The proposing agent NEVER writes these. The proposing agent only implements code in their own repo, driven by `task-assignment` messages that arrive after spec-agent maps `tasks.md`.
