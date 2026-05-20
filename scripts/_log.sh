#!/usr/bin/env bash
# Shared logging utility for otaman/maestro bash hooks.
#
# Currently exports: rotate_log
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/_log.sh"
#   rotate_log "$LOG_FILE"               # 1 MiB threshold, keep 3 backups
#   rotate_log "$LOG_FILE" 2097152       # custom max bytes (2 MiB)
#   rotate_log "$LOG_FILE" 1048576 5     # custom max bytes + backup count
#
# Env overrides (apply when args 2/3 are omitted):
#   OTAMAN_LOG_MAX_BYTES   (default 1048576)
#   OTAMAN_LOG_KEEP        (default 3)
#
# Behavior:
#   * No-op if the log file doesn't exist or is under the threshold.
#   * Otherwise: drop <log>.<keep>, shift <log>.N -> <log>.(N+1) for N=keep-1..1,
#     then <log> -> <log>.1. The caller's next append starts a fresh file.
#   * All filesystem ops use ``2>/dev/null || true`` — rotation failures never
#     break the calling hook.

rotate_log() {
    local log_file="$1"
    local max_bytes="${2:-${OTAMAN_LOG_MAX_BYTES:-1048576}}"
    local keep="${3:-${OTAMAN_LOG_KEEP:-3}}"

    [[ -n "$log_file" ]] || return 0
    [[ -f "$log_file" ]] || return 0

    # Portable file size: GNU coreutils stat then BSD stat fallback.
    local size=""
    if command -v stat >/dev/null 2>&1; then
        size="$(stat -c '%s' "$log_file" 2>/dev/null \
                || stat -f '%z' "$log_file" 2>/dev/null \
                || true)"
    fi
    [[ -n "$size" ]] || return 0
    # Bash arithmetic — guard against non-numeric stat output.
    [[ "$size" =~ ^[0-9]+$ ]] || return 0
    (( size < max_bytes )) && return 0

    # Drop the oldest backup, then shift each .N to .(N+1), then base -> .1.
    rm -f -- "${log_file}.${keep}" 2>/dev/null || true
    local i
    for (( i = keep - 1; i >= 1; i-- )); do
        if [[ -f "${log_file}.${i}" ]]; then
            mv -f -- "${log_file}.${i}" "${log_file}.$((i + 1))" 2>/dev/null || true
        fi
    done
    mv -f -- "$log_file" "${log_file}.1" 2>/dev/null || true
}
