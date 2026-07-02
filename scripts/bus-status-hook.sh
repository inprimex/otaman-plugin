#!/usr/bin/env bash
# Otaman UserPromptSubmit hook — injects pending bus message count
# into Claude's context before each prompt is processed.
# Designed for speed: minimal file I/O, no Python, no jq.
set -euo pipefail

# Read stdin (required by hook protocol)
INPUT="$(cat)"

# Extract cwd
CWD="$(echo "$INPUT" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
[[ -z "$CWD" ]] && exit 0

# Cross-platform path normalization (WSL ↔ Git Bash)
if [[ "$CWD" == /mnt/* ]] && [[ ! -d "$CWD" ]]; then
    alt="/$(echo "$CWD" | sed 's|^/mnt/||')"
    [[ -d "$alt" ]] && CWD="$alt"
elif [[ "$CWD" == /[a-zA-Z]/* ]] && [[ ! -d "$CWD" ]]; then
    alt="/mnt/${CWD:1}"
    [[ -d "$alt" ]] && CWD="$alt"
fi

# Find project root (shared resolver)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_resolve.sh"

ROOT="$(find_maestro_root "$CWD" 2>/dev/null)" || exit 0
[[ ! -d "$ROOT/.agents/bus/active" ]] && exit 0

BUS="$ROOT/.agents/bus/active"
ACKS="$BUS/acks"

# Determine agent identity.
# Priority: CWD's CLAUDE.md (per-repo, set by generate-agent-config.py) →
#          .agents/current-agent (project-global fallback).
# This used to be inverted — current-agent first — which leaked the last
# `otaman set-agent` value into every tab and made the [otaman] N pending
# line wrong in 7/8 tabs of the 2026-04-29 incident.
AGENT=""
if [[ -f "$CWD/CLAUDE.md" ]]; then
    AGENT="$(sed -n 's/.*You are `\([^`]*\)`.*/\1/p' "$CWD/CLAUDE.md" | head -1)"
fi

if [[ -z "$AGENT" && -f "$ROOT/.agents/current-agent" ]]; then
    AGENT="$(tr -d '[:space:]' < "$ROOT/.agents/current-agent")"
fi

[[ -z "$AGENT" ]] && exit 0

# Count pending messages for this agent (fast: one pass over filenames + ack check)
#
# Pure-bash string handling below (no sed/head/tr/cat/basename forks) is
# deliberate, not stylistic: bus/active/ accumulates every message ever
# sent (resolving a message writes a .ack file; it never moves or prunes
# the underlying .md), so this loop's iteration count is the project's
# *entire* bus history, not just pending messages -- 1300+ files in a
# lived-in project. The original per-file sed|head|tr pipeline forked
# ~8 subprocesses per file (~11,000 forks at that scale), which is what
# blew the 5s UserPromptSubmit timeout. Builtins turn each iteration into
# in-process string ops with zero forks.
PENDING=0
URGENT=0

for msg in "$BUS"/*.md; do
    [[ -f "$msg" ]] || continue
    stem="${msg##*/}"
    stem="${stem%.md}"

    # Check ack — skip if resolved
    ackfile="$ACKS/${stem}.${AGENT}.ack"
    if [[ -f "$ackfile" ]]; then
        IFS= read -r ack < "$ackfile" || ack=""
        [[ "$ack" == *"resolved"* ]] && continue
    fi

    # Extract `to:` and `priority:` in one pass over the first 15 lines
    # (matches the original sed '1,15' + first-match-wins + whitespace-
    # strip semantics, including a stray trailing \r on CRLF files).
    to=""
    pri=""
    lineno=0
    while IFS= read -r line; do
        lineno=$((lineno + 1))
        if [[ -z "$to" && "$line" == to:* ]]; then
            to="${line#to:}"
            to="${to//[[:space:]]/}"
        elif [[ -z "$pri" && "$line" == priority:* ]]; then
            pri="${line#priority:}"
            pri="${pri//[[:space:]]/}"
        fi
        { [[ -n "$to" && -n "$pri" ]] || [[ $lineno -ge 15 ]]; } && break
    done < "$msg"

    # Check if addressed to this agent or all
    [[ "$to" != "$AGENT" && "$to" != "all" ]] && continue

    PENDING=$((PENDING + 1))
    [[ "$pri" == "urgent" || "$pri" == "high" ]] && URGENT=$((URGENT + 1))
done

# Check blocked tasks. `grep -c` exits 1 (no match) while still printing
# "0" to stdout, so `"$(grep -c ... || echo 0)"` was concatenating BOTH
# outputs into "0\n0" whenever the file existed with zero matches -- broke
# the `-gt` comparison below with "0: syntax error in expression". Assign
# first, then let `|| BLOCKED=0` overwrite on a genuine failure; it's a
# separate statement, not captured inside the same command substitution.
BLOCKED=0
[[ -f "$ROOT/.agents/blocked/${AGENT}.md" ]] && {
    BLOCKED="$(grep -c '^## Blocked:' "$ROOT/.agents/blocked/${AGENT}.md" 2>/dev/null)" || BLOCKED=0
}

# Only inject context if there's something noteworthy
[[ "$PENDING" -eq 0 && "$BLOCKED" -eq 0 ]] && exit 0

# Build status line
STATUS="[otaman] ${PENDING} pending message(s)"
[[ "$URGENT" -gt 0 ]] && STATUS="${STATUS} (${URGENT} urgent)"
[[ "$BLOCKED" -gt 0 ]] && STATUS="${STATUS}, ${BLOCKED} blocked task(s)"
STATUS="${STATUS}. Run /otaman:check for details."

# Escape for JSON
STATUS="$(echo "$STATUS" | sed 's/"/\\"/g')"

echo "{\"systemMessage\":\"${STATUS}\"}"
exit 0
