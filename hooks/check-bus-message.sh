#!/usr/bin/env bash
# PreToolUse: F012 — block forged/tampered bus messages before they land on
# disk. See scripts/check_bus_message.py for the full rationale and the
# validation itself; this wrapper only does a cheap bash-level pre-filter
# so python is spawned solely for Write/Edit calls that could plausibly be
# touching a bus message (the vast majority of tool calls never match).
#
# Input (stdin): JSON with tool_name, tool_input (file_path + content for
# Write; file_path + old_string/new_string for Edit).
# Output: same PreToolUse deny contract as check-ownership.sh /
#   check-blocked.sh (permissionDecision:deny + permissionDecisionReason +
#   systemMessage on stdout, exit 0 — never exit 2, see issue #73).
#
# Fail-safe: any error here (no python3, no otaman_core, bad JSON) exits 0
# (allow) — this is a defense-in-depth backstop, not a hard gate the whole
# fleet grinds to a halt on.

set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$HOOK_DIR")"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"

INPUT="$(cat)"

# Fast pre-filter: skip everything that isn't a candidate bus message path.
# (A false positive here — e.g. message BODY text that happens to mention
# ".agents/bus/" — just costs one unnecessary python spawn; the real,
# JSON-aware path check happens in check_bus_message.py.)
case "$INPUT" in
    *'.agents/bus/'*) ;;
    *) exit 0 ;;
esac
case "$INPUT" in
    *'/acks/'*) exit 0 ;;
esac

PY="$(resolve_otaman_python "$PLUGIN_ROOT")" || exit 0

printf '%s' "$INPUT" | ${PY} "$HOOK_DIR/../scripts/check_bus_message.py"
