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

3. **What it does**:
   - Creates a new `{project}-otaman/` folder (or user-specified name)
   - Runs `git init` in the new folder
   - Moves: `platform.yaml`, `.agents/`, `launch-agents.*`, `.claude/` into the new folder
   - Rewrites repo paths in `platform.yaml`: `./repo` becomes `../repo`
   - Writes `.otaman` marker files in each managed repo
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
- If the parent directory IS a git repo, warn the user and ask for confirmation.
