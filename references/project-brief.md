# Otaman — Project Brief

> Self-contained overview for discussion. Snapshot date: 2026-04-30.
> Scope: enough context to have substantive architectural / strategic conversations
> without the reader having access to the codebase.

---

## 1. What Otaman Is

A Claude Code plugin that turns multiple Claude Code instances — each running in its own VS Code window or terminal tab — into a coordinated multi-agent team that can collaborate across multiple repositories with strict ownership boundaries, structured inter-agent communication, and compliance-friendly audit trails.

**Target user**: CTOs, tech leads, and senior developers managing multi-repo platforms (often 5–10+ repos), particularly in regulated industries (HIPAA, ISO 27001, GDPR) where every agent action needs to be traceable.

**Built by**: Roman Starikov, who runs an outsource development company and uses otaman to manage client engagements end-to-end (pre-sale → discovery → development → support → retrospective).

---

## 2. The Problem It Solves

When a single team uses Claude Code across many repos, every Claude Code session is independent. There's no built-in way to:

- **Enforce ownership** — prevent the "frontend agent" from accidentally rewriting the auth-service code.
- **Coordinate spec changes** — agent A discovers a missing API endpoint mid-implementation; agent B in another repo needs to know.
- **Maintain a communication protocol** — file-based messages with priorities, addressing, and acknowledgement.
- **Capture an audit trail** — required by compliance regimes (HIPAA, ISO 27001, GDPR), and by clients who pay per-hour.
- **Drive cross-repo features** — "add pagination to /users" touches backend, web, mobile; how do agents pick up their slice without conflicting?

Claude Code's built-in Agent Teams solves single-session orchestration but doesn't address cross-session, multi-repo, ownership-enforced work. Existing community frameworks (CrewAI etc.) target different problem spaces (workflow automation, not human-supervised dev work).

---

## 3. Architecture Overview

### Plugin shape

Otaman is a **Claude Code plugin**, not a standalone CLI. This buys:

- Native hooks integration (PreToolUse for ownership enforcement, UserPromptSubmit for bus surfacing, SessionStart for AFK control)
- Slash commands (`/otaman:init`, `/otaman:status`, etc.)
- Skills that auto-trigger when agents work in a otaman-managed project
- Distribution via the Claude Code plugin marketplace (planned)
- Composability with other plugins (hookify, security-guidance, code-review)

A `otaman` Bash CLI exists for human-facing operations and as an integration surface for external tooling.

### Dedicated otaman folder layout

A otaman project is a sibling folder of the managed repos:

```
parent-dir/
├── myproject-otaman/         # The otaman folder — its own git repo
│   ├── platform.yaml          # Single source of truth
│   ├── .agents/               # All orchestration state (bus, queues, ownership map)
│   ├── .otaman-presale/      # Pre-sale artifacts (estimation, discovery)
│   └── ...
├── auth-service/              # Managed repo
│   ├── .otaman               # Marker file — relative path to otaman folder
│   ├── CLAUDE.md              # Has a <!-- otaman:begin -->...<!-- end --> block
│   └── .git/hooks/post-commit # Otaman hooks installed here
├── web-app/
│   └── ...
└── specs-repo/                # Optional — OpenSpec lives here when used
```

Each managed repo gets a `.otaman` marker file (gitignored) so any script or hook running inside the repo can find the otaman folder. The resolution chain is `.otaman` file → `OTAMAN_ROOT` env var → walk-up fallback.

### platform.yaml — declarative source of truth

Every project is described by a single YAML file:

```yaml
project: greenbin
version: "1.0"
repos:
  - name: auth-service
    path: ../auth-service
    owner: backend-agent
    tech: [csharp, dotnet]
    remote: git@gitlab.com:greenbin/auth-service.git
    launch:                              # Optional per-repo launcher hint
      title: "Backend"
      shell: ssh
      commands: ["claude /otaman:check"]
specs:
  path: ../greenbin-specs
  format: openspec                       # openspec | fallback
git_host:                                # Phase 7 — API integration
  provider: gitlab
  token:
    sources:
      - { type: env,     name: OTAMAN_GL_TOKEN }
      - { type: dotenv,  name: OTAMAN_GL_TOKEN }
      - { type: keyring, service: otaman, account: gitlab-greenbin }
git_platform:                            # Lighter — used for cloning
  provider: gitlab
  org: greenbin
observers:
  - role: cto-reviewer
    triggers: [pr, spec-change, architecture-change]
  - role: security
    triggers: [pr, dependency-update, auth-change]
communication:
  bus_path: .agents/bus
  format: markdown
  max_age_days: 30
standards:
  git:
    branching: custom
    development_branch: release/dev
    notes: "Legacy: release/dev (development), release/prod (production)."
profiles:
  backend: { repos: [auth-service, ...] }
  full:    { repos: all }
```

`/otaman:init` consumes this and generates `.agents/`, per-repo `CLAUDE.md` blocks, ownership maps, hooks, and `.mcp.json` files.

### Ownership model

Each repo has exactly one **owner agent**. Soft enforcement (per-repo `CLAUDE.md` tells the agent its boundaries) plus hard enforcement (PreToolUse hook blocks unauthorized writes). The hook reads `.agents/ownership.json` (generated from `platform.yaml`) and refuses any tool call whose target path is outside the current agent's owned repos.

### Bus / communication protocol

File-based message queue under `.agents/bus/`:

```
.agents/bus/
├── active/
│   ├── 20260428T210722-spec-agent-to-admin-agent-fix-ci.md
│   ├── 20260428T215619-mobile-agent-to-all-post-commit-review.md
│   └── acks/
│       └── 20260428T210722-spec-agent-to-admin-agent-fix-ci.admin-agent.ack
└── archive/
    └── 2026-04/                       # Rolled monthly when fully acked
```

- Messages are immutable after creation; ack state lives in per-agent ack files (`{stem}.{agent}.ack` containing `read` or `resolved`).
- Broadcast (`to: all`) requires every agent to ack before archival.
- Message types: `question`, `contract-change`, `spec-change-request`, `spec-change-approved`, `spec-change-rejected`, `review-request`, `task-assignment`, `task-complete`, `info`.
- Priorities: `low | normal | high | urgent`.

### MCP servers

Two stdio-launched MCP servers, declared in the plugin's `.mcp.json`:

- **otaman-bus** — 13 tools: `otaman_check`, `otaman_send`, `otaman_ack`, `otaman_status`, `otaman_read_message`, `otaman_blocked`, `otaman_queue`, `otaman_complete`, `otaman_propose`, `otaman_list_agents`, `otaman_set_agent`, `otaman_read_spec`, `otaman_cleanup`.
- **otaman-estimation** — 7 tools: `search_benchmarks`, `add_benchmark`, `get_component_estimate`, `get_domain_expert`, `get_project_meta`, `update_project_phase`, `save_knowledge_item`.

Both built on FastMCP. Each managed repo also gets a per-repo `.mcp.json` (merged with existing) so the tools are available wherever an agent works.

### Hooks

| Event | Hook | Purpose |
|---|---|---|
| PreToolUse | `check-ownership.sh` | Block writes outside owned repo |
| PreToolUse | `bridge-approval.py` | Route Write/Edit to Telegram for approval when AFK |
| UserPromptSubmit | `bus-status-hook.sh` | Inject "[otaman] N pending" line |
| UserPromptSubmit | `user-activity.sh` | Update last-activity timestamp for idle-AFK |
| SessionStart | `check-account.sh` | Verify launcher-set account matches |
| SessionStart | `ssh-auto-afk.sh` | Auto-AFK on unattended-flagged connections |
| SessionStart | `session-start-clear-afk.sh` | Clear stale AFK on fresh session |
| Stop | `stop-notify.sh` | Telegram ping when Claude ends with `?` and AFK on |

### Bridge daemon (Phase 6)

A per-account loopback HTTP daemon that bridges Claude Code's PreToolUse / Stop hooks to a Telegram bot:

- Auto-creates a forum topic per project in a Telegram group, with allowlisted user IDs.
- Surfaces approval prompts (`Approve / Reject` buttons) and bus messages (`spec-change-request`, `to: human`).
- AFK toggle (`otaman afk on|off|status`) — three sources: `manual`, `unattended` (launcher-flagged), `idle-auto` (configurable N-minute idle watchdog).
- Free-text replies via Telegram MessageHandler land back as bus messages.
- One daemon per otaman account; many accounts can share one Claude OAuth login.

---

## 4. Spec Hierarchy: OpenSpec → API Contracts

Otaman recognises two spec layers:

- **OpenSpec** (business layer) — *what* and *why*. Lives in a dedicated specs repo using the OpenSpec framework. Contains proposals, requirements, design, tasks. This is where product decisions are made.
- **API Contracts** (technical layer) — OpenAPI, event schemas, shared types. Derived from OpenSpec decisions.

Otaman **delegates** to OpenSpec rather than duplicating. When a managed project has OpenSpec installed, all spec operations invoke the `openspec` CLI programmatically. When OpenSpec is absent, otaman falls back to lightweight markdown proposals in `.agents/proposals/`.

### Two flows

**Top-down (human-initiated)**:
1. Human creates a feature via OpenSpec (`/opsx:new add-auth` in specs repo)
2. OpenSpec generates proposal, specs, design, tasks
3. Otaman reads `tasks.md` and maps tasks to repo owners
4. Agents implement in their owned repos, coordinating via bus
5. Agents report completion via `otaman complete` — updates `tasks.md` checkboxes
6. Observers review cross-repo impact

**Bottom-up (agent-initiated, the otaman-distinctive flow)**:
1. Agent discovers mid-implementation that a spec change is needed
2. Agent writes `spec-change-request` to bus with what + why + which repos
3. Human reviews via `/otaman:approve` — approves, modifies, or rejects
4. On approval, otaman invokes `openspec` CLI in the specs repo
5. Specs-repo post-commit hook broadcasts `spec-change` to all affected agents
6. Agents adapt and resume

The bottom-up flow is what makes otaman+OpenSpec more powerful than either alone.

---

## 5. Current Capabilities

### Slash commands

| Command | Purpose | Surface |
|---|---|---|
| `/otaman:scan` | Scan existing project, generate draft platform.yaml | Setup |
| `/otaman:init` | Scaffold `.agents/`, install hooks, write per-repo CLAUDE.md | Setup |
| `/otaman:migrate` | Move existing otaman deployment to dedicated folder layout | Setup |
| `/otaman:doctor` | Environment readiness (git, runtimes, CLI tools, MCP) | Diag |
| `/otaman:check` | Read pending bus messages (Bash CLI) | Bus |
| `/otaman:status` | Cross-repo dashboard | Bus |
| `/otaman:propose` | Agent proposes spec change → bus | Spec |
| `/otaman:approve` | Human approves/rejects pending proposals | Spec |
| `/otaman:review` | Trigger cto/security observer review | Spec |
| `/otaman:team` | Decompose a feature, assign tasks across repos | Workflow |
| `/otaman:handoff` | Pre-sale → development bridge | Lifecycle |
| `/otaman:gate` | Lifecycle gate validation | Lifecycle |
| `/otaman:presale` | Start estimation workflow (Gate 0–3, Tier A–E) | Pre-sale |
| `/otaman:discovery` | Discovery-phase validation, risk mitigation | Pre-sale |
| `/otaman:audit-knowledge` | Score Claude's knowledge of project tech stack | Pre-sale |
| `/otaman:retrospective` | Post-project: capture actuals → benchmark library | Post-project |
| `/otaman:bridge` | Daemon lifecycle (install/uninstall/status) | Bridge |
| `/otaman:afk` | AFK toggle | Bridge |
| `/otaman:ping` | Proactive Telegram notification | Bridge |
| `/otaman:reverse-doc` | Generate platform.yaml from existing repos (in-place) | Setup |
| `/otaman:clone` | Clone all repos from platform.yaml | Setup |
| `/otaman:debug-model` | Diagnostic — verify model:frontmatter routing | Diag |

### Skills

- **multi-repo-orchestration** — core: ownership, communication protocol, bus rules, first-session checklist
- **spec-management** — OpenSpec delegation patterns, fallback workflow
- **knowledge-capture** — capturing reusable knowledge during presale/delivery
- **cto-advisor** — strategic CTO + pre-sales advisory methodology, 7-domain library (healthcare, fintech, ecommerce, ml-ai, gaming, drones-uav, embedded-iot)
- **project-estimator** — gated estimation methodology (Gate 0 intake → Gate 1 complexity → Gate 2 tier → Gate 3 execution), tier A–E templates, constraint patterns

### Agents

- **otaman-solution-architect** (model: opus) — pre-sale orchestrator. Wires the project-estimator and cto-advisor skills into otaman's presale flow (project-meta.yaml, MCP benchmarks, `.otaman-presale/` artifacts).
- **otaman-cto-reviewer** — architecture & design review.
- **otaman-security-observer** — security-focused review.
- **otaman-spec-validator** — validates spec change proposals.
- **otaman-debug-model-agent** — diagnostic subagent (verifies model frontmatter routing).

### CLI subcommands (`otaman` binary)

```
otaman scan|init|migrate|doctor|reverse-doc|clone
otaman status|check|ack|send|read|queue|blocked
otaman propose|complete
otaman set-agent|list-agents|cleanup
otaman bridge install|uninstall|status|run
otaman afk on|off|status
otaman ping
otaman accounts list|add|remove
otaman models|launcher
otaman git-host detect|list|check|add|pr|post-review
```

---

## 6. Phases Shipped

| Phase | Theme | Shipped |
|---|---|---|
| 1 | Core MVP — plugin scaffold, schema, init, ownership hook, communication protocol | early |
| 2 | Discovery — scan, OpenSpec detection, propose, spec-validator, cto-reviewer | early |
| 3 | Observers — security-observer, git hooks, status, scheduled review, compliance audit | early |
| 4 | CLI & docs — README, CLI wrapper, examples | early |
| 5 | Spec changes — approval workflow, programmatic OpenSpec CLI, bus restructure (active/archive/acks), task-to-owner mapping, cross-platform paths | early |
| 5.x–9 | Pre-sale / domain templates / lifecycle gates / team orchestration | 57 stories, 79 tests, 82 files |
| 6 | Remote approval bridge — Telegram, AFK, bus surfacing, multi-account | 2026-04-23..25 |
| 7 | Git host integration — provider-neutral PR/MR (GitHub, GitLab, Bitbucket Cloud, Azure DevOps), `otaman git-host` CLI | 2026-04-25 |

937 tests pass as of 2026-04-30.

### Phase 8+ — designed but not started

- **Collab team mode** — HTTP MCP, conversation persistence, headless Claude Code, on-prem Docker, BYO agent. Two artifacts to produce next: per-mode capability matrix + three-decisions doc (bus storage / hot-path hooks / redaction).
- **Five deployment modes** locked: full-local / LAN-mesh / basic-enterprise / advanced-enterprise / SaaS-suspended. One codebase, mode-flag gating, not five products.

---

## 7. Recent Architectural Learnings (2026-04-29..30)

Two failures that shaped current direction.

### A. Deferred MCP tools — instructions don't reliably bridge to tool calls

Claude Code's harness now lists MCP tools by name in a `<system-reminder>` but doesn't pre-load schemas. Calling `otaman_check(...)` directly fails with `InputValidationError` until the agent fetches the schema via `ToolSearch(query="select:<name>")`.

**Two attempts at instructing agents to call ToolSearch first both failed**:

- **v1**: a `## Step 0: Load MCP tool schemas (REQUIRED)` block. Result across 8 greenbin tabs: 5 spawned subagents to "load schemas" (30k+ tokens each), 1 invoked the wrong agent (`otaman-debug-model-agent`) on semantic match of the verb "load".
- **v2**: rewritten as `Tool: ToolSearch / Args: ...`, explicitly forbidding the wrong patterns. Result: 0/8 tabs called ToolSearch correctly. Some treated `ToolSearch` as a shell binary (`command -v toolsearch`), others spawned subagents that ran completely unrelated bash (`command -v aws`).

**Conclusion**: the LLM-instruction → ToolSearch → MCP-tool bridge is too fragile for hot-path commands. Variance comes from model variant (Sonnet main vs haiku sub-skill), prompt cache state, and how the slash-command body lands relative to other system reminders. Wording iterations don't converge.

**Fix (current state)**: hot-path commands use the Bash CLI directly (`otaman check`, `otaman ack`, `otaman status`); structured/write-heavy commands (`/otaman:propose`, `/otaman:team`, etc.) keep MCP because their lower invocation rate masks the variance and their structured payloads are worth the schema-load overhead.

### B. Per-repo agent identity vs project-global

A separate but related bug: `.agents/current-agent` is a flat file shared across the whole project. A `otaman set-agent mobile-agent` from one tab leaked into every other tab — `/otaman:check` resolved to mobile-agent regardless of which repo the tab was in.

**Fix**: `resolve_agent_identity(root, cwd, explicit)` now does CWD → `platform.yaml.repos[]` → owner first, falling back to `.agents/current-agent` only when CWD doesn't match any managed repo. Same priority swap applied to `bus-status-hook.sh`. Tests cover 11 scenarios.

### Lessons captured in CLAUDE.md and persistent memory

- Hot path uses Bash CLI; structured ops use MCP. Don't re-attempt MCP-only on `/otaman:check`.
- New MCP tool added → also add a CLI subcommand if it's read-only and on the hot path.
- Phrasing matters: avoid the verb "load" anywhere near tool-call instructions.

---

## 8. Backlog

Items parked, not on an active phase:

- **Domain coverage gap** — every domain should have both a skill reference file (`skills/{cto-advisor,project-estimator}/references/domains/<d>.md`) AND an MCP payload (`references/domain-experts/<d>.md`). Current gap: `gaming`, `drones-uav`, `embedded-iot` exist only in skills; `marketplace`, `saas`, `iot` exist only in MCP. Both sides need filling out.

- **PM tool integration** — pull backlogs from external systems (Jira, Linear, GitHub Projects, Asana, Notion, Azure DevOps) into otaman. Same PAT/OAuth pattern as git hosts. Imports tickets as `task-assignment` bus messages; completion flows back via `otaman complete`. Provider abstraction in `scripts/pm_sync.py`, Jira + Linear first.

- **Bitbucket Data Center / Server adapter** — separate REST base from Cloud. Defer until a real user self-hosts.

- **Inline / line-level review comments** — current `GitHostAdapter` only supports issue-level comments. Inline comments need different endpoints per provider. Either extend the Protocol or add a parallel `GitHostReviewAdapter`. Wire `/otaman:review` to emit them.

- **Auto-post `/otaman:review` to PR** — today the slash command writes the review to `.agents/reviews/pending/`, then the user runs `otaman git-host post-review` separately. Add a `--post-to-pr` flag (or auto-post when `git_host:` is configured).

- **`otaman upgrade` workflow** — current update path is `git pull` on the plugin host + `/otaman:init` per platform + restart tabs. Worth a dedicated CLI that discovers all known platforms (the launcher already inventories them in `launch-settings.yaml`) and walks them.

- **Block-version markers in per-repo CLAUDE.md** — write `<!-- otaman:version 0.2.3 -->` inside the otaman block. SessionStart hook detects stale versions and posts a one-line nudge.

- **Self-healing init** — split init into a fast `init --refresh-only` that just rewrites the otaman:begin/end block + ownership.json + .otaman markers, skipping hooks/permissions/queue scaffolding. Safe to run on every plugin upgrade.

- **Plugin marketplace listing** — once published, `claude plugin update otaman` becomes a one-liner and the rollout pain disappears.

---

## 9. Tech Stack & Constraints

- **Python 3.10+** (Roman runs 3.14.2 on Windows with `py` launcher; Linux/WSL uses `python3`)
- **Bash** for hooks and the CLI shebang. Cross-platform expected — every script must work in Windows (Git Bash / WSL) and Linux/macOS.
- **YAML** for config (platform.yaml, launch-settings.yaml, schemas)
- **JSON** for ownership maps, MCP config, `.claude/settings.local.json`
- **PyYAML** required for validation; `fastmcp` for MCP servers; `python-telegram-bot` for the bridge transport.
- All paths in `platform.yaml` are **relative** (`../repo-name` from the otaman folder), never absolute. Generated configs use `.as_posix()` (forward slashes) so Windows ↔ WSL works without translation.
- **OpenSpec** is a Node.js dependency (npm-installed, invoked via `openspec` CLI). Optional; otaman has a fallback.
- **Telegram bot API** for the bridge transport. Optional; the bridge's `NullTransport` is the default.
- **Git host CLIs** (glab/gh/etc.) are optional — the Phase 7 adapters call provider APIs directly with PATs.

### Cross-platform rules (hard-won)

- WSL ↔ Git Bash path normalisation: `/mnt/c/...` ↔ `/c/...` ↔ `C:/...`. The CLI's `_normalize_path` and the bridge's `_resolve_account_for_notify` both handle this.
- Single OAuth login can serve many accounts: launcher exports `OTAMAN_ACTIVE_ACCOUNT` per tab; the bridge daemon and `check-account.sh` consult that env var first, falling back to `CLAUDE_CONFIG_DIR` basename.
- AFK has three sources (`manual` / `unattended` / `idle-auto`); SessionEnd clears the auto sources but never clobbers `manual`. Bare SSH presence does NOT auto-AFK — that misfired when humans actively launched tabs from a local laptop.

---

## 10. Ecosystem & Relationships

### Complementary Claude Code plugins

| Plugin | Role alongside otaman |
|---|---|
| **hookify** | Custom per-agent rules beyond ownership |
| **security-guidance** | Base security patterns (XSS, injection) |
| **code-review** | PR review with specialised agents |
| **commit-commands** | Git commit/push/PR workflow |
| **claude-md-management** | Keep per-repo CLAUDE.md current |

Otaman orchestrates *across* repos and adds ownership + communication on top — it doesn't replace these.

### Companion project: Revlet.ai

Structured knowledge packs for AI agents (think "AGENTS.md but as a curated, versioned package per tech stack"). Otaman is the first consumer: `/otaman:audit-knowledge` scores Claude's confidence per technology, suggests revlet.ai pack downloads for gaps. Revlet has its own MCP server contract that otaman will consume in the future.

### Business context

Roman runs an outsource development company; otaman is built around the agency lifecycle:

```
Pre-sale (estimation, gates) → Discovery (assumptions, risks) →
Development (multi-repo agents) → Support → Retrospective (feeds benchmarks)
```

The presale + estimation + retrospective loops feed each other: every project ends with actuals captured to the benchmark library, which feeds the next presale's complexity scoring. This is why otaman has an estimation MCP and not just a bus MCP.

---

## 11. Suggested Discussion Topics

Areas where outside perspective would help.

### Strategic

1. **Audience broadening or narrowing** — Otaman is built for "tech leads with 5–10 repos and regulated-industry compliance needs." Should it also try to land with single-developer-with-a-side-project users (lower friction, but they don't need most of what's built)? Or stay focused on the agency / multi-repo CTO?

2. **Open source, SaaS, or hybrid** — Plugin is currently built in a private repo. The Phase 8 deployment-modes design includes a SaaS variant (suspended). What's the right monetisation angle? Open-source the plugin + sell a hosted bridge daemon? Sell `otaman upgrade` automation? Sell consulting on top?

3. **Otaman vs Revlet boundary** — Both projects are growing. Where does orchestration end and curated-knowledge begin? Currently Revlet provides the *content* (tech stack docs) and otaman provides the *coordination* (who owns what, who needs what). Is that boundary stable or will they merge?

### Tactical

4. **Phase 8 collab team mode** — design started, no code yet. Two artifacts to produce: per-mode capability matrix + three-decisions doc (bus storage / hot-path hooks / redaction). What's the most valuable next slice to ship as an MVP — HTTP MCP for cross-machine bus, or headless Claude Code orchestration for unattended agents?

5. **Update UX is genuinely painful** — current path: `git pull` on the Linux server + `/otaman:init` per platform + restart tabs. Backlog has `otaman upgrade` and block-version markers, but neither is implemented. Worth surfacing as a P1?

6. **Documentation organisation** — `CLAUDE.md` is growing organically (≈580 lines now, mixing architecture, recent learnings, naming conventions, backlog). When should it split, and along what seams?

### Architectural

7. **The Bash CLI vs MCP split** — currently scoped to `/otaman:check` only. Other slash commands (`/otaman:propose`, `/otaman:team`, `/otaman:retrospective`) still use MCP-via-instruction. They haven't shown the same chaos in practice (lower invocation rate), but the underlying fragility is identical. Should the split be backported preemptively, or only when a specific command starts misbehaving?

8. **Slash-command-body design pattern for MCP** — this is a real hole in Claude Code's plugin authoring story. If a slash command needs to call MCP tools, there's no reliable way to instruct the LLM to do so (per Section 7). Possible angles: (a) Claude Code adds an `mcp_tools:` frontmatter field that pre-loads schemas; (b) plugin authors write everything as bash shims; (c) a community pattern emerges. What's the most useful direction to push?

9. **Bus persistence and multi-machine** — file-based bus is great for single-host work but doesn't naturally span machines. The Phase 8 collab mode wants HTTP MCP + persistent storage. Naive options: SQLite + file sync, or PostgreSQL + WebSockets. What's the MVP shape that doesn't over-engineer?

10. **AFK / unattended state model** — three sources today (`manual`, `unattended`, `idle-auto`). The interaction rules around SessionEnd / SessionStart / unattended re-set are subtle and have already had bugs (the `VALID_SOURCES` parse miss on 2026-04-26). Worth modelling as a state machine and writing it down?

---

## 12. Quick Reference

### Repository structure (highlights)

```
otaman-plugin/
├── .claude-plugin/plugin.json           # Plugin manifest
├── .mcp.json                            # MCP server declarations
├── platform-schema.yaml                 # JSON Schema (in YAML) for platform.yaml
├── commands/                            # 22 slash commands
├── skills/                              # 5 skills (cto-advisor, project-estimator, etc.)
├── agents/                              # 5 named agents (solution-architect, etc.)
├── hooks/                               # PreToolUse / SessionStart / Stop / UserPromptSubmit
├── servers/
│   ├── bus_server.py                    # 13 otaman_* MCP tools
│   └── estimation_server.py             # 7 estimation MCP tools
├── scripts/                             # Python helpers (validate-platform, generate-agent-config, etc.)
├── cli/otaman.py                       # The `otaman` binary
├── bridge/                              # Phase 6: daemon, bus-surface, transports
├── references/                          # Reference docs (this file lives here)
├── tests/                               # 937 tests passing as of 2026-04-30
└── CLAUDE.md                            # Internal authoring instructions
```

### Useful entry points for further reading

- `CLAUDE.md` (root) — full architectural rationale, naming conventions, phase history, backlog, and the recent MCP-instruction failure analysis.
- `references/communication-protocol.md` — bus message format, ack semantics, types and priorities.
- `references/remote-approval-design.md` — Phase 6 bridge design.
- `skills/multi-repo-orchestration/SKILL.md` — what an agent reads when it joins a otaman project.
- `skills/project-estimator/SKILL.md` — Gate 0–3 methodology with worked examples.

---

*End of brief. Drop into a claude.ai conversation as the first message and follow up with whatever you want to dig into.*
