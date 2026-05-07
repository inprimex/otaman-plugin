---
name: scan
description: "Scan repos and create a dedicated otaman folder with draft platform.yaml"
model: sonnet
effort: medium
arguments:
  - name: path
    description: "Directory to scan for repos (default: parent of current directory)"
    required: false
---

# /otaman:scan

Scan an existing multi-repo project and create a dedicated otaman folder with a draft `platform.yaml`.

## Steps

### Step 0: Determine scan directory and otaman folder location

Ask the user two things:

1. **Where to scan for repos** — default is the parent directory of CWD (since repos are typically siblings). The user can specify any path.

2. **Where to create the otaman folder** — default suggestion: `{project-name}-otaman` as a sibling of the scanned repos. For example, if scanning `C:\work\watchtower`, suggest `C:\work\watchtower\watchtower-otaman`.

3. **Spec repo** — ask if they have an existing spec repo or want openspec inside the otaman folder.

### Step 1: Create the otaman folder

```bash
mkdir -p "<otaman-folder>"
cd "<otaman-folder>" && git init
```

Generate `.gitignore` in the otaman folder:
```
# Runtime artifacts (not versioned)
.agents/bus/
.agents/blocked/
.agents/queue/
.agents/sessions/
.agents/current-agent
```

### Step 2: Run the discovery script

```bash
py "${CLAUDE_PLUGIN_ROOT}/scripts/discover-repos.py" "<scan-path>" --otaman-dir "<otaman-folder>"
```

This scans the target directory for repos and outputs `platform.yaml.draft` inside the otaman folder. Repo paths will be relative to the otaman folder (e.g., `../watchtower-citadel`).

### Step 3: Present the discovery report

The script outputs a JSON summary to stdout. Format it clearly:
- List each discovered repo with its path, detected tech stack, and suggested owner
- Flag repos that already have CLAUDE.md (append mode)
- Flag repos with existing `.claude/` configs or hooks (preserve mode)
- **OpenSpec detection**: If `openspec` is found, highlight it and note `specs.format: openspec`
- If no OpenSpec found, explain that specs will live inside the otaman folder (`./openspec`)
- Show detected API contracts directory if found
- Warn about monorepo indicators if detected

### Step 4: Interactive ownership assignment

For each repo, ask the user to confirm or change the suggested owner agent name. Use the AskUserQuestion tool to present repos, letting them adjust assignments.

### Step 5: Finalize the draft

After the user confirms ownership:
- Read the generated draft file in the otaman folder
- Edit the `owner` fields to match user choices
- Rename to `platform.yaml` (ask user first if one already exists)

### Step 6: Suggest next steps

Tell the user:
1. Review `platform.yaml` in the otaman folder
2. Run `/otaman:init` from inside the otaman folder to apply the configuration
3. This will create `.agents/`, install hooks in repos, and write `.otaman` marker files

## Owner suggestion heuristics

The discovery script suggests owners based on tech stack:
- React, Vue, Angular, Next.js, Svelte -> `frontend-agent`
- Node.js backend, Express, Fastify, NestJS -> `backend-agent`
- Python (Django, Flask, FastAPI) -> `backend-agent`
- Python (ML libs: torch, tensorflow, sklearn) -> `data-agent`
- Go, Rust, Java, C# -> `backend-agent`
- Terraform, Pulumi, Kubernetes manifests -> `devops-agent`
- Docs-only repo -> `docs-agent`
- Mobile (React Native, Flutter, Swift, Kotlin) -> `mobile-agent`
- Unknown -> `agent-{repo-name}` (user must assign)

These are suggestions only. The user always has final say.

## Important

- Discovery is read-only for repo directories -- no writes to any repo.
- The only directory that gets written to is the new otaman folder.
- If re-scanning with `--update`, reads existing `platform.yaml` from otaman folder.
