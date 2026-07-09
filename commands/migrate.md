---
name: migrate
description: "Migrate an existing otaman deployment from project-root layout to a dedicated otaman folder"
model: haiku
effort: low
arguments:
  - name: otaman-dir
    description: "Name or path for the new otaman folder (default: {project}-otaman)"
    required: false
---

# /otaman:migrate

Migrate an existing otaman deployment (where artifacts live in a bare project root) to a dedicated otaman folder with its own git repo.

## When to use

Use this when you have an existing project where `platform.yaml`, `.agents/`, launch scripts, and `.claude/` are scattered in a parent directory that has NO git repo.

## Steps

1. **Detect current layout**: Look for `platform.yaml` and `.agents/` in the current directory or parent. If found in a directory without `.git/`, this is a candidate for migration.

2. **Run the migration**:
   ```bash
   otaman migrate [otaman-dir-name]
   ```
   If `otaman` isn't on PATH, invoke as a Python module:
   ```bash
   python3 -m otaman_cli.main migrate [otaman-dir-name]
   ```

   Preview first if the user wants to see what would happen without changing
   anything:
   ```bash
   otaman migrate [otaman-dir-name] --dry-run
   ```
   This is a destructive, cross-directory operation, so the command prints
   an identity echo (resolved root, project name, repo count, target
   folder) up front and then asks for interactive confirmation before
   moving anything — surface that prompt to the user rather than assuming
   it auto-proceeds. Pass `--yes` (or `-y`) to skip the confirmation for a
   non-interactive run.

3. **What it does**:
   - Warns (non-fatal) if the current root already has a `.git/` directory — may already be migrated.
   - Errors out if the target otaman folder already exists and is non-empty, or if there's nothing to migrate (none of the artifacts below are present).
   - Creates a new `{project}-otaman/` folder (or user-specified name)
   - Moves: `platform.yaml`, `.agents/`, `.claude/`, `.mcp.json`, `CLAUDE.md`, and any `launch-agents.ps1`/`launch-agents.sh`/`LAUNCH-AGENTS.md` present, into the new folder
   - Rewrites repo paths in `platform.yaml`: `./repo` becomes `../repo`
   - Runs `git init` in the new folder
   - Writes `.otaman` marker files in each managed repo (includes `agent: <owner>` from `platform.yaml`)
   - Updates `.gitignore` in each repo (adds `.otaman`)
   - Generates `.gitignore` in the otaman folder (ignores runtime artifacts)
   - Makes an initial git commit

4. **After migration**: Tell the user to:
   - Verify the otaman folder contents
   - Run `/otaman:init` from inside the otaman folder to reinstall hooks
   - Launch agents from the otaman folder going forward

## Important

- This is a one-time operation.
- The old parent directory will just have repos as subdirectories after migration.
- The command itself already warns and asks for confirmation before moving anything — no need to duplicate that check yourself, just don't pass `--yes` unless the user explicitly wants a non-interactive run.
