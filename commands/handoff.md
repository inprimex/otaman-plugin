---
name: handoff
description: "Convert discovery output into platform.yaml + .agents/ — bridge from pre-sale to development"
model: sonnet
effort: medium
arguments:
  - name: mode
    description: "Mode: 'check' (show readiness), 'execute' (do the handoff)"
    required: false
---

# /otaman:handoff

Bridge from pre-sale/discovery to development. Converts `.otaman-presale/` artifacts into `platform.yaml`, `.agents/`, and OpenSpec repo scaffold.

## Prerequisites

Before running handoff, these should be complete:
- `/otaman:presale` — estimation done (Gate 3 delivered)
- `/otaman:discovery` — assumptions validated, risks mitigated (recommended but not required)
- `/otaman:audit-knowledge` — tech stack gaps identified (recommended)

## Steps

### Step 0: Check readiness (default mode, or mode = "check")

Read `.otaman-presale/` and assess handoff readiness:

| Check | Status | Notes |
|-------|--------|-------|
| Estimation exists | ✅/❌ | `estimation/estimate-v*.md` |
| Assumptions validated | ✅/⚠️/❌ | All confirmed/declined in `discovery/validated-assumptions.yaml` |
| Risks mitigated | ✅/⚠️/❌ | All high risks have mitigation in `discovery/updated-risks.yaml` |
| Architecture documented | ✅/❌ | `architecture/c4-context.md` or `c4-container.md` exists |
| Knowledge audit done | ✅/❌ | `knowledge-audit.yaml` exists |
| No blocking knowledge gaps | ✅/❌ | No `none` confidence items without docs |

If mode is "check", show the table and stop. Suggest running missing steps.

If critical items are missing (no estimation), refuse handoff and explain what's needed.

If non-critical items are missing (no knowledge audit), warn but allow proceeding.

### Step 1: Generate platform.yaml (7.4a)

Read `.otaman-presale/project-meta.yaml` and estimation documents to build `platform.yaml`:

1. **project**: from `project_code` or `project_name`
2. **repos**: from estimation's architecture (ask user to confirm repo list, paths, owners)
3. **domain**: from `project-meta.yaml`
4. **standards**: from estimation's tech stack decisions + knowledge audit
   - Map each repo to its framework, language, package manager, testing
   - Include methodology from estimation (TDD, DDD if mentioned)
5. **lifecycle**: set default phases based on domain, or custom if specified in estimation
6. **knowledge**: from `knowledge-audit.yaml` — list packs and their status
7. **specs**: ask user — OpenSpec or fallback?
8. **observers**: default CTO + security, customize based on domain (healthcare adds compliance observer)
9. **communication**: standard bus config

Use the AskUserQuestion tool to confirm repo list and ownership assignments before writing.

Write `platform.yaml` to the project root.

### Step 2: Scaffold OpenSpec or proposals (7.4b)

Based on `specs.format`:

- **openspec**: Create specs repo directory if it doesn't exist. Suggest user run `openspec init` in it.
- **fallback**: Create `.agents/proposals/` directory (will be created by `/otaman:init`).

If the estimation produced specific feature/epic breakdowns, suggest creating initial proposals or OpenSpec changes for each.

### Step 3: Create ADRs from architecture decisions (7.4c)

Read `.otaman-presale/architecture/tech-decisions.md` (if exists) and convert each technology decision into an ADR:

For each decision:
1. Create `.agents/decisions/{NNN}-{short-title}.md`
2. Use the ADR template from `references/adr-template.md`
3. Include: context (why the decision was needed), decision (what was chosen), alternatives considered, consequences

### Step 4: Migrate presale artifacts (7.4d)

Move relevant `.otaman-presale/` artifacts into `.agents/`:

| Source | Destination | Notes |
|--------|------------|-------|
| `estimation/` | `.agents/estimation-archive/` | Full estimation documents for reference |
| `assumptions.yaml` | `.agents/estimation-archive/assumptions.yaml` | Original + validated |
| `risks.yaml` | `.agents/estimation-archive/risks.yaml` | With mitigation plans |
| `knowledge-audit.yaml` | `.agents/knowledge-audit.yaml` | Active reference |
| `captured-knowledge.yaml` | `.agents/estimation-archive/captured-knowledge.yaml` | Extracted knowledge items |
| `project-meta.yaml` | `.agents/project-meta.yaml` | Update phase to "development" |

Do NOT delete `.otaman-presale/` — keep it as historical record. The migration copies, not moves.

### Step 5: Run /otaman:init

After platform.yaml is created, run `/otaman:init` to generate:
- `.agents/` directory structure
- Per-repo CLAUDE.md with ownership + standards + knowledge references
- Ownership map, agent registry, queue files
- Git hooks

### Step 6: Summary

Present:
- platform.yaml created with {N} repos, {N} agents
- {N} ADRs created from architecture decisions
- Presale artifacts migrated to `.agents/estimation-archive/`
- Knowledge audit: {N} items ready, {N} items need docs
- Phase updated to: development

Suggest next steps:
- Open each repo in its own Claude Code session
- Run `/otaman:check` in each session (auto via launch config)
- Provide documentation for any knowledge gaps before coding
- Start implementing from the task queue

## Notes

- Handoff is a one-time operation per project (pre-sale → development transition)
- Running handoff again will ask before overwriting existing platform.yaml
- The `.otaman-presale/` directory is preserved as historical record
- After handoff, the project lifecycle is managed by otaman's standard commands
