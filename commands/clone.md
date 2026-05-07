---
name: clone
description: "Clone all project repos from a otaman configuration and set up the environment"
model: haiku
effort: low
arguments:
  - name: source
    description: "Local path, git URL, or SSH remote (user@host:path)"
    required: true
  - name: target
    description: "Target directory (default: current directory)"
    required: false
---

# /otaman:clone

Set up a complete project from a otaman configuration — clone all repos, initialize hooks, check environment.

## Usage

```bash
# From a local platform.yaml or otaman folder:
otaman clone /path/to/platform.yaml
otaman clone /path/to/project-otaman/

# From a git repo (otaman folder tracked in git):
otaman clone git@github.com:org/project-otaman.git

# From a remote server via SSH:
otaman clone user@server:/home/dev/project/project-otaman/

# Specify target directory:
otaman clone git@github.com:org/project-otaman.git --target ~/projects
```

## What it does

1. **Fetches platform.yaml** from the source (local, git clone, or SSH)
2. **Clones all repos** from their `remote` URLs in platform.yaml
3. **Runs otaman init** — creates .agents/, hooks, .otaman markers, .mcp.json
4. **Runs otaman doctor** — validates environment (git, runtimes, CLI tools)
5. **Reports results** — which repos cloned, which failed, environment status

## Prerequisites

- Git installed
- SSH key configured (for SSH/git sources)
- platform.yaml must have `remote` fields on repos (added by `otaman scan`)
