# otaman-plugin — developer guide

Otaman's Claude Code plugin: slash commands, skills, agent definitions, hook
scripts, two stdio MCP servers (bus + estimation), and the multi-platform
launcher scripts. Part of the **[Otaman platform](https://github.com/inprimex/otaman-core)**
(core · cli · plugin · bridge · runner · adapters).

## Layout

| Path | Contents |
|---|---|
| `src/otaman_plugin/` | Python package — MCP servers (`servers/`), repo discovery, project scaffolding, doctor checks, the CLAUDE.md/marker generator |
| `scripts/` | Hook scripts (`*.sh`, `*.py`) + the multi-platform launchers (`launch-agents.sh`, `launch-agents.ps1`) |
| `servers/` | `run-server.sh` shim that resolves a Python interpreter and execs an MCP server |
| `commands/`, `skills/`, `agents/`, `hooks/` | Plugin assets loaded by Claude Code (slash commands, skills, agent personas, hook wiring) |
| `references/` | User-facing walkthroughs (source of truth for docs.otaman.ai) |
| `tests/` | pytest suite |

## Development

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/). The package
depends on `otaman-core` as a sibling checkout.

```bash
# From the workspace root (parent of the sibling checkouts):
uv sync --all-packages

# Run the test suite:
uv run --package otaman-plugin pytest

# Lint + format (ruff is the single linter/formatter, pinned in CI):
uvx ruff@0.16.3 check .
uvx ruff@0.16.3 format --check .
```

The lint baseline lives in `pyproject.toml` under `[tool.ruff]`. CI runs
`ruff check` + `ruff format --check` as required steps; keep both green.

## Testing notes

- The suite must never touch a live bus. `tests/conftest.py` strips
  `OTAMAN_ROOT` / `MAESTRO_ROOT` / `OTAMAN_AGENT` for every test so
  bus-write code lands in a tmp sandbox, never a real workspace root.
- MCP tools are exposed via FastMCP; call the underlying function in tests
  with `tool.fn(...)`.
- Some launcher tests execute real PowerShell via `pwsh` and skip when it
  is not on `PATH`.

## Installing the plugin

Marketplace-installable, or from source into a Claude Code session:

```bash
claude mcp add otaman-plugin --transport stdio -- python -m otaman_plugin.server
```

Hooks are wired by adding the entries from `hooks/hooks.json` to your
project's `.claude/settings.json`, with `CLAUDE_PLUGIN_ROOT` pointing at
this checkout.

## Contributing

Contributions are accepted under the project's Contributor License
Agreement — see `CONTRIBUTING.md`. This repository is licensed
`AGPL-3.0-only`; see `LICENSE`.

---

> **Note for platform operators:** running `otaman init` writes the private
> orchestration rules (fleet layout, bus internals) to a **gitignored
> `CLAUDE.local.md`** in your working tree, which Claude Code auto-loads
> after this file. That file is never committed; this committed guide is
> the public-safe entry point. Re-run `otaman init` to refresh the local
> rules.
