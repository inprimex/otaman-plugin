---
name: team
description: "Orchestrate a cross-repo feature — decompose into tasks, assign via bus, track progress"
model: sonnet
effort: medium
arguments:
  - name: workflow
    description: "Workflow type (e.g., 'api-change', 'db-migration') or free-form feature description"
    required: true
  - name: description
    description: "Feature description"
    required: false
---

# /otaman:team

Orchestrate a cross-repo feature by decomposing it into ordered tasks with dependencies, assigning to agents via the bus, and tracking progress.

## How It Works

Unlike Game Studios' `/team-*` (which uses Task tool in a single session), otaman's `/otaman:team` uses the **bus + MCP** for cross-session orchestration:

1. You describe the feature
2. Otaman decomposes it into ordered tasks with dependencies
3. Each task is sent as a `task-assignment` message to the owning agent
4. Agents pick up tasks via `/otaman:check` in their own sessions
5. Agents execute, ack when done
6. `/otaman:status` shows pipeline progress

## Steps

### Step 1: Understand the feature

Read the `<workflow>` and `<description>`. If a workflow template exists in `references/workflows/`, load it for the standard task pattern.

If no template matches, decompose the feature yourself:
- What repos are affected?
- What's the dependency order? (spec first? backend before frontend?)
- Are any tasks parallelizable?

### Step 2: Build the task plan

Create an ordered list of tasks:

```markdown
## Feature: Add pagination to /users endpoint

### Tasks (ordered by dependency)

1. **spec-update** → spec-validator
   - Validate pagination contract exists in spec
   - Depends on: (none)
   - Priority: high

2. **backend-impl** → backend-agent
   - Implement pagination on GET /users (page, limit, cursor)
   - Depends on: spec-update
   - Priority: normal

3. **frontend-update** → frontend-agent
   - Update API client types, add pagination UI
   - Depends on: backend-impl
   - Priority: normal

4. **cross-repo-review** → cto-reviewer
   - Review cross-repo impact and contract consistency
   - Depends on: backend-impl, frontend-update
   - Priority: normal
```

Present this plan to the user for approval before sending messages. Use AskUserQuestion to confirm.

### Step 3: Send task-assignment messages

**First, make this direct tool call** (one call, no subagent, no Grep/Read/Bash — `ToolSearch` is a built-in tool you invoke the same way as `Read`):
- Tool: `ToolSearch`
- `query`: `select:otaman_send,otaman_status`
- `max_results`: `2`

Then for each task, use `otaman_send`:

```
otaman_send(
  cwd=<cwd>,
  to=<agent-name>,
  subject="[TEAM] <task-title>",
  body="## Feature: <feature-name>\n\n<task-description>\n\n**Depends on**: <deps>\n**Priority**: <priority>\n**When done**: ack this message as resolved",
  msg_type="task-assignment",
  priority=<priority>
)
```

For tasks with dependencies, include in the body:
```
**Blocked until**: <dependency task message stems>
Check bus for completion acks from dependency agents before starting.
```

### Step 4: Track progress

After sending all messages, show a summary:

```
Team Pipeline: Add pagination to /users endpoint
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [SENT]    spec-update → spec-validator
  [SENT]    backend-impl → backend-agent (blocked by: spec-update)
  [SENT]    frontend-update → frontend-agent (blocked by: backend-impl)
  [SENT]    cross-repo-review → cto-reviewer (blocked by: backend-impl, frontend-update)

Track progress: /otaman:status or otaman status
Each agent will pick up their task via /otaman:check.
```

### Step 5: Monitor (when called with no arguments on existing pipeline)

If there are existing `[TEAM]` prefixed messages on the bus, show their status:
- Pending (not yet picked up)
- Read (acked as read, agent working on it)
- Resolved (complete)
- Blocked (waiting on dependencies)

## Notes

- Each agent works in their own Claude Code session — otaman:team doesn't spawn subagents
- Tasks are asynchronous — agents pick them up at their own pace (guided by bus awareness rules)
- The human can monitor via `/otaman:status` which shows pending/read/resolved counts
- For urgent features, set priority to `high` — bus awareness rules tell agents to prioritize these
- Workflow templates in `references/workflows/` provide standard task patterns for common operations
