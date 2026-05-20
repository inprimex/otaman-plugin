#!/usr/bin/env bash
# SessionStart: auto-enable AFK for sessions explicitly flagged as
# unattended by the launcher.
#
# Previously this hook triggered on any SSH session (SSH_CONNECTION
# or SSH_TTY being set) on the assumption that SSH meant "remote and
# away." That misfired when the human was actively launching tabs
# via a cross-machine launcher — they were *at* the terminal despite
# the session being SSH. Current contract:
#
#   - Fires **only** when ``OTAMAN_UNATTENDED=1`` is set. The launcher
#     exports this when a connection in launch-settings.yaml declares
#     ``unattended: true`` (e.g. long-lived agents on a box nobody's
#     watching). Interactive SSH tabs do NOT set it and stay local.
#   - Pure SSH env vars (``SSH_CONNECTION``, ``SSH_TTY``,
#     ``OTAMAN_LAUNCHER_SSH``) are recorded in the diagnostic log but
#     no longer trigger on their own.
#   - ``OTAMAN_AFK_AUTO=0`` still turns the hook into a no-op (full
#     opt-out, useful for tests or quick kill-switch).
#   - Existing AFK files are never clobbered (manual > auto).
#
# Diagnostics: every invocation appends a line to
# ``<otaman-root>/.otaman/ssh-auto-afk.log`` recording what env vars
# it saw and what decision it made.
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"
# shellcheck source=../scripts/_log.sh
source "$HOOK_DIR/../scripts/_log.sh"

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0
LOG_FILE="$PROJECT_ROOT/.otaman/ssh-auto-afk.log"
LOG_DIR="$PROJECT_ROOT/.otaman"
mkdir -p "$LOG_DIR" 2>/dev/null || true
rotate_log "$LOG_FILE"

NOW="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"

# Gather diagnostic snapshot.
_ssh_conn="${SSH_CONNECTION:-<unset>}"
_ssh_tty="${SSH_TTY:-<unset>}"
_launcher_ssh="${OTAMAN_LAUNCHER_SSH:-<unset>}"
_unattended="${OTAMAN_UNATTENDED:-<unset>}"
_afk_auto="${OTAMAN_AFK_AUTO:-<unset>}"

_log() {
    # Best-effort append; log-write failures never fail the hook.
    printf '%s  %s\n' "$NOW" "$1" >> "$LOG_FILE" 2>/dev/null || true
}

_log "hook fired (OTAMAN_UNATTENDED=$_unattended SSH_CONNECTION=$_ssh_conn SSH_TTY=$_ssh_tty OTAMAN_LAUNCHER_SSH=$_launcher_ssh OTAMAN_AFK_AUTO=$_afk_auto)"

# Env-var opt-out (kill switch).
if [[ "${OTAMAN_AFK_AUTO:-1}" == "0" ]]; then
    _log "skipped: OTAMAN_AFK_AUTO=0"
    exit 0
fi

# Only act when the launcher explicitly declared this session unattended.
# Interactive SSH tabs (the common launcher case) don't set this, so the
# human stays on the native prompt despite being in an SSH session.
if [[ "${OTAMAN_UNATTENDED:-}" != "1" ]]; then
    _log "skipped: OTAMAN_UNATTENDED!=1 (SSH presence alone no longer triggers)"
    exit 0
fi
_sig="OTAMAN_UNATTENDED"

AFK_FILE="$PROJECT_ROOT/.otaman/afk"
if [[ -f "$AFK_FILE" ]]; then
    _log "skipped: AFK already set (preserving existing state)"
    exit 0
fi

USER_LABEL="${USER:-${USERNAME:-unknown}}"
cat > "$AFK_FILE" <<EOF
enabled_at: $NOW
source: unattended
signal: $_sig
enabled_by: $USER_LABEL
EOF

_log "ENABLED AFK (source=unattended, signal=$_sig, by=$USER_LABEL)"
printf 'otaman: AFK auto-enabled (connection flagged unattended). '\
'Approvals route via daemon; disable with `otaman afk off` if this host is manned.\n' >&2

# Best-effort Telegram notification — fires only if a daemon is up for
# this account. Never fails the hook (background + redirected output).
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
    ${_PY} "$HOOK_DIR/../scripts/afk.py" _send-event enabled \
        --reason "launcher flagged this connection as unattended" \
        >/dev/null 2>&1 &
    disown 2>/dev/null || true
fi

exit 0
