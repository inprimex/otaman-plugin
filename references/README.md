# otaman references

User-facing reference docs and walkthroughs for the otaman plugin.

Full documentation, including topics not covered here, lives at
**[docs.otaman.ai](https://docs.otaman.ai)**.

## Start here

If you're new to otaman:

1. **[getting-started.md](./getting-started.md)** — 15-minute zero-to-working tutorial. Read this first.
2. **[../README.md](../README.md)** (plugin root) — what otaman is + the project brief.

## Setup walkthroughs

The four most-common setup tasks, each step-by-step with troubleshooting:

| Walkthrough | What it covers | Time |
|---|---|---|
| **[telegram-setup.md](./telegram-setup.md)** | Bot via @BotFather, group with topics, allowlist, AFK approval round-trip | ~10 min |
| **[launcher-walkthrough.md](./launcher-walkthrough.md)** | Launcher folder concept, connections (local/lan/mesh), accounts, tmux resilience, profile subsets | ~15 min |
| **[git-host-setup.md](./git-host-setup.md)** | PAT creation per provider (GitHub, GitLab, Bitbucket, Azure DevOps), secrets chain, verification | ~5 min/provider |
| **[messenger-config.md](./messenger-config.md)** | Deeper Telegram transport config — bot tokens, allowlist patterns, transport overrides | reference |
| **[team-mode-setup.md](./team-mode-setup.md)** | Joining an otaman-coordinated team — bridge auth + cross-session messaging | ~15 min |
| **[cloudflare-tunnel.md](./cloudflare-tunnel.md)** | Deploy bridge + Zitadel behind one Cloudflare Tunnel, no VPN | reference |

## Reference docs

Schema + protocol references, not step-by-step tutorials:

| Doc | Purpose |
|---|---|
| **[communication-protocol.md](./communication-protocol.md)** | Bus message schema, priorities, addressing, ack lifecycle |
| **[compliance-guide.md](./compliance-guide.md)** | HIPAA / ISO 27001 / GDPR audit-trail considerations |
| **[connection-resilience.md](./connection-resilience.md)** | How tmux + SSH retry interact with long-running agents |

## Folder references

| Folder | Contents |
|---|---|
| **[path-rules/](./path-rules/)** | Path-resolution conventions across managed repos |
| **[workflows/](./workflows/)** | Multi-step workflow recipes for common engagements |
| **[domain-experts/](./domain-experts/)** | Per-domain context (ecommerce, fintech, healthcare, iot, marketplace, ml-ai, saas) — consumed by the estimation MCP server |
| **[estimation-templates/](./estimation-templates/)** | Tier-A through tier-E project-sizing templates used by the pre-sale solution architect |

## What to read in what order

**Solo developer new to Claude-Code multi-repo work:**
1. `getting-started.md`
2. `launcher-walkthrough.md`
3. `telegram-setup.md` once you start working away from your desk

**Joining an existing otaman-coordinated team:**
1. `getting-started.md`
2. `team-mode-setup.md`

**Plugin contributors / curious developers:**
1. `../README.md` (project brief)
2. `../CLAUDE.md` (plugin dev guide)
3. [docs.otaman.ai](https://docs.otaman.ai) for full architecture detail

## Conventions

- All walkthroughs target **15 minutes or less** of focused setup time.
- Every walkthrough has a **troubleshooting** section for the 5 most common failures.
- Commands assume Unix/macOS shells with `bash` / `zsh` unless explicitly flagged for Windows PowerShell.
- The `_secrets` chain (env => dotenv => keyring) is the universal pattern for storing tokens; **never** put tokens in `platform.yaml` or `launch-settings.yaml`.
