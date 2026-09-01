# otaman-plugin

> **Otaman platform:** [otaman-core](https://github.com/inprimex/otaman-core) · [otaman-cli](https://github.com/inprimex/otaman-cli) · **otaman-plugin (you are here)** · [otaman-bridge](https://github.com/inprimex/otaman-bridge) · [otaman-runner](https://github.com/inprimex/otaman-runner) · [otaman-adapters](https://github.com/inprimex/otaman-adapters)

Otaman's Claude Code plugin — slash commands, skills, agent definitions, hook scripts, and the stdio MCP fallback server. Marketplace-installable; works standalone or as the client side of a full otaman deployment.

Full documentation, walkthroughs, and architecture notes live at **[docs.otaman.ai](https://docs.otaman.ai)**.

## What this plugin provides

- **Plugin manifest** — `.claude-plugin/plugin.json` / `.mcp.json` declaring the plugin to Claude Code.
- **Slash commands** — every `/otaman:<cmd>` the human or agents invoke in a Claude Code session.
- **Skills** — reusable instructional modules: `multi-repo-orchestration`, `spec-management`, `cto-advisor`, `ba-skill`, `cpo-skill`, and others.
- **Agent definitions** — observer and reviewer personas (cto-reviewer, security-observer, spec-validator) that Claude Code instantiates on demand.
- **Hook scripts** — Bash + Python scripts wired into Claude Code's `PreToolUse`, `SessionStart`, `Stop`, and `PreCompact` lifecycle events.
- **stdio MCP server** — runs in-process when no bridge daemon is present, enabling single-user local operation.
- **Launcher scripts** — `launch-agents.sh` (Linux / macOS) and `launch-agents.ps1` (Windows) for multi-agent session start-up.

## Dependencies

- Claude Code (the harness)
- `otaman-core` (shared protocols, identity resolution, secret-source chain), as a sibling checkout
- `otaman-bridge` at runtime for remote-approval AFK mode (optional — the message bus itself is plain filesystem markdown under `.agents/bus/` and needs no daemon; bridge is only for routing approvals to a phone/remote surface)

## Quick start (development)

```bash
# From the workspace root (parent of this repo and the otaman-core sibling checkout):
uv sync --all-packages

# Run the test suite
uv run --package otaman-plugin pytest

# Install the plugin into Claude Code (from plugin root)
claude mcp add otaman-plugin --transport stdio -- python -m otaman_plugin.servers.bus_server
```

To wire the hooks, add the `hooks.json` entries from `hooks/hooks.json` to your project's `.claude/settings.json`, with `CLAUDE_PLUGIN_ROOT` pointing at this repo's checkout.

## Repository layout

| Directory | Contents |
|---|---|
| `src/otaman_plugin/` | Python modules — MCP servers (`servers/`), discovery, scaffolding, doctor checks |
| `scripts/` | Hook scripts + multi-platform launchers |
| `agents/`, `skills/`, `commands/` | Claude Code plugin assets — subagents, skills, slash commands |
| `hooks/` | `hooks.json` and the auxiliary scripts wired to Claude Code lifecycle events |
| `profiles/` | Skill profiles (healthcare, software-development, minimal-meta) |
| `templates/` | Companion-repo templates used during project scaffolding |
| `examples/` | Worked example of a otaman-managed project layout |
| `references/` | User-facing setup, walkthrough, and reference documentation |
| `tests/` | pytest suite |

## See also

- **[docs.otaman.ai](https://docs.otaman.ai)** — full documentation, walkthroughs, architecture notes, and integration guides
- `references/getting-started.md` — getting started inside this repo
- `references/launcher-walkthrough.md` — launcher quick reference
- `CONTRIBUTING.md` — contributor workflow
- `SECURITY.md` — security policy and reporting channel

## License

AGPL-3.0-only (community edition). Commercial license available for teams that cannot ship source — see [otaman.ai](https://otaman.ai).
