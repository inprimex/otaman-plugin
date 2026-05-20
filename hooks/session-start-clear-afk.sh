#!/usr/bin/env bash
# SessionStart: auto-clear any active AFK so a fresh Claude session lands
# on the native prompt path. The user is launching Claude — they're at a
# keyboard, so previously-set "I'm away" state should not block them.
#
# Sources cleared: manual, idle-auto, ssh-auto, unattended (and any
# leftover entry whose source field we don't recognise — better to err
# toward "back at keyboard").
#
# Skip rules:
#   OTAMAN_UNATTENDED=1  — launcher flagged this connection unattended;
#                           ssh-auto-afk.sh runs after us and would re-set
#                           the file anyway, so skipping avoids a confusing
#                           "cleared then enabled" notification pair.
#   OTAMAN_AFK_AUTO=0    — global kill switch (mirrors ssh-auto-afk.sh).
#
# A best-effort Telegram notification fires via afk.py's notify path so
# the user sees the auto-clear from their phone too.
#
# Diagnostics: appends a line to <otaman-root>/.otaman/session-start-clear-afk.log
# describing whether the hook fired or skipped and why.
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"
# shellcheck source=../scripts/_log.sh
source "$HOOK_DIR/../scripts/_log.sh"

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0
LOG_DIR="$PROJECT_ROOT/.otaman"
LOG_FILE="$LOG_DIR/session-start-clear-afk.log"
mkdir -p "$LOG_DIR" 2>/dev/null || true
rotate_log "$LOG_FILE"

NOW="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"

_log() {
    printf '%s  %s\n' "$NOW" "$1" >> "$LOG_FILE" 2>/dev/null || true
}

_unattended="${OTAMAN_UNATTENDED:-<unset>}"
_afk_auto="${OTAMAN_AFK_AUTO:-<unset>}"

_log "hook fired (OTAMAN_UNATTENDED=$_unattended OTAMAN_AFK_AUTO=$_afk_auto)"

if [[ "${OTAMAN_AFK_AUTO:-1}" == "0" ]]; then
    _log "skipped: OTAMAN_AFK_AUTO=0 (kill switch)"
    exit 0
fi

if [[ "${OTAMAN_UNATTENDED:-}" == "1" ]]; then
    _log "skipped: OTAMAN_UNATTENDED=1 (ssh-auto-afk.sh will set state)"
    exit 0
fi

AFK_FILE="$PROJECT_ROOT/.otaman/afk"
if [[ ! -f "$AFK_FILE" ]]; then
    _log "no AFK file — nothing to clear"
    exit 0
fi

# Capture the prior source for the notification body before we delete.
PRIOR_SOURCE="$(sed -n 's/^source:[[:space:]]*//p' "$AFK_FILE" | head -1 | tr -d '\r\n' | tr -d ' ')"

if rm -f "$AFK_FILE" 2>/dev/null; then
    _log "CLEARED AFK (prior source=${PRIOR_SOURCE:-unknown})"
    printf 'otaman: AFK auto-cleared (new Claude session — back to local prompts).\n' >&2
else
    _log "rm failed: $AFK_FILE"
    exit 0
fi

# Best-effort Telegram notification — silent if no daemon is running.
if command -v python3 >/dev/null 2>&1; then
    _PY="python3"
elif command -v py >/dev/null 2>&1; then
    _PY="py -3"
elif command -v python >/dev/null 2>&1; then
    _PY="python"
else
    _PY=""
fi
if [[ -n "$_PY" ]]; then
    ${_PY} "$HOOK_DIR/../scripts/afk.py" _send-event cleared \
        --source "${PRIOR_SOURCE:-}" \
        --reason "new Claude session started" \
        >/dev/null 2>&1 &
    disown 2>/dev/null || true
fi

exit 0
