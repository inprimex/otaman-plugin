---
name: check
description: "Check the message bus for messages addressed to the current agent"
effort: low
arguments:
  - name: agent
    description: "Agent name to check messages for (default: auto-detected from .agents/current-agent)"
    required: false
  - name: status
    description: "Filter by status: pending, read, resolved, all (default: pending)"
    required: false
---

# /otaman:check

Run this single Bash command and display its output verbatim:

```bash
otaman check {{agent}}
```

That's it. The CLI handles project root detection, agent identity (auto-resolved from `.agents/current-agent` when `{{agent}}` is empty), bus parsing, ack-status lookup, blocked-task surfacing, and priority sorting. Display the stdout to the user as-is.

## After showing results

If the user wants to acknowledge a specific message, run:

```bash
otaman ack <message-stem>      # marks resolved
otaman ack <message-stem> --read   # marks read but keeps it visible
```

The `<message-stem>` is the filename without `.md`, shown in the `otaman check` output.

## If `otaman` isn't on PATH

The `otaman` binary should be on PATH after `pip install otaman-cli` (or
`uv sync --all-packages` in dev). If it isn't:

```bash
# Option 1: invoke via Python module form (requires otaman-cli installed)
python3 -m otaman_cli.main check {{agent}}

# Option 2: install otaman-cli into the active interpreter
pip install otaman-cli   # or: uv pip install otaman-cli
```

## Notes

- This command uses the bash CLI, not MCP. The CLI is deterministic, doesn't need schema-loading, and works identically across Sonnet / haiku / any model variant. MCP tools (`otaman_check`, `otaman_ack`, etc.) remain available for other commands and for direct programmatic access — they just aren't on the hot path here.
- The pre-allowed permissions in each repo's `.claude/settings.local.json` include `Bash(otaman check:*)` and `Bash(otaman ack:*)` so the user is never prompted.
