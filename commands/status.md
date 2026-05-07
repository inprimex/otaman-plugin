---
name: status
description: "Show cross-repo status for the otaman-managed project — git state, pending messages, reviews, and agent activity"
model: haiku
effort: low
arguments:
  - name: repo
    description: "Filter to a specific repo (default: all repos)"
    required: false
  - name: format
    description: "Output format: summary or detail (default: summary)"
    required: false
---

# /otaman:status

Show a consolidated status view across all repos in the otaman-managed project.

## Step 0: Find the project root

**CRITICAL**: You are likely running inside a repo subdirectory (e.g., `my-specs-repo/`), but the `.agents/` directory and `platform.yaml` live in the **parent project root** (e.g., `my-project/`).

To find the project root, try reading `platform.yaml` at increasing parent levels using the **Read tool** (NOT bash):
1. Read `./platform.yaml` — if found, project root = current directory
2. Read `../platform.yaml` — if found, project root = `..`
3. Read `../../platform.yaml` — if found, project root = `../..`
4. Continue up to 5 levels

Once found, resolve the project root to an **absolute path** and use it for all subsequent paths.

All paths below are relative to the project root, NOT the current repo directory.

## Steps

1. **Run the status script**:
   ```bash
   py "${CLAUDE_PLUGIN_ROOT}/scripts/status-report.py" "$PROJECT_ROOT"
   ```
   If the `repo` argument is provided, pass it as a second argument to filter.

2. **Present the report** to the user. The script outputs JSON to stdout. Format it as a clear dashboard:

### Summary view (default)

```
Otaman Status: {project-name}
═══════════════════════════════

Repos (N total):
  auth-service    backend-agent     main ✓  2 ahead  [3 pending msgs]
  web-app         frontend-agent    feat/ui ●  clean   [1 pending msg]
  specs-repo      —                 main ✓  clean    [no messages]

Messages:
  4 pending  │  2 read  │  12 resolved

Reviews:
  1 pending (cto-reviewer: architecture review)
  0 in progress

Proposals:
  1 active (PROP-003: add pagination)
```

### Detail view (format=detail)

Include per-repo:
- Full git log of last 5 commits
- List of pending messages with subjects
- Any pending reviews with status
- Modified files count

## Important

- This command is read-only — it never modifies any state
- If `$PROJECT_ROOT/.agents/` doesn't exist, tell the user to run `/otaman:init` first
- If a repo directory doesn't exist, show it as "NOT FOUND" in the status
- For git operations, handle repos that aren't git repositories gracefully
- Messages are in `bus/active/`, NOT directly in `bus/`
