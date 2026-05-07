---
name: multi-repo-orchestration
description: "Core otaman skill — ownership enforcement, inter-agent communication protocol, and multi-repo coordination rules"
triggers:
  - "platform.yaml"
  - ".agents/"
  - "ownership"
  - "agent communication"
  - "message bus"
  - "multi-repo"
  - "cross-repo"
---

# Multi-Repo Orchestration

You are working in a **otaman-managed** multi-repo project. Follow these rules strictly.

## Project Layout

Otaman artifacts live in a dedicated **otaman folder** (`{project}-otaman/`) which is its own git repo. Managed repos are siblings (or at any relative path), referenced from `platform.yaml` via relative paths like `../repo-name`.

```
parent-directory/
├── myproject-otaman/          # Otaman folder (its own git repo)
│   ├── platform.yaml           # Project config
│   ├── .agents/                # All orchestration state
│   │   ├── bus/active/         # Message bus
│   │   ├── bus/active/acks/    # Per-agent ack files
│   │   ├── bus/archive/        # Archived messages
│   │   ├── queue/              # Per-agent task queues
│   │   ├── sessions/           # Session state files
│   │   ├── blocked/            # Blocked task tracking
│   │   ├── reviews/            # Observer review results
│   │   ├── decisions/          # Architecture Decision Records
│   │   ├── knowledge/          # Shared tech docs
│   │   ├── ownership.json      # Ownership map
│   │   └── current-agent       # Active agent identity
│   └── ...
├── repo-auth-service/          # Managed repo (owner: backend-agent)
│   ├── .otaman                # Marker file → points to ../myproject-otaman
│   └── ...
├── repo-web-app/               # Managed repo (owner: frontend-agent)
│   ├── .otaman                # Marker file → points to ../myproject-otaman
│   └── ...
└── specs-repo/                 # Specs repo
```

Each managed repo contains a `.otaman` marker file with the relative path back to the otaman folder (e.g., `../myproject-otaman`). Use this to locate the otaman folder from any repo.

### Finding the otaman folder

From a managed repo, read `.otaman` to get the relative path to the otaman folder. All `.agents/` paths in this document are relative to the otaman folder, not the repo you are working in.

## First Session Checklist

When starting a new session on a otaman-managed project, orient yourself before doing any work:

1. **Locate otaman folder**: Read `.otaman` in your repo → resolve the path to the otaman folder
2. **Identity**: Read `{otaman}/.agents/current-agent` or your repo's CLAUDE.md → confirm which agent you are and which repos you own
3. **Bus check**: Run `otaman check` (Bash) → see pending messages and blocked tasks. Pre-allowed in `.claude/settings.local.json` so no permission prompt. The CLI auto-detects project root and your identity.
4. **Task queue**: Read `{otaman}/.agents/queue/{your-agent-name}.md` → see your active/queued/blocked tasks
5. **Specs**: Read specs relevant to your repo (the `specs_dir` paths listed in your repo's CLAUDE.md)
6. **Session state**: If `{otaman}/.agents/sessions/{your-agent-name}.md` exists, read it — it contains your state from before the last context compaction (queue snapshot, pending messages, git status, blocked tasks)
7. **Recent changes**: Run `git log --oneline -10` in your repo → understand recent work
8. **Knowledge docs**: If `{otaman}/.agents/knowledge/` exists, check for tech docs relevant to your current work

(Where `{otaman}` is the path resolved from your repo's `.otaman` marker file.)

Then: resume your active task, or pick the highest-priority queued task, or act on pending bus messages.

## Ownership Model

Each repository has exactly one **owner agent**. The ownership map is in `{otaman}/.agents/ownership.json`.

### Rules
- **You may only write to repos you own.** The PreToolUse hook will block unauthorized writes.
- **You have read access to all repos.** Use this to understand contracts, APIs, and shared types.
- **The otaman folder's `.agents/` directory is shared.** All agents can read and write to it for communication.
- **The `specs/` directory is read-only for all agents** unless going through the proposal workflow.

### Checking your identity
Your agent identity is stored in `{otaman}/.agents/current-agent`. Read this file to know which agent you are and which repos you own.

## Communication Protocol

Agents communicate through structured markdown files in `{otaman}/.agents/bus/active/`.

### Sending a message

Create a new file in `{otaman}/.agents/bus/active/` with this format:

**Filename**: `{YYYYMMDDTHHmmSS}-{your-agent}-to-{target-agent}-{type}.md`

**Content**:
```markdown
---
id: {YYYYMMDDTHHmmSS}-{short-identifier}
from: {your-agent-name}
to: {target-agent-name}
priority: normal
type: info
timestamp: {ISO-8601}
status: pending
---

## Subject: {Brief description}

{Message body with details}
```

### Field values

**priority**: `low` | `normal` | `high` | `urgent`
- `urgent` — blocks your work, need immediate response
- `high` — important, should be addressed soon
- `normal` — standard communication
- `low` — FYI, no action needed

**type**: `question` | `contract-change` | `spec-change-request` | `proposal` | `review-request` | `info` | `task-assignment` | `task-complete`

**to**: A specific agent name, `human` (for approval flows), or `all` for broadcast messages.

**depends_on** (optional): Comma-separated list of message stems that must be resolved before this task can start. Used by `/otaman:team` for cross-repo feature pipelines. When you receive a `task-assignment` with `depends_on`, check that all dependency messages are acked as `resolved` before starting work.

### Acknowledging messages
Acknowledge messages via ack files in `{otaman}/.agents/bus/active/acks/`:
- Mark as read: `echo "read" > {otaman}/.agents/bus/active/acks/{msg-stem}.{your-agent}.ack`
- Mark as resolved: `echo "resolved" > {otaman}/.agents/bus/active/acks/{msg-stem}.{your-agent}.ack`
- Or use the MCP tool: `otaman_ack(cwd, message_stem, "resolved")`
- Or use the CLI: `otaman ack <msg-stem>`

### When to send messages
- You changed an API contract or shared type → send `contract-change` to affected agents
- You need information from another repo → send `question` to the owner
- You want a spec change → send `proposal` (or use `/otaman:propose`)
- You want a review → send `review-request`
- General announcement → send `info` to `all`

## Bus Awareness (CRITICAL)

You MUST actively monitor the message bus. Do not wait for the human to tell you to check — **check proactively**.

### When to check the bus

Run `otaman check` (Bash) or `/otaman:check` (slash) at these moments:

1. **After completing each significant task** — file saved, feature implemented, test passing
2. **Before starting a new task** from your backlog or queue
3. **When idle or waiting** — waiting for tests, builds, or human input
4. **After every 3-5 tool calls** during active work — a quick check takes seconds

**Rule: Never let your pending message count exceed 3 without acting.**

### How to handle each message type

When you receive a message, respond based on its type and your current state:

| Message type | You are idle | You are mid-task |
|-------------|-------------|-----------------|
| `task-assignment` | Start implementing immediately | Ack as `read`, add to your queue, finish current task first |
| `urgent` (any type) | Act immediately | **Pause current work**, inform the human, handle the urgent item |
| `contract-change` | Read it, check if it affects your code, ack as `resolved` | Read it, note if current work is affected, ack as `read`, review impact at next breakpoint |
| `question` | Answer immediately via bus reply | Ack as `read`, answer at your next natural breakpoint |
| `spec-change-approved` | Check if it unblocks any blocked tasks | Same — check blocked tasks |
| `spec-change` | Read updated specs, resume blocked tasks if any | Note it, resume blocked tasks at next breakpoint |
| `info` | Read and ack as `resolved` | Ack as `read`, review when convenient |
| `review-request` | If you're an observer agent, start the review | Ack as `read`, queue the review |

### Message response timing

- **urgent**: Within the current interaction (interrupt if needed)
- **high**: Before starting your next task
- **normal**: At your next natural breakpoint (between tasks)
- **low**: When convenient, no rush

### Autonomy: act, don't ask

When you check the bus and find messages addressed directly to you (not broadcasts), **read all of them immediately** and **act without asking the human for permission first**. Treat the human as a teammate who wants status, not a gatekeeper who wants to approve each step.

Decision rule per message:

- **Confidence ≥95% in the correct response** → just do it. Send the reply, ack the message, update the queue, then report in **short form** (1–3 lines): what arrived, what you sent, what's still pending. Do NOT ask "want me to answer?" — that wastes the human's time.
- **Confidence <95%** (ambiguous question, product decision, irreversible action, risky change) → surface the message content and ask. The cost of a wrong autonomous answer is high.

Things that always require asking, regardless of confidence:
- `spec-change-request` messages to `human` (approval is the whole point)
- Requests that would modify another agent's owned repo
- Destructive operations (deletes, force pushes, schema drops)
- Questions whose answer depends on Roman's business judgment, not technical facts

Things that are almost always safe to auto-handle:
- `question` with a factual answer derivable from the code or specs you own
- `contract-change` / `info` / `spec-change-approved` → read, note impact, ack
- `task-assignment` → ack as `read`, add to queue (starting the work may still need confirmation depending on priority)

Short-form status template after autonomous handling:
```
Bus: 2 direct msgs from frontend-agent.
→ Replied to pagination question (msg 20260411T...).
→ Acked contract-change as resolved.
Pending: none.
```

## Task Queue

Maintain your task queue in `{otaman}/.agents/queue/{your-agent-name}.md`. This is your work backlog — update it as you pick up and complete tasks.

### Queue format

```markdown
## Active
- [ ] {Current task description} (source: {own backlog | bus message stem})

## Queued
- [ ] {Task from bus} (from: {message-stem}, priority: {priority})
- [ ] {Another task} (from: {source}, priority: {priority})

## Blocked
- [ ] {Blocked task} (blocked by: {proposal-stem}, waiting for: {spec approval | spec commit})

## Completed (recent)
- [x] {Done task} (completed: {date})
```

### Queue rules

1. **Max 1 active task** at a time — finish or explicitly pause before switching
2. **Queued tasks sorted by priority** — urgent > high > normal > low
3. **When you finish the active task**: check bus first, then pick highest-priority queued task
4. **When a task-assignment arrives mid-work**: ack as `read`, add to Queued section, continue current task
5. **When an urgent message arrives mid-work**: pause active task (move to Queued with note "paused"), handle urgent item
6. **Blocked tasks stay blocked** until you see both `spec-change-approved` AND `spec-change` messages
7. **Move completed tasks** to the Completed section (keep last 5 for context, remove older ones)

## Task Completion Reporting (CRITICAL)

When you finish implementing tasks from a `task-assignment`, you MUST report completion so `tasks.md` stays accurate. This is not optional — without it, the specs repo shows 0% progress on work that is done.

### How to report

Use the CLI to report which tasks you completed:

```bash
# Specific tasks:
otaman complete <change-name> --tasks "2.1, 2.3"

# A range of tasks:
otaman complete <change-name> --tasks "3.1-3.5"

# All tasks for the change:
otaman complete <change-name> --all
```

This automatically:
1. Updates `tasks.md` in the specs repo (`[ ]` -> `[x]`)
2. Sends a `task-complete` bus message to all agents
3. Clears blocked entries if using `--all`

### When to report

- **After completing each task or small batch** — don't wait until everything is done
- **Before switching to a new task** — report the current one first
- **At session end** — report any work completed during this session

### Rule: never ack without completing

Do NOT ack a `task-assignment` as `resolved` without first running `otaman complete`. The ack means "I handled the message"; `otaman complete` means "the work is done and tracked."

### Lifecycle

```
task-assignment received → ack as "read" → implement → otaman complete → ack as "resolved"
```

## Cross-Repo Awareness

You have read access to all repos in the project. Use this effectively.

### Before implementing API endpoints or shared types
1. Read the contracts in the specs repo (your `specs_dir` paths from CLAUDE.md)
2. If you're implementing a client for another repo's API, read THEIR source code to verify the contract matches reality
3. Check other repos' CLAUDE.md to understand their agent's responsibilities and current work

### Before committing changes that affect other repos
1. **Send `contract-change` message FIRST** — describe what changed and what other agents need to update
2. Do NOT wait for ack before committing — send the notification, then commit
3. If the change is breaking (not backward-compatible), set priority to `high`

### Reading other repos
- Read source code, configs, and documentation freely — you have full read access
- Read their CLAUDE.md to understand their ownership and specs
- **Never write** to a repo you don't own — the PreToolUse hook will block it
- If you need a change in another repo, send a `question` or `task-assignment` message to its owner

## Working with Specs

The `specs/` directory contains the source of truth for all data contracts.

### Reading specs
Always check relevant specs before implementing API endpoints, clients, or shared types. The spec is the contract — your implementation must match it.

### Changing specs — the propose → block → wait → resume cycle

If you discover a missing endpoint, a contract gap, or any spec change needed during implementation, you **must** follow this formal lifecycle:

#### Step 1: Propose
Run `/otaman:propose` with a clear title and detailed description of what needs to change and why. This writes a `spec-change-request` message to the bus addressed to `human`. Do NOT modify specs directly. Do NOT attempt to implement the feature that depends on the missing spec.

#### Step 2: Block
**STOP working on anything that depends on the proposed spec change.** Mark the task as blocked in your current work:
- Note which feature/task is blocked and which proposal it depends on
- Record the proposal message stem (shown after `/otaman:propose`) so you can track it

#### Step 3: Work on other tasks
Switch to tasks that do NOT depend on the pending spec change. If all your current tasks are blocked, inform the human and wait.

#### Step 4: Poll for approval
Your regular bus checks (see **Bus Awareness** section above) will surface these message types:
- `spec-change-approved` — the human approved your proposal. Read the message for any modifications the human requested.
- `spec-change-rejected` — the human rejected it. Read the rejection reason. Either revise and re-propose, or adapt your approach to work within existing specs.
- `spec-change` — the specs repo was updated (new specs committed). This means the actual spec content is now available.
- `task-assignment` — tasks from the updated spec have been mapped to you.

#### Step 5: Resume
Once you see **both** `spec-change-approved` AND `spec-change` (the actual spec update), read the updated spec files from the specs repo (your `specs_dir` paths in CLAUDE.md), then resume implementing the blocked task.

**Critical rule**: Never implement against a spec that doesn't exist yet. The approval message alone is not enough — wait for the actual spec content to be committed and the `spec-change` notification to appear.

## Decision Records

For significant architectural decisions, create an ADR in `{otaman}/.agents/decisions/`:

**Filename**: `{NNN}-{short-title}.md`

**Content**:
```markdown
---
id: ADR-{NNN}
date: {YYYY-MM-DD}
author: {agent-name}
status: proposed
---

## {Title}

### Context
{Why this decision is needed}

### Decision
{What was decided}

### Consequences
{Impact on the project}
```

## Compliance Notes

- All changes must go through git commits with clear messages
- The message bus provides an audit trail of inter-agent communication
- Decision records document architectural choices
- Ownership enforcement prevents unauthorized modifications
- Review trails are preserved in `{otaman}/.agents/reviews/`
