---
name: whoami
description: "Show current agent identity + project + routing + bus state"
effort: low
arguments:
  - name: json
    description: "Set to 'json' for JSON output"
    required: false
---

# /otaman:whoami

Run this single Bash command and display its output verbatim:

```bash
otaman whoami
```

That's it. The CLI auto-detects the maestro/otaman project root, resolves agent identity via the same priority chain the hooks use (`.maestro` marker → cwd → `.claude/settings.local.json` → ownership.json), reads platform.yaml for the project name, checks `OTAMAN_ACTIVE_ROUTING` (with legacy fallbacks), reads `CLAUDE_CONFIG_DIR`, queries tmux for the session name, and counts bus messages addressed to this agent. Display the stdout to the user as-is.

## When to use

- User asks "who am I?" / "what agent am I?" / "what tab is this?"
- User asks for current routing / config dir / bus state
- Sanity check after a tmux pane gets reattached or a long idle period
- When the terminal tab title is missing or wrong and you need to confirm context

## JSON mode (for programmatic / scripted use)

```bash
otaman whoami --json
```

Returns a structured payload: `{agent, project, project_root, cwd, routing, config_dir, in_tmux, tmux_session, bus_counts}`.

## Aliases

`otaman iam` is a synonym for `otaman whoami` (shorter to type).

## If `otaman` isn't on PATH

Use the Python module form:

```bash
python3 -m otaman_cli.main whoami
```

## Notes

- Bash CLI, not MCP. Deterministic, hot-path, pre-allowed via `Bash(otaman:*)` in each repo's `.claude/settings.local.json` — never prompts the user.
- Safe to run anywhere (works outside a project too — just shows what's resolvable from the cwd).
