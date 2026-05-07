---
name: help
description: "Explain how otaman works, list all commands grouped by phase, and show common workflows"
model: haiku
effort: low
arguments:
  - name: topic
    description: "Specific command or topic to explain in detail (e.g., 'init', 'bus', 'ownership'). Omit for the full overview."
    required: false
---

# /otaman:help

Print a concise guide to otaman for the human. If `<topic>` is provided, drill into that command or concept; otherwise print the full overview.

## Step 0: If the user passed a topic

If `<topic>` is one of the commands below, read `${CLAUDE_PLUGIN_ROOT}/commands/<topic>.md` and produce a focused explanation of that command (what it does, when to use it, the arguments, typical flow). Stop there.

If `<topic>` is a concept keyword, route to the matching section:

- `ownership` → explain the ownership model + PreToolUse hook (section "Ownership" below)
- `bus` | `messages` | `protocol` → explain the message bus (section "Communication bus" below)
- `specs` | `openspec` → explain the spec delegation model (section "Specs" below)
- `observers` | `review` | `cto` | `security` → explain observer agents (section "Observers" below)
- `presale` | `estimation` | `gate` → explain the presale flow (section "Pre-sale & estimation" below)
- `workflow` | `flow` → print the end-to-end workflow section only
- `skills` → list the skills that ship with otaman

If `<topic>` is something else, note that it's not a known help topic and fall through to the full overview.

## Full overview — print this when no topic is given

### What otaman is

Otaman is a Claude Code plugin for coordinating multiple Claude Code sessions across multiple repositories. Each repo has exactly one **owner agent** that can write to it; other agents are read-only. Agents communicate through a **file-based message bus** in `.agents/bus/`. Observer agents (CTO, security) review changes without writing code. Specs are delegated to **OpenSpec** when present.

Everything is file-based and git-native — no custom broker, no custom UI, rollback via `git revert`.

### Directory layout

```
my-project/
├── my-project-otaman/        # ← dedicated otaman folder (git repo)
│   ├── platform.yaml          # the single source of truth
│   ├── .agents/               # ownership, bus, reviews, decisions
│   └── .claude/
├── auth-service/              # managed repo (owner: backend-agent)
│   └── .otaman               # marker pointing back to otaman folder
├── web-app/                   # managed repo (owner: frontend-agent)
│   └── .otaman
└── specs-repo/                # optional: OpenSpec lives here
```

### End-to-end workflow

**Pre-sale → delivery (new project from a lead):**

1. `/otaman:presale` — gated estimation (Gate 0 → 1 → 2 → 3), scaffolds `.otaman-presale/`
2. `/otaman:discovery` — validate assumptions, mitigate risks, produce real specs (for complex or low-confidence projects)
3. `/otaman:handoff` — convert presale/discovery output into `platform.yaml`
4. `/otaman:init` — generate `.agents/`, per-repo CLAUDE.md, hooks, marker files
5. Day-to-day: `/otaman:check`, `/otaman:status`, `/otaman:propose`, `/otaman:review`
6. `/otaman:retrospective` — capture estimation accuracy + lessons learned

**Existing project adoption:**

1. `/otaman:scan` — detect repos, tech stacks, OpenSpec, produce draft `platform.yaml`
2. User reviews draft, runs `/otaman:init` from the otaman folder
3. (Optional) `/otaman:migrate` — if you were on the old project-root layout, move to dedicated otaman folder

**Cloning an already-configured project onto a new machine:**

1. `/otaman:clone` — read `platform.yaml`, clone each repo via git/SSH

### Commands (grouped)

**Pre-sale & discovery**
- `/otaman:presale [artifacts]` — gated estimation with the `otaman:project-estimator` skill
- `/otaman:discovery` — validation phase for low-confidence estimates
- `/otaman:handoff` — bridge from pre-sale to development (produces `platform.yaml`)
- `/otaman:retrospective` — post-project capture of estimation accuracy

**Setup**
- `/otaman:scan [path]` — scan existing repos, create draft config
- `/otaman:init` — generate orchestration state from `platform.yaml`
- `/otaman:migrate [name]` — move old layout to dedicated otaman folder
- `/otaman:clone` — clone all repos from `platform.yaml` onto a fresh machine
- `/otaman:doctor` — verify environment (git, runtimes, CLIs, MCP)

**Day-to-day orchestration**
- `/otaman:status [repo] [format]` — cross-repo status view
- `/otaman:check` — read bus messages addressed to current agent
- `/otaman:team` — decompose a cross-repo feature, assign tasks via bus
- `/otaman:gate` — validate readiness for a lifecycle phase transition

**Specs & proposals (agent-initiated)**
- `/otaman:propose` — write a spec-change-request to the bus
- `/otaman:approve` — human reviews and approves/rejects pending proposals

**Reviews & audits**
- `/otaman:review` — trigger CTO / security / spec-validator observer
- `/otaman:reverse-doc` — generate architecture docs (C4, components) from code
- `/otaman:audit-knowledge` — identify gaps in Claude's knowledge of the stack

**Help**
- `/otaman:help [topic]` — this command

### Skills (auto-loaded by agents)

- `otaman:multi-repo-orchestration` — ownership rules, bus protocol, core orchestration
- `otaman:spec-management` — OpenSpec CLI delegation + fallback proposals
- `otaman:knowledge-capture` — capturing reusable facts during presale/delivery
- `otaman:cto-advisor` — strategic advisory methodology, 7-domain library
- `otaman:project-estimator` — gated estimation (Gate 0–3, Tier A–E), same 7 domains

### Agents

- `otaman-solution-architect` — presale orchestration (loads project-estimator + cto-advisor skills)
- `otaman-cto-reviewer` — architecture review of in-flight changes (loads cto-advisor)
- `otaman-security-observer` — security-focused PR / dependency review
- `otaman-spec-validator` — validates spec-change proposals

### Core concepts

#### Ownership

Each repo has exactly one owner in `platform.yaml`. A PreToolUse hook (`scripts/check-ownership.sh`) blocks writes outside the agent's owned repo. Observers are read-only by rule.

#### Communication bus

Messages go to `.agents/bus/active/` with filename `{YYYYMMDDTHHmmSS}-{from}-to-{to}-{type}.md`. Types: `question`, `contract-change`, `spec-change-request`, `spec-change-approved`, `task-assignment`, `task-complete`, `review-request`, `info`. Each recipient writes an ack file (`.agents/bus/active/acks/{msg-stem}.{agent}.ack`) containing `read` or `resolved`. Fully-acked and older-than-`max_age_days` messages move to `.agents/bus/archive/YYYY-MM/`.

#### Specs

When OpenSpec is installed in the specs repo, otaman delegates: `openspec new change "..."`, `openspec instructions`, `openspec archive`. When absent, otaman falls back to markdown proposals in `.agents/proposals/`. Agent-initiated spec changes flow: `propose` → `approve` → OpenSpec CLI execution → bus broadcast → agents adapt → `otaman complete` updates `tasks.md` checkboxes.

#### Observers

Not permanently running — triggered by events (git hooks, spec changes, `/otaman:review`). Write reviews to `.agents/reviews/pending/`. Never modify production code.

#### Pre-sale & estimation

`/otaman:presale` launches the solution-architect agent, which loads the `project-estimator` skill. The skill drives Gate 0 (intake) → Gate 1 (complexity scoring) → Gate 2 (tier A–E selection) → Gate 3 (execution). The agent handles otaman-specific orchestration: `.otaman-presale/` artifacts, `project-meta.yaml`, MCP benchmarks (`search_benchmarks`, `get_component_estimate`, `get_domain_expert`), and knowledge capture. Domains: `healthcare`, `fintech`, `ecommerce`, `ml-ai`, `gaming`, `drones-uav`, `embedded-iot`.

### Common flows — copy-paste starting points

**"I have a new lead — produce an estimate":**
```
/otaman:presale path/to/rfp-or-call-notes.md
```

**"We won the deal — set up the project":**
```
/otaman:handoff        # writes platform.yaml from presale output
/otaman:init           # generates .agents/, markers, per-repo CLAUDE.md
```

**"I'm dropping into an existing project on a new machine":**
```
/otaman:clone          # clones all repos listed in platform.yaml
/otaman:doctor         # verifies the environment
```

**"I'm the backend agent, what's waiting for me?":**
```
/otaman:check          # messages addressed to me
/otaman:status         # overall project state
```

**"I found a spec gap during implementation":**
```
/otaman:propose        # writes spec-change-request to bus
# human runs /otaman:approve later
```

### Reference docs

- `references/agent-roles.md` — role templates
- `references/communication-protocol.md` — message format and lifecycle
- `references/adr-template.md` — ADR template
- `references/compliance-guide.md` — HIPAA / ISO / GDPR audit requirements
- `references/workflows/` — detailed workflow docs
- `references/domain-experts/` — MCP-loaded estimation checklists per domain

### Get deeper help

```
/otaman:help <command>     # e.g. /otaman:help init
/otaman:help <concept>     # e.g. /otaman:help bus
```
