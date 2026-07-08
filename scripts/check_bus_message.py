#!/usr/bin/env python3
"""PreToolUse hook body for F012 (security GAP finding, 2026-07-08).

See ``hooks/check-bus-message.sh`` for the bash wrapper that does a cheap
pre-filter and invokes this only for candidate bus-message writes.

Why this exists: ``otaman_core.validate_message.validate_message()`` is
otherwise only ever run as a manual, opt-in ``otaman validate-messages``
audit command — nothing runs it at write time. Neither ``check-ownership.sh``
nor ``check-blocked.sh`` reads ``tool_input.content`` at all (both only look
at ``file_path``). That means, prior to this hook, any agent's Write/Edit
tool call could drop a file straight into ``.agents/bus/active/`` with
``from: human`` / ``type: spec-change-approved`` and nothing would stop it —
not the CLI, not the MCP tool, not any hook. This closes that gap
regardless of which path (CLI ``otaman send``, MCP ``otaman_send``, or a
direct Write/Edit tool call) was used to try to create the message.

Validates the WOULD-BE resulting content of a Write/Edit targeting a
``.agents/bus/**/*.md`` file (excluding the ``acks/`` subdirectory — bare-
text ack markers, not bus messages) and denies the tool call if
``otaman_core.validate_message.validate_message_content`` reports errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": reason,
    }
    print(json.dumps(payload))


def _is_bus_message_path(path_str: str) -> bool:
    """A bus message is a *.md file directly under an .agents/bus/ tree,
    excluding the acks/ subdirectory (bare-text ack markers, not messages —
    validating them as messages would reject every ack write)."""
    if not path_str:
        return False
    parts = Path(path_str).parts
    if "acks" in parts:
        return False
    if not path_str.endswith(".md"):
        return False
    return "bus" in parts and ".agents" in parts


def _resulting_content(tool_name: str, tool_input: dict, file_path: str) -> str | None:
    """The file content the tool call would produce, so Edit (a partial
    diff) is validated on the same footing as Write (a full replacement)."""
    if tool_name == "Write":
        return tool_input.get("content", "")
    if tool_name == "Edit":
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        try:
            current = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            # File doesn't exist yet — unusual for Edit, but best-effort:
            # validate what the new text alone would look like.
            return new
        if old and old in current:
            return current.replace(old, new, 1)
        # old_string not found — the Edit tool call will fail on its own;
        # nothing new to validate here.
        return None
    return None


def main() -> int:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0  # Can't parse — fail open, matching the rest of the hook chain.

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or data.get("file_path") or ""

    if not _is_bus_message_path(file_path):
        return 0

    content = _resulting_content(tool_name, tool_input, file_path)
    if content is None:
        return 0

    from otaman_core._resolve import find_maestro_root
    from otaman_core.validate_message import load_known_agents, validate_message_content

    project_root = find_maestro_root(Path(file_path).resolve().parent)
    known_agents = load_known_agents(project_root) if project_root else set()
    errors, _warnings = validate_message_content(content, known_agents)
    if errors:
        _deny(
            "BLOCKED: this write would produce an invalid bus message ("
            + "; ".join(errors)
            + "). See otaman_core.validate_message for the schema."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
