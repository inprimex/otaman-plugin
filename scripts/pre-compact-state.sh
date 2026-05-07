#!/usr/bin/env bash
# Pre-compact hook: saves agent session state before context compression.
# This allows agents to resume context after compaction.
#
# Saves to: .agents/sessions/{agent-name}.md
# Reads: current-agent, queue, recent bus messages, git status

set -euo pipefail

# Find project root (shared resolver)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_resolve.sh"

ROOT="$(find_maestro_root 2>/dev/null)" || exit 0

# Determine agent identity
AGENT=""
if [ -f "CLAUDE.md" ]; then
    AGENT=$(grep -oP 'You are `\K[^`]+' CLAUDE.md 2>/dev/null || true)
fi
if [ -z "$AGENT" ] && [ -f "$ROOT/.agents/current-agent" ]; then
    AGENT=$(cat "$ROOT/.agents/current-agent" 2>/dev/null | tr -d '[:space:]')
fi

[ -z "$AGENT" ] && exit 0

# Create sessions directory
SESSIONS_DIR="$ROOT/.agents/sessions"
mkdir -p "$SESSIONS_DIR"

STATE_FILE="$SESSIONS_DIR/$AGENT.md"

# Build state snapshot
{
    echo "# Session State — $AGENT"
    echo "**Saved**: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "**Reason**: pre-compact (context compression)"
    echo ""

    # Current queue
    QUEUE_FILE="$ROOT/.agents/queue/$AGENT.md"
    if [ -f "$QUEUE_FILE" ]; then
        echo "## Task Queue"
        cat "$QUEUE_FILE"
        echo ""
    fi

    # Pending bus messages
    BUS_DIR="$ROOT/.agents/bus/active"
    if [ -d "$BUS_DIR" ]; then
        PENDING=0
        echo "## Pending Bus Messages"
        for msg in "$BUS_DIR"/*.md; do
            [ -f "$msg" ] || continue
            TO=$(grep -m1 '^to:' "$msg" 2>/dev/null | sed 's/^to: *//' || true)
            if [ "$TO" = "$AGENT" ] || [ "$TO" = "all" ]; then
                STEM=$(basename "$msg" .md)
                ACK_FILE="$BUS_DIR/acks/$STEM.$AGENT.ack"
                if [ ! -f "$ACK_FILE" ]; then
                    SUBJECT=$(grep -m1 '^## ' "$msg" 2>/dev/null | sed 's/^## //' || echo "(no subject)")
                    echo "- $STEM: $SUBJECT"
                    PENDING=$((PENDING + 1))
                fi
            fi
        done
        [ "$PENDING" -eq 0 ] && echo "_(none)_"
        echo ""
    fi

    # Git status (brief)
    echo "## Git Status"
    if command -v git >/dev/null 2>&1; then
        BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
        echo "Branch: $BRANCH"
        MODIFIED=$(git diff --name-only 2>/dev/null | head -10)
        if [ -n "$MODIFIED" ]; then
            echo "Modified files:"
            echo "$MODIFIED" | sed 's/^/  - /'
        else
            echo "Working tree clean"
        fi
    fi
    echo ""

    # Blocked tasks
    BLOCKED_FILE="$ROOT/.agents/blocked/$AGENT.md"
    if [ -f "$BLOCKED_FILE" ]; then
        echo "## Blocked Tasks"
        cat "$BLOCKED_FILE"
        echo ""
    fi

} > "$STATE_FILE"

echo "Session state saved to .agents/sessions/$AGENT.md"
