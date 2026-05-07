#!/usr/bin/env bash
# SessionEnd: clear auto-enabled AFK so unattended-session state doesn't
# leak into the next interactive local session on the same machine.
#
# Clears AFK entries whose ``source:`` is ``unattended``, ``ssh-auto`` (legacy
# naming, kept for backwards-compat with AFK files written by old hook
# versions), or ``idle-auto``. Manually set AFK (``source: manual``) survives
# untouched so explicit TTLs / indefinite settings aren't lost.
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0

AFK_FILE="$PROJECT_ROOT/.otaman/afk"
[[ -f "$AFK_FILE" ]] || exit 0

# Check source line. sed pattern mirrors check-ownership.sh idiom.
SOURCE="$(sed -n 's/^source:[[:space:]]*//p' "$AFK_FILE" | head -1 | tr -d '\r\n' | tr -d ' ')"
case "$SOURCE" in
    unattended|ssh-auto|idle-auto)
        rm -f "$AFK_FILE" 2>/dev/null || true
        ;;
esac
exit 0
