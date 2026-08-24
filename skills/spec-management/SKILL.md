---
name: spec-management
description: "OpenSpec delegation and spec change workflow — delegates to OpenSpec when present, provides lightweight fallback when not"
triggers:
  - "spec change"
  - "proposal"
  - "openspec"
  - "opsx"
  - "API contract"
  - "feature proposal"
  - "spec workflow"
---

# Spec Management

This skill governs how spec and feature changes flow through a otaman-managed project.

## Detecting the mode

Check `platform.yaml` → `specs.format`:
- **`openspec`** — the pinned OpenSpec CLI is available. Delegation to `/opsx:` /
  `openspec` commands is **guarded by identity and repo** — see
  [Authority & guards](#authority--guards-who-may-delegate-to-opsx) below.
  Only **spec-agent, operating in the specs repo**, delegates
  archive/materialization/spec-authoring to the tool.
- **`fallback`** — No OpenSpec. Use otaman's lightweight proposal workflow.

Mere presence of the CLI (`specs.format: openspec`, or the binary being on a
host) NEVER changes an agent's spec workflow on its own. The mode gate is
**necessary but not sufficient** to delegate; the identity/repo guard below
must also hold.

## Authority & guards (who may delegate to `/opsx:*`)

The OpenSpec CLI gates *structure* and executes *standard* delta application;
it does **not** hold *judgment*. Judgment stays with spec-agent's house
procedure. This encodes the `spec-tooling` capability (change
`openspec-cli-adoption`, conflicts C3/C4).

**C3 — delegation is spec-agent-only, in the specs repo.**
Archive, materialization (delta application), and spec-authoring operations
delegate to `/opsx:*` / `openspec` **only when BOTH** hold:
1. the acting identity is **spec-agent** (`OTAMAN_AGENT=spec-agent`), and
2. the session is operating **in the specs repo**.

For **every other agent** — regardless of whether the CLI is installed or
`specs.format` is `openspec` — the spec workflow is **unchanged**:
`/otaman:propose` in, task-assignment out. No `/opsx:*` archive,
materialization, or authoring delegation happens for them. If you are not
spec-agent, treat spec ops exactly as you would in **fallback mode**.

Even for spec-agent, **nonstandard archives** (decision records,
superseded-without-materialization, correction preambles) are NOT delegated —
they run by house procedure (manual, or `openspec archive` with
`--skip-specs`/`-y`). The tool executes *standard* archives only, inside the
branch-and-PR flow after definition-of-done verification.

**C4 — `openspec init`/`openspec update` SHALL NOT run in any fleet repo.**
Those commands write agent-instruction files (CLAUDE.md/AGENTS.md stubs, slash
commands) that collide with the **sanitized, committed CLAUDE.md** and the
**generator-owned CLAUDE.local.md** mechanism. In a fleet repo the correct
action is to **refuse**. If specific assets they produce are wanted, generate
them in a **scratch directory outside the repo** and adopt piecemeal by
explicit review — never let `init/update` write into the working tree.

## OpenSpec mode (`specs.format: openspec`)

> **Scope:** the delegation in this section applies **only to spec-agent
> operating in the specs repo** (C3 guard above). Any other agent — even with
> the CLI installed — stays in the `/otaman:propose` → task-assignment flow
> and should skip to [Fallback mode](#fallback-mode-specsformat-fallback) for
> how spec ops actually work for them.

When OpenSpec is present, otaman does NOT manage proposals, specs, or task breakdowns. OpenSpec handles the full planning lifecycle:

### What otaman delegates (spec-agent, in the specs repo)
| Operation | Interactive (specs repo session) | CLI (programmatic) | Notes |
|-----------|------|-----|-------|
| New change proposal | `/opsx:new` | `openspec new change "{name}"` | Creates change dir in OpenSpec repo |
| Generate artifacts | `/opsx:ff` | `openspec instructions {artifact} --change {name}` | Per-artifact instructions |
| Check status | `/opsx:status` | `openspec status --change {name}` | Shows artifact completion |
| Task breakdown | Reads `tasks.md` from OpenSpec | Otaman maps tasks to repo owners | |
| Implementation | `/opsx:apply` | N/A (interactive only) | Per-repo, within owned repos only |
| Archiving | `/opsx:archive` | `openspec archive {change-name}` | After feature is shipped |

### What otaman adds on top
- **Task-to-owner mapping**: Reads OpenSpec `tasks.md` and maps each task to the repo owner agent. Sends bus messages to notify assigned agents.
- **Cross-repo coordination**: When a feature spans multiple repos, otaman ensures all affected agents are notified via the bus.
- **Ownership enforcement**: Agents can only implement tasks in their owned repos, even if OpenSpec assigns tasks broadly.
- **Observer triggers**: Spec changes trigger CTO/security observer reviews.
- **Propose → block → wait → resume**: Agents that discover spec gaps must formally propose changes and wait for approval before implementing.

### Two workflows

#### Top-down: human initiates a feature
The human works in the specs repo session with OpenSpec installed:
```
1. Human runs /opsx:new "add user pagination" in specs repo (or CLI: openspec new change "add-user-pagination")
2. OpenSpec creates change directory with proposal → human reviews
3. Human runs /opsx:ff → works through artifacts (specs, design, tasks)
4. Human commits → spec-change-hook.sh fires:
   a. Bus notification: spec-change (to: all)
   b. map-tasks.py runs: creates task-assignment messages per repo owner
5. Agents run /otaman:check → see task-assignment messages
6. Agents read specs from their specs_dir paths (READ-ONLY)
7. Agents implement in their owned repos
8. Agents ack task-assignment messages when done
```

#### Bottom-up: agent discovers a spec gap
The agent is working in its repo and realizes the spec is missing or incomplete:
```
1. Agent discovers: "I need POST /users/bulk-invite but spec doesn't define it"
2. Agent runs /otaman:propose "add bulk invite endpoint"
   → writes spec-change-request to bus (to: human)
3. Agent STOPS working on this task — marks it as blocked
   → switches to other non-blocked tasks
4. Human runs /otaman:check or otaman check → sees the proposal
5. Human runs /otaman:approve → approves the proposal
   → approval broadcast written to bus (to: all)
   → otaman tells human: "run /opsx:new in specs repo"
6. Human switches to specs repo session:
   → runs /opsx:new "add bulk invite endpoint" (or CLI: openspec new change "add-bulk-invite")
   → runs /opsx:ff to work through artifacts (proposal → specs → design → tasks)
   → commits changes
7. spec-change-hook.sh fires:
   → bus notification: spec-change (to: all)
   → map-tasks.py creates task-assignment messages
8. Agent runs /otaman:check → sees:
   a. spec-change-approved (from step 5)
   b. spec-change (from step 7)
   c. task-assignment (from step 7)
9. Agent reads updated spec (READ-ONLY)
10. Agent resumes implementing the blocked task
11. Agent acks all messages when done
```

**Critical**: In the bottom-up flow, the agent MUST NOT implement the feature between steps 2 and 9. The proposal is not a spec — it's a request. Only after specs are committed and the `spec-change` notification arrives should the agent proceed.

### Reading OpenSpec artifacts
When you need to understand a feature's requirements:
1. Check `specs.path` in platform.yaml for the OpenSpec repo location
2. Look in `openspec/changes/` for active work items (each feature is a directory)
3. Read `proposal.md` → `design.md` → `tasks.md` in each feature directory
4. Check `openspec/specs/` for accumulated specs (organized by domain)
5. Your CLAUDE.md `specs_dir` mapping tells you which spec folders are relevant to your repo
6. Do NOT modify these files — all spec changes go through `/otaman:propose` → human approval → OpenSpec

## Fallback mode (`specs.format: fallback`)

When OpenSpec is not installed, otaman provides a simple proposal workflow.

### Creating a proposal
Write a markdown file in `.agents/proposals/`:

**Filename**: `{NNN}-{short-description}.md`

**Content**:
```markdown
---
id: PROP-{NNN}
author: {agent-name}
date: {YYYY-MM-DD}
status: proposed
affects: [repo-name-1, repo-name-2]
---

## {Feature title}

### Problem
{What problem this solves}

### Proposed change
{What to change and how}

### Affected repos
{Which repos need changes and what changes}

### API contract changes
{Any OpenAPI / schema changes needed — or "None"}
```

### Proposal statuses
- `proposed` — awaiting review
- `approved` — ready for implementation
- `rejected` — declined with reason
- `implemented` — done, can be cleaned up

### Fallback limitations
The fallback workflow is intentionally simple. It does NOT provide:
- Automated spec generation
- Task breakdown
- Design documents
- Fast-forward workflow

If you need these features, install OpenSpec in your specs repo.

## API Contracts

Regardless of openspec/fallback mode, API contracts (OpenAPI, etc.) may exist separately.

Check `platform.yaml` → `contracts`:
- `contracts.path` — where contract files live
- `contracts.format` — openapi, jsonschema, or protobuf

### Rules for contracts
- Contracts are the **technical** source of truth for inter-service communication
- Always read relevant contracts before implementing API endpoints or clients
- In openspec mode, contracts are derived from OpenSpec specs
- In fallback mode, contracts are managed manually
- Send a `contract-change` bus message to affected agents whenever a contract changes
