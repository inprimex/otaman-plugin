---
name: approve
description: "Review and approve or reject pending spec-change-request proposals from agents"
model: sonnet
effort: medium
arguments:
  - name: action
    description: "Action to take: list, approve, reject (default: list)"
    required: false
  - name: id
    description: "Message stem or partial match to approve/reject a specific proposal"
    required: false
  - name: comment
    description: "Comment or modifications to include with approval/rejection"
    required: false
---

# /otaman:approve

Review pending spec-change-request messages from agents and approve or reject them.

This is the human-in-the-loop gate for agent-initiated spec changes. Agents propose changes via `/otaman:propose`, and humans control what actually gets created in the specs repo.

## Step 0: Find the project root

**CRITICAL**: You may be running inside a repo subdirectory. To find the project root, try reading `platform.yaml` at increasing parent levels using the **Read tool** (NOT bash):
1. Read `./platform.yaml` — if found, project root = current directory
2. Read `../platform.yaml` — if found, project root = `..`
3. Read `../../platform.yaml` — if found, project root = `../..`
4. Continue up to 5 levels

Once found, resolve to an **absolute path**. All paths below are relative to the project root.

## Step 1: List pending proposals (action=list or no action)

List bus messages and read each one:
```bash
ls $PROJECT_ROOT/.agents/bus/active/
```
Then use Read to check each file. Filter for messages with `type: spec-change-request` and no approval ack.

For each pending proposal, show:
- Message ID and stem (for reference)
- Which agent proposed it (`from` field)
- Title and description
- Justification (why the agent thinks this is needed)
- Affected repos/specs
- Suggested changes

If no pending proposals exist, say so and exit.

## Step 2: Approve (action=approve)

When the human approves a proposal:

1. **Read the full proposal message** from `bus/active/`
2. **Check specs format** from `$PROJECT_ROOT/platform.yaml` → `specs.format`
3. **If `openspec`**:
   - Extract the proposal title and description
   - Run the OpenSpec CLI programmatically in the specs repo:
     ```bash
     cd "$PROJECT_ROOT/{specs.path}" && openspec new change "{title}" --description "{description}"
     ```
   - If `openspec` CLI is not available, fall back to:
     ```bash
     cd "$PROJECT_ROOT/{specs.path}" && npx openspec new change "{title}" --description "{description}"
     ```
   - If neither works, tell the user to run `/opsx:new "{title}"` manually in the specs repo session, then continue with notification
   - After creating the change, the user works on artifacts in the specs repo using:
     - `openspec instructions {artifact} --change {title}` to get instructions for each artifact
     - `openspec status --change {title}` to check completion status
     - Or interactively via `/opsx:ff` in the specs repo Claude Code session
4. **If `fallback`**:
   - Create a proposal file in `$PROJECT_ROOT/.agents/proposals/` with the agent's content
   - Set status to `approved`
5. **Create approval ack**: Write an ack file for the proposal message:
   ```bash
   echo "approved" > "$PROJECT_ROOT/.agents/bus/active/acks/{msg-stem}.human.ack"
   ```
6. **If comment provided**: Append the human's comment/modifications to the ack or create a response message
7. **Broadcast approval**: Write a new bus message to `bus/active/` with:
   - `type: spec-change-approved`
   - `from: human`
   - `to: all`
   - Reference to the original proposal (include the msg-stem so agents can match it to their blocked tasks)
   - Any modifications the human requested
   - Note: the proposing agent's blocked task (in `.agents/blocked/`) will be resolved when they run `/otaman:check` and see both the approval AND the subsequent `spec-change` notification
8. **Map tasks** (if OpenSpec generated tasks.md): Run the task mapping script:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/map-tasks.py" "$PROJECT_ROOT/{specs.path}/openspec/changes/{feature-dir}"
   ```

## Step 3: Reject (action=reject)

When the human rejects a proposal:

1. **Create rejection ack**:
   ```bash
   echo "rejected" > "$PROJECT_ROOT/.agents/bus/active/acks/{msg-stem}.human.ack"
   ```
2. **Broadcast rejection**: Write a new bus message to `bus/active/` with:
   - `type: spec-change-rejected`
   - `from: human`
   - `to: {original proposer}`
   - The rejection reason (from `comment` argument or ask the user)
3. The proposing agent will see the rejection via `/otaman:check`

## Step 4: Approve with modifications

The human can approve but request changes:
1. Follow the approve flow above
2. Include the modifications in the approval broadcast message
3. Set `priority: high` on the broadcast so agents notice
4. The modifications become requirements for the implementing agents

## Important

- Only humans should run `/otaman:approve` — agents must not approve their own proposals
- The approval creates a spec in the OpenSpec repo (or fallback proposals dir) — this is the point of no return for spec creation
- All approvals and rejections are tracked via ack files and bus messages for the audit trail
- If the `openspec` CLI fails, don't silently skip — tell the user and suggest manual alternatives
- The spec-change-hook in the specs repo will automatically notify all agents when the spec is committed
