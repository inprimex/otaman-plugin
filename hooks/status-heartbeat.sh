#!/usr/bin/env bash
# status-heartbeat 1.1 — refresh this agent's status `updated_at` while its
# session is alive, so cli's staleness rule (otaman_cli.status.staleness, 1.2)
# can tell "working for eight hours" from "died eight hours ago".
#
# Measured 2026-09-16: `updated_at == since` for EVERY live record — nothing
# refreshed a record after its state was set, so a crashed session kept
# claiming work indefinitely and `otaman status` reported a dead fleet as busy.
# cli's half renders STALE past the TTL; this half is what keeps a LIVE session
# from being falsely accused by that rule. Both halves are needed: render-time
# truth alone would flip every long-running session to STALE.
#
# Wired to BOTH UserPromptSubmit and PreToolUse. Prompts alone are not enough —
# an agent working autonomously for hours (the fleet's normal mode) submits
# almost no prompts while making constant tool calls, and would go falsely STALE
# on a prompt-only heartbeat. Tool calls alone would miss a session sitting at
# an idle prompt. Together they cover both, which is why the spec says "while
# the session lives" rather than naming one hook.
#
# THROTTLED, per the task's explicit "no per-call write amplification": the
# common path is one `stat` and an integer compare, then exit — no fork, no
# parse, no write. Only once per HEARTBEAT_INTERVAL does it rewrite the file.
# This matters because PreToolUse fires on every single Bash/Write/Edit; the
# repo already has a documented incident (PR #72) where a per-call hook blew
# the UserPromptSubmit timeout on a real workspace.
#
# The file's own mtime IS the throttle clock — this hook is the only writer
# that touches a record without changing its state, and any OTHER writer
# (`otaman set-status`) sets updated_at at the same moment it rewrites the
# file. So mtime and updated_at cannot drift, and using mtime avoids parsing a
# timestamp on the hot path entirely.
#
# Scope is `working` and `waiting` ONLY — deliberately identical to
# staleness.py's STALEABLE frozenset. Heartbeating an `idle` or `blocked`
# record would be pointless (neither is ever rendered STALE) and actively
# wrong for `human`/`afk`, a deliberate 89-day-old human state that must not
# look like a live session.
#
# Never blocks and never speaks: every failure path exits 0 silently. A hook
# that cannot refresh a timestamp must not be able to stall a tool call or
# inject text into the transcript.
set -u

# Seconds between refreshes. Default 300 against cli's 1800s default TTL — 6x
# headroom, so a single long operation (full test run, large clone) can never
# flip a live session to STALE, while a dead one still stops claiming work
# within the hour. Overridable for tests.
HEARTBEAT_INTERVAL="${OTAMAN_HEARTBEAT_INTERVAL:-300}"

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh" 2>/dev/null || exit 0

# Hook protocol: stdin carries the event JSON. Read it so the writer never
# gets EPIPE, and pull `cwd` for identity + root resolution (same extraction
# bus-status-hook.sh uses — one sed, on a string already in memory).
INPUT="$(cat 2>/dev/null)"
CWD="$(printf '%s' "$INPUT" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
[[ -z "$CWD" ]] && CWD="$PWD"

ROOT="$(find_maestro_root "$CWD" 2>/dev/null)" || exit 0

# Identity: the same zero-subprocess chain the other latency-sensitive hooks
# use (per-repo CLAUDE.md sniff, then the OTAMAN_AGENT spawn override).
# NOT resolve_agent_identity() — that spawns python3 to import otaman_core,
# which is correct for a git hook that runs once per commit but not for one
# on every tool call. team-mode B1 retired .agents/current-agent; it is
# deliberately not consulted here either.
AGENT=""
if [[ -f "$CWD/CLAUDE.md" ]]; then
    AGENT="$(sed -n 's/.*You are `\([^`]*\)`.*/\1/p' "$CWD/CLAUDE.md" | head -1)"
fi
[[ -z "$AGENT" && -n "${OTAMAN_AGENT:-}" ]] && AGENT="$OTAMAN_AGENT"
[[ -z "$AGENT" ]] && exit 0

STATUS_FILE="$ROOT/.agents/status/$AGENT.yaml"
# No record means set-status has never run for this agent. Creating one here
# would invent a state nobody declared — the heartbeat refreshes an existing
# claim, it never makes one.
[[ -f "$STATUS_FILE" ]] || exit 0

# ---- Throttle (the hot path: stat + compare, then exit) --------------------
NOW_EPOCH="$(printf '%(%s)T' -1 2>/dev/null)" || NOW_EPOCH=""
if [[ -z "$NOW_EPOCH" ]]; then
    NOW_EPOCH="$(date +%s 2>/dev/null)" || exit 0
fi

# GNU stat and BSD/macOS stat disagree on flags; try both, give up quietly.
FILE_EPOCH="$(stat -c %Y "$STATUS_FILE" 2>/dev/null)" \
    || FILE_EPOCH="$(stat -f %m "$STATUS_FILE" 2>/dev/null)" \
    || exit 0
[[ "$FILE_EPOCH" =~ ^[0-9]+$ ]] || exit 0

(( NOW_EPOCH - FILE_EPOCH < HEARTBEAT_INTERVAL )) && exit 0

# ---- Refresh path (at most once per interval) ------------------------------
# Only states that CLAIM a live session are heartbeat-eligible; see the header.
STATE=""
while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == state:* ]]; then
        STATE="${line#state:}"
        STATE="${STATE#"${STATE%%[![:space:]]*}"}"   # ltrim
        STATE="${STATE%"${STATE##*[![:space:]]}"}"   # rtrim
        STATE="${STATE//\'/}"
        STATE="${STATE//\"/}"
        break
    fi
done < "$STATUS_FILE"

[[ "$STATE" == "working" || "$STATE" == "waiting" ]] || exit 0

# TZ=UTC0 is load-bearing, not decoration: bash's printf %()T formats in LOCAL
# time, so a bare `printf '%(...Z)T'` stamps local time and mislabels it `Z`.
# Caught live on this host (UTC+3): the hook wrote a stamp 3h in the FUTURE.
# In a negative-offset zone it fails the dangerous way instead — a US agent
# (UTC-8) would write stamps 8h in the past, blowing straight through cli's
# 1800s TTL and rendering every LIVE session STALE, i.e. exactly the defect
# this change exists to remove, reintroduced by its own fix.
NOW_ISO="$(TZ=UTC0 printf '%(%Y-%m-%dT%H:%M:%SZ)T' -1 2>/dev/null)" || NOW_ISO=""
if [[ -z "$NOW_ISO" ]]; then
    NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" || exit 0
fi

# Rewrite in place, replacing only the updated_at line and preserving the rest
# byte-for-byte. Deliberately NOT a yaml load/dump round-trip: this hook must
# never be able to reformat, reorder, or drop a field it does not understand
# from a record whose real owner is cli's FileStatusBackend.
TMP="$STATUS_FILE.hb.$$"
{
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == updated_at:* ]]; then
            printf "updated_at: '%s'\n" "$NOW_ISO"
        else
            printf '%s\n' "$line"
        fi
    done < "$STATUS_FILE"
} > "$TMP" 2>/dev/null || { rm -f "$TMP" 2>/dev/null; exit 0; }

# Atomic swap so a concurrent reader never sees a half-written record.
mv -f "$TMP" "$STATUS_FILE" 2>/dev/null || rm -f "$TMP" 2>/dev/null

exit 0
