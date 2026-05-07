#!/usr/bin/env bash
# UserPromptSubmit: record the timestamp of the most recent human prompt.
#
# Used by the bridge daemon's IdleAFKMonitor (bridge/idle_afk.py) to tell
# "user is actively driving Claude" from "user walked away."
#
# The file lives at ``<otaman-root>/.otaman/last-user-activity`` and
# contains one ISO-8601 UTC timestamp. Writing it is idempotent and
# non-blocking — any failure is swallowed so a flaky filesystem can never
# stall Claude's prompt submission.
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0

STATE_DIR="$PROJECT_ROOT/.otaman"
mkdir -p "$STATE_DIR" 2>/dev/null || true

NOW="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
ACTIVITY_FILE="$STATE_DIR/last-user-activity"

# Atomic-ish write via temp + rename so a reader never sees a half-written
# line. Best-effort — if anything fails we just skip.
TMP="$ACTIVITY_FILE.tmp.$$"
{ printf '%s\n' "$NOW" > "$TMP" && mv -f "$TMP" "$ACTIVITY_FILE"; } 2>/dev/null || \
    rm -f "$TMP" 2>/dev/null || true

exit 0
