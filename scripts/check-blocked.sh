#!/usr/bin/env bash
# PreToolUse hook: BLOCKS writes when agent has blocked tasks.
#
# When an agent has proposed a spec change and is waiting for approval,
# their tasks are recorded in .agents/blocked/{agent}.md. This hook
# prevents the agent from implementing against specs that don't exist yet.
#
# Input: JSON via stdin (PreToolUse protocol)
# Output: JSON block response or silent allow
#
# Exit codes:
#   0 — allow (no blocked tasks)
#   2 — block (agent has blocked tasks)

set -euo pipefail

# Read stdin (required by hook protocol)
INPUT="$(cat)"

# Find otaman root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_resolve.sh"

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0

# Resolve agent identity via priority chain: OTAMAN_AGENT env > .otaman agent: field > current-agent fallback
AGENT="$(resolve_agent_identity "$PROJECT_ROOT")" || exit 0
[[ -n "$AGENT" ]] || exit 0

# Check blocked tasks file
BLOCKED_FILE="$PROJECT_ROOT/.agents/blocked/$AGENT.md"
[[ -f "$BLOCKED_FILE" ]] || exit 0

# Count blocked tasks (look for ## Blocked: headers)
COUNT=$(grep -c '^## Blocked:' "$BLOCKED_FILE" 2>/dev/null) || COUNT=0
[[ "$COUNT" -eq 0 ]] && exit 0

# Extract blocked task names (up to 5 for the message)
TASKS="$(sed -n 's/^## Blocked: \(.*\)/\1/p' "$BLOCKED_FILE" | head -5 | tr '\n' ', ' | sed 's/, $//')"

# Build block message
MSG="BLOCKED: You have ${COUNT} blocked task(s): ${TASKS}. "
MSG="${MSG}You CANNOT write code for blocked tasks until specs are approved. "
MSG="${MSG}Run /otaman:check to see if your proposals were approved. "
MSG="${MSG}To unblock: wait for spec-change-approved + spec-change messages, then clear .agents/blocked/${AGENT}.md"

# Escape for JSON
MSG="$(echo "$MSG" | sed 's/"/\\"/g')"

echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\"},\"systemMessage\":\"${MSG}\"}"
exit 2
