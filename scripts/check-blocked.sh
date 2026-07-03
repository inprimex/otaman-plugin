#!/usr/bin/env bash
# PreToolUse hook: blocks writes to CODE for a blocked task while its spec
# proposal is still pending approval.
#
# When an agent proposes a spec change and is waiting for approval, its
# tasks are recorded in .agents/blocked/{agent}.md. This hook prevents the
# agent from implementing against specs that don't exist yet.
#
# Scoping (issue #73): the deny is scoped two ways so a pending proposal
# never freezes *all* editing:
#   1. Self-heal — a blocked entry whose proposal already has an
#      approved/rejected human ack on the bus is treated as resolved and no
#      longer blocks, even if the entry hasn't been tombstoned in the file
#      yet. (Cheap: one ack-file stat per entry, never a bus scan.)
#   2. Path scope — only writes whose target is inside a repo THIS agent
#      owns are denied (that's where "implementing against specs" happens).
#      Coordination data (.agents/** bus/blocked/queue), scratchpad/tmp, and
#      other repos are always allowed. Editing your own blocked file to
#      clear it, or writing a scratch note, is never frozen.
#
# Input: JSON via stdin (PreToolUse protocol). Only Write|Edit reach this
#        hook (see hooks.json matcher), so tool_input.file_path is present.
# Output: JSON deny (exit 0) or silent allow (exit 0).
#
# Deny surfaces the reason via BOTH permissionDecisionReason (to the model)
# and systemMessage (to the operator), and exits 0 — NOT exit 2. Exit 2
# makes Claude Code ignore stdout JSON and use (empty) stderr, which is why
# the old "echo JSON; exit 2" form showed only a generic "denied" with no
# reason (issue #73).
#
# Exit codes:
#   0 — always (allow = no output; deny = JSON on stdout)

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

BUS_ACKS="$PROJECT_ROOT/.agents/bus/active/acks"

# --- Collect ACTIVE blocked entries (self-heal resolved ones) --------------
# An entry starts at a line-leading `## Blocked:` header and owns the
# following `- **Proposal**:` line. Tombstoned entries begin with
# `<!-- ## Blocked:` so their header is not line-leading and never matches.
# An entry is "resolved" (skipped) when its proposal has an approved/rejected
# human ack on the bus — the same signal /otaman:approve writes.
ACTIVE_TITLES=""
ACTIVE_COUNT=0
_cur_title=""
_cur_proposal=""

_flush_entry() {
    if [[ -n "$_cur_title" ]]; then
        local resolved=0
        if [[ -n "$_cur_proposal" ]]; then
            local ackfile="$BUS_ACKS/${_cur_proposal}.human.ack"
            if [[ -f "$ackfile" ]]; then
                local ackc=""
                ackc="$(cat "$ackfile" 2>/dev/null || true)"
                if [[ "$ackc" == *approved* || "$ackc" == *rejected* ]]; then
                    resolved=1
                fi
            fi
        fi
        if [[ "$resolved" -eq 0 ]]; then
            ACTIVE_COUNT=$((ACTIVE_COUNT + 1))
            if [[ -z "$ACTIVE_TITLES" ]]; then
                ACTIVE_TITLES="$_cur_title"
            else
                ACTIVE_TITLES="$ACTIVE_TITLES, $_cur_title"
            fi
        fi
    fi
    _cur_title=""
    _cur_proposal=""
    return 0
}

while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == '## Blocked: '* ]]; then
        _flush_entry
        _cur_title="${line#'## Blocked: '}"
    elif [[ "$line" == *'**Proposal**:'* ]]; then
        p="${line#*'**Proposal**:'}"
        p="${p#"${p%%[![:space:]]*}"}"   # trim leading whitespace
        p="${p%%[[:space:]]*}"           # first whitespace-delimited token
        _cur_proposal="$p"
    fi
done < "$BLOCKED_FILE"
_flush_entry

# No active (unresolved) blocks → nothing to enforce.
[[ "$ACTIVE_COUNT" -eq 0 ]] && exit 0

# --- Resolve the write target ----------------------------------------------
json_get() {
    local json="$1" key="$2"
    echo "$json" | sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1
}

TARGET_PATH="$(json_get "$INPUT" "file_path")"
# No file_path (unexpected for Write/Edit) → can't scope, don't block.
[[ -n "$TARGET_PATH" ]] || exit 0

# Resolve to absolute (dir may exist even if the file is new).
if [[ -d "$(dirname "$TARGET_PATH" 2>/dev/null)" ]]; then
    TARGET_PATH="$(cd "$(dirname "$TARGET_PATH")" 2>/dev/null && pwd)/$(basename "$TARGET_PATH")" || true
fi
TARGET_PATH="${TARGET_PATH%/}"

# --- Is the target inside a repo THIS agent owns? --------------------------
OWNERSHIP_FILE="$PROJECT_ROOT/.agents/ownership.json"
# No ownership map → can't scope. Match check-ownership.sh's degraded
# behaviour (it also can't proceed) and ALLOW rather than blanket-deny.
[[ -f "$OWNERSHIP_FILE" ]] || exit 0

# Parse path/owner pairs (same order, 1:1) — mirrors check-ownership.sh.
REPO_PATHS="$(sed -n 's/.*"path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$OWNERSHIP_FILE")"
REPO_OWNERS="$(sed -n 's/.*"owner"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$OWNERSHIP_FILE")"

i=0
while IFS= read -r line; do PATHS_ARR[i]="$line"; i=$((i + 1)); done <<< "$REPO_PATHS"
i=0
while IFS= read -r line; do OWNERS_ARR[i]="$line"; i=$((i + 1)); done <<< "$REPO_OWNERS"

IN_OWNED_REPO=0
for idx in "${!PATHS_ARR[@]}"; do
    REPO_REL="${PATHS_ARR[$idx]}"
    REPO_OWNER="${OWNERS_ARR[$idx]:-}"
    [[ -n "$REPO_REL" && "$REPO_OWNER" == "$AGENT" ]] || continue
    REPO_ABS="$(cd "$PROJECT_ROOT/$REPO_REL" 2>/dev/null && pwd)" || continue
    if [[ "$TARGET_PATH" == "$REPO_ABS"/* || "$TARGET_PATH" == "$REPO_ABS" ]]; then
        IN_OWNED_REPO=1
        break
    fi
done

# Target is coordination data, scratchpad, or another agent's repo → allow.
# (Another agent's repo is denied separately by check-ownership.sh.)
[[ "$IN_OWNED_REPO" -eq 1 ]] || exit 0

# --- Deny: target is code in the agent's own repo, with an active block ----
REASON="BLOCKED: ${ACTIVE_COUNT} pending spec proposal(s) awaiting approval: ${ACTIVE_TITLES}. "
REASON="${REASON}Editing code in your own repo while a proposal is pending is treated as implementing against an unapproved spec. "
REASON="${REASON}Coordination files (.agents/ bus, blocked, queue), scratchpad, and other repos remain editable. "
REASON="${REASON}To proceed: wait for the spec-change-approved + spec-change messages (run /otaman:check), "
REASON="${REASON}or if a proposal is already approved/withdrawn, clear it with: otaman blocked --clear \"<title>\"."

# JSON-escape (backslashes first, then quotes; reason is single-line).
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
R_ESC="$(esc "$REASON")"

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"},"systemMessage":"%s"}\n' "$R_ESC" "$R_ESC"
exit 0
