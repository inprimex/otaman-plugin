---
name: init
description: "Initialize a otaman-managed project from platform.yaml — generates .agents/ directory, ownership map, per-repo CLAUDE.md files, .otaman markers, and agent registry"
model: sonnet
effort: medium
arguments:
  - name: config
    description: "Path to platform.yaml (default: ./platform.yaml)"
    required: false
---

# /otaman:init

Initialize the otaman orchestration layer for this project.

## Step 0: Find platform.yaml

You should be running inside the **otaman folder** (the dedicated directory created by `/otaman:scan`).

Check for `platform.yaml` in the current directory first. If not found, try reading at increasing parent levels using the **Read tool** (NOT bash):
1. Read `./platform.yaml` — if found, otaman root = current directory
2. Read `../platform.yaml` — if found, otaman root = `..`
3. Continue up to 5 levels

Once found, resolve to an **absolute path**.

## Steps

1. **Locate config**: Find `platform.yaml` at the path provided, or at `$OTAMAN_ROOT/platform.yaml`. If it doesn't exist, copy the template from `${CLAUDE_PLUGIN_ROOT}/assets/platform.yaml.template` to `./platform.yaml` and tell the user to customize it before re-running.

2. **Validate config**: Run the validation script:
   ```bash
   py "${CLAUDE_PLUGIN_ROOT}/scripts/validate-platform.py" "<config-path>"
   ```
   If validation fails, show the errors and stop.

3. **Generate agent infrastructure**: Run the generation script:
   ```bash
   py "${CLAUDE_PLUGIN_ROOT}/scripts/generate-agent-config.py" "<config-path>"
   ```
   This creates:
   - `.agents/` directory with subdirectories: `bus/active/`, `bus/active/acks/`, `bus/archive/`, `proposals/`, `reviews/pending/`, `reviews/done/`, `decisions/`
   - `.agents/ownership.json` — maps repos to owner agents
   - `.agents/agents.yaml` — registry of all agents and their roles
   - Per-repo `CLAUDE.md` files with ownership rules (appends if exists)
   - Per-repo `.otaman` marker files pointing back to the otaman folder
   - Per-repo `.gitignore` updated with `.otaman` entry
   - Git hooks in each repo (post-commit, spec-change)

4. **Report results**: Show the user what was generated. List:
   - Number of repos configured
   - Agent names and their owned repos
   - Observer roles configured
   - Communication bus path
   - .otaman markers installed
   - Any warnings (e.g., repo directories that don't exist yet)

## Important

- Never overwrite an existing `.agents/ownership.json` without asking the user first. If it exists, ask whether to regenerate.
- Never overwrite existing per-repo `CLAUDE.md` files. The script appends otaman rules to existing files or creates new ones.
- If repo directories listed in `platform.yaml` don't exist, warn but don't fail — the user may create them later.
- The `.otaman` marker file in each repo is gitignored — it's a local pointer, not a versioned artifact.
