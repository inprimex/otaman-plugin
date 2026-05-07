---
name: review
description: "Trigger an observer review (CTO, security, spec-validator) on recent changes or a specific scope"
model: sonnet
effort: medium
arguments:
  - name: reviewer
    description: "Which reviewer to trigger: cto, spec, security, or all (default: all)"
    required: false
  - name: scope
    description: "What to review: a feature name, PR number, repo name, or 'recent' for latest changes (default: recent)"
    required: false
---

# /otaman:review

Trigger one or more observer agents to review changes in the project.

## Step 0: Find the project root

**CRITICAL**: You are likely running inside a repo subdirectory, but `platform.yaml` and `.agents/` live in the **parent project root**.

To find the project root, try reading `platform.yaml` at increasing parent levels using the **Read tool** (NOT bash):
1. Read `./platform.yaml` — if found, project root = current directory
2. Read `../platform.yaml` — if found, project root = `..`
3. Read `../../platform.yaml` — if found, project root = `../..`
4. Continue up to 5 levels

Once found, resolve to an **absolute path**. All paths below are relative to the project root.

## Steps

1. **Determine reviewer(s)**: Based on the `reviewer` argument:
   - `cto` or `cto-reviewer` → launch the otaman-cto-reviewer agent
   - `spec` or `spec-validator` → launch the otaman-spec-validator agent
   - `security` or `security-observer` → launch the otaman-security-observer agent
   - `all` (default) → launch all available observers in parallel

2. **Determine scope**: Based on the `scope` argument:
   - **Feature name** → find the feature in OpenSpec active directory or `$PROJECT_ROOT/.agents/proposals/`
   - **PR number** → use `gh pr view` to get the PR diff and affected files
   - **Repo name** → review recent changes in that specific repo
   - **`recent`** (default) → check git log across all repos for changes since the last review

3. **Gather context for the reviewer**: Before launching the observer agent, collect:
   - The relevant files and changes (diff or file list)
   - The `$PROJECT_ROOT/platform.yaml` config (repos, ownership, specs)
   - Any related bus messages or proposals from `$PROJECT_ROOT/.agents/bus/active/`
   - The API contracts if spec validation is requested

4. **Launch the observer agent(s)**: Use the Agent tool to launch the appropriate agent(s). Provide the gathered context in the prompt. If multiple reviewers are requested, launch them in parallel.

5. **Report results**: After the observer agent(s) complete:
   - Show the review summary (status: approved / changes-requested / needs-discussion)
   - List any action items
   - Note where the full review was saved (`$PROJECT_ROOT/.agents/reviews/pending/`)
   - Send bus messages to affected repo owners if action items exist (write to `bus/active/`)

## Determining "recent changes"

When scope is `recent`:
1. Check `$PROJECT_ROOT/.agents/reviews/done/` for the timestamp of the last completed review
2. For each repo in platform.yaml, run `git log --since=<last-review-date> --oneline`
3. Collect all changed files across repos
4. If no last review exists, use changes from the last 24 hours

## Important

- Observer agents are READ-ONLY — they never modify code or specs
- Reviews are always saved to `$PROJECT_ROOT/.agents/reviews/pending/`
- After a human or agent addresses review feedback, move the review file to `.agents/reviews/done/`
- If a reviewer is not yet implemented, say so and skip it
- Do not block on reviews — they are advisory, not gates (unless the user configures otherwise)
