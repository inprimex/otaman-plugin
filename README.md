# otaman-plugin

Otaman's Claude Code plugin — slash commands, skills, agent definitions, hook scripts, and the stdio MCP fallback server. Marketplace-installable; works standalone or as the client side of a full otaman deployment.

## Status

| Component | Shipped | Roadmap |
|---|---|---|
| Claude Code plugin manifest | shipped | — |
| Slash commands (`/otaman:init`, `/otaman:status`, etc.) | shipped | — |
| Skills (multi-repo-orchestration, spec-management, etc.) | shipped | — |
| Agent definitions (cto-reviewer, security-observer, etc.) | shipped | — |
| Hook scripts (ownership, blocked-task, bridge-approval) | shipped | — |
| `stdio` MCP server (Mode 1 local fallback) | shipped | — |
| `launch-agents.sh` (Linux / macOS launcher) | shipped | runner-client refactor (ADR-009) |
| `launch-agents.ps1` (Windows launcher) | shipped | runner-client refactor (ADR-009) |
| NATS event subscription in hooks | — | Step 4 |

## What this repo owns

- **Plugin manifest** — `plugin.json` / `mcp.json` declaring the plugin to Claude Code.
- **Slash commands** — every `/otaman:<cmd>` the human or agents invoke in a Claude Code session.
- **Skills** — reusable instructional modules: `multi-repo-orchestration`, `spec-management`, `cto-advisor`, `ba-skill`, `cpo-skill`, and others.
- **Agent definitions** — observer and reviewer personas (cto-reviewer, security-observer, spec-validator) that Claude Code instantiates on demand.
- **Hook scripts** — Bash + Python scripts wired into Claude Code's `PreToolUse`, `SessionStart`, `Stop`, and `PreCompact` lifecycle events.
- **stdio MCP server** — Mode 1 fallback: runs in-process when no bridge daemon is present, enabling single-user local operation.
- **Launcher scripts** — `launch-agents.sh` / `launch-agents.ps1`; transitioning from direct `tmux`/`wt.exe` calls to `otaman-runner` HTTP clients per ADR-009.

## Dependencies

- Claude Code (harness)
- `otaman-core` (shared protocols, identity resolution, secret-source chain)
- `otaman-bridge` at runtime for remote-approval AFK mode and bus routing (optional — degrades gracefully to stdio MCP)

## Quick start (development)

```bash
# Install with dev + test extras
uv sync --package otaman-plugin --extra test

# Run the test suite
uv run --package otaman-plugin pytest

# Install the plugin into Claude Code (from plugin root)
claude mcp add otaman-plugin --transport stdio -- python -m otaman_plugin.server
```

To wire the hooks, add the `hooks.json` entries from `hooks/hooks.json` to your project's `.claude/settings.json`, with `CLAUDE_PLUGIN_ROOT` pointing at this repo's checkout.

## See also

- [ADR-009 (unified spawner)](https://github.com/inprimex/otaman-meta/blob/main/adrs/ADR-009-unified-spawner.md) — launcher migration to runner clients
- [ADR-006 (NATS system bus)](https://github.com/inprimex/otaman-meta/blob/main/adrs/ADR-006-nats-system-bus.md) — future hook event substrate
- [polyrepo-structure.md](https://github.com/inprimex/otaman-meta/blob/main/polyrepo-structure.md) — ownership map
- [phased-roadmap.md](https://github.com/inprimex/otaman-meta/blob/main/phased-roadmap.md) — Step 1–7 sequencing
- [otaman.dev](https://otaman.dev) — platform docs

## License

AGPL-3.0 (community edition). Commercial license available for teams that cannot ship source — see [otaman.dev](https://otaman.dev).
