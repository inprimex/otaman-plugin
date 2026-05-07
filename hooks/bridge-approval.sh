#!/usr/bin/env bash
# PreToolUse: forward permission prompts to the bridge daemon when
# AFK mode is on. Fail-safe: any error path exits 0 so Claude Code's
# native terminal prompt handles the decision.
#
# SCOPE: Registered in hooks/hooks.json for the tools that actually
# perform side effects (Bash, Write, Edit, NotebookEdit). Read-only
# tools (Read, Grep, Glob, MCP tools that fetch state) bypass the
# bridge so routine agent orchestration doesn't spam the phone with
# approval prompts. Widen the matcher in hooks.json if you want
# finer-grained coverage.
#
# Input (stdin): JSON with tool_name, tool_input, session_id.
# Output (stdout, only when taking an opinion):
#   { "hookSpecificOutput": {
#       "hookEventName": "PreToolUse",
#       "permissionDecision": "allow|deny|ask"
#     },
#     "systemMessage": "..." }
# Exit codes:
#   0 — no opinion, or explicit allow/ask
#   2 — deny
#
# The hot path (AFK off) stays in bash so hook latency stays low — we
# only spawn Python when AFK is actually on.

set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"

# Pull the hook input off stdin now so we can pipe it through later.
INPUT="$(cat)"

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0
AFK_FILE="$PROJECT_ROOT/.otaman/afk"

# Fast path: no AFK file → no opinion, native prompt.
[[ -f "$AFK_FILE" ]] || exit 0

# Slow path: AFK on. Delegate to Python for the daemon round-trip.
# Pick the Python interpreter the rest of otaman uses.
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v py >/dev/null 2>&1; then
    PY="py -3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    # No interpreter → fail-safe exit.
    echo "otaman bridge: no python interpreter on PATH; native prompt fallback" >&2
    exit 0
fi

# Pipe the original JSON input into the Python helper.
printf '%s' "$INPUT" | ${PY} "$HOOK_DIR/../scripts/bridge_approval.py"
