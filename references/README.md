# otaman references

User-facing reference docs and walkthroughs for the otaman plugin.

## Start here

If you're new to otaman:

1. **[getting-started.md](./getting-started.md)** — 15-minute zero-to-working tutorial. Read this first.
2. **[../README.md](../README.md)** (plugin root) — what otaman is + the project brief

## Setup walkthroughs

The four most-common setup tasks, each step-by-step with troubleshooting:

| Walkthrough | What it covers | Time |
|---|---|---|
| **[telegram-setup.md](./telegram-setup.md)** | Bot via @BotFather, group with topics, allowlist, AFK approval round-trip | ~10 min |
| **[launcher-walkthrough.md](./launcher-walkthrough.md)** | Launcher folder concept, connections (local/lan/mesh), accounts, tmux resilience, profile subsets | ~15 min |
| **[git-host-setup.md](./git-host-setup.md)** | PAT creation per provider (GitHub, GitLab, Bitbucket, Azure DevOps), secrets chain, verification | ~5 min/provider |
| **[messenger-config.md](./messenger-config.md)** | Deeper Telegram transport config — bot tokens, allowlist patterns, transport overrides | reference |

## Reference docs

Schema + protocol references, not step-by-step tutorials:

| Doc | Purpose |
|---|---|
| **[agent-roles.md](./agent-roles.md)** | Templates for agent role definitions in `platform.yaml` |
| **[communication-protocol.md](./communication-protocol.md)** | Bus message schema, priorities, addressing, ack lifecycle |
| **[compliance-guide.md](./compliance-guide.md)** | HIPAA / ISO 27001 / GDPR audit-trail considerations |
| **[adr-template.md](./adr-template.md)** | ADR (Architecture Decision Record) template for spec changes |
| **[connection-resilience.md](./connection-resilience.md)** | How tmux + SSH retry interact with long-running agents |

## Design + roadmap

Architecture and where-things-are-going content (you don't need this
for daily use, but useful for contributors):

| Doc | Purpose |
|---|---|
| **[remote-approval-design.md](./remote-approval-design.md)** | T1..T2d bridge daemon design — how Telegram approvals are wired |
| **[project-brief.md](./project-brief.md)** | The pitch + design rationale + scope decisions |
| **[phase-8-roadmap.md](./phase-8-roadmap.md)** | Phase 8+ collab modes + the five deployment modes |
| **[t1-migration.md](./t1-migration.md)** | Account-isolation rollout notes from the T1 release |
| **[t2-live-test.md](./t2-live-test.md)** | Bridge daemon T2 live-test transcript (Telegram round-trip) |

## Per-domain references

| Folder | Contents |
|---|---|
| **[domain-experts/](./domain-experts/)** | Per-domain estimation knowledge packs (healthcare, fintech, ecommerce, ml-ai, marketplace, saas, iot) — loaded by the `otaman:project-estimator` skill |
| **[estimation-templates/](./estimation-templates/)** | Tier A-E project templates (proposal + workbook shapes) |
| **[path-rules/](./path-rules/)** | Path-resolution conventions across managed repos |
| **[workflows/](./workflows/)** | Multi-step workflow recipes for common engagements |

## What to read in what order

**Solo developer new to claude-code multi-repo work:**
1. `getting-started.md`
2. `launcher-walkthrough.md`
3. `telegram-setup.md` when you start working away from your desk

**Adding otaman to an existing legacy maestro project:**
1. `getting-started.md` (the migrate flow is mentioned but rare path)
2. The CLAUDE.md in the maestro folder describes the migrate-vs-init choice

**Plugin contributors / curious developers:**
1. `../README.md` (project brief)
2. `project-brief.md` (deeper design rationale)
3. `phase-8-roadmap.md` (where we're going)
4. `../CLAUDE.md` (the plugin's own dev guide)
5. ADRs in `../../otaman-meta/adrs/` (locked architectural decisions)

## Conventions

- All walkthroughs target **15 minutes or less** of focused setup time.
- Every walkthrough has a **troubleshooting** section for the 5 most
  common failures.
- Commands assume Unix/macOS shells with `bash`/`zsh` unless explicitly
  flagged for Windows PowerShell.
- The `_secrets` chain (env → dotenv → keyring) is the universal pattern
  for storing tokens; **never** put tokens in `platform.yaml` or
  `launch-settings.yaml`.
