#!/usr/bin/env bash
# Stop event: surface Claude's end-of-turn question to Telegram when AFK.
# Fast-path: if no AFK flag file, exit 0 immediately (no Python startup
# cost on every Stop — and Stop fires at the end of every Claude turn).
#
# Input (stdin): JSON from Claude Code with session_id + transcript_path.
# Output: none on stdout (this is a notification, not a decision).
# Fail-safe: any error path exits 0. Never breaks the session.
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"

INPUT="$(cat)"

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0
AFK_FILE="$PROJECT_ROOT/.otaman/afk"
[[ -f "$AFK_FILE" ]] || exit 0

# Pick Python (same logic as bridge-approval.sh).
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v py >/dev/null 2>&1; then
    PY="py -3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    exit 0
fi

printf '%s' "$INPUT" | ${PY} "$HOOK_DIR/../scripts/stop_notify.py" || true
exit 0
