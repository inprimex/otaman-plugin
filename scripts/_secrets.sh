#!/usr/bin/env bash
# Shared secrets helper for maestro bash scripts and hooks.
#
# Loads .maestro/secrets.env (if present) into the current shell, respecting
# existing values — env vars already set by the user win over dotenv contents.
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/_secrets.sh"
#   load_maestro_secrets "$MAESTRO_ROOT"

load_maestro_secrets() {
    local maestro_root="${1:-}"
    [[ -z "$maestro_root" ]] && return 0

    local dotenv="$maestro_root/.maestro/secrets.env"
    [[ -f "$dotenv" ]] || return 0

    # Mode check — warn if looser than 0600/0400. Not fatal; some
    # filesystems (WSL on DrvFs, network mounts) don't track modes cleanly.
    local mode=""
    if command -v stat >/dev/null 2>&1; then
        mode="$(stat -c '%a' "$dotenv" 2>/dev/null \
                || stat -f '%A' "$dotenv" 2>/dev/null \
                || true)"
    fi
    if [[ -n "$mode" && "$mode" != "600" && "$mode" != "400" ]]; then
        printf 'maestro: warning: %s has mode %s; expected 600 or 400\n' \
            "$dotenv" "$mode" >&2
    fi

    local line key val
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Trim leading whitespace.
        line="${line#"${line%%[![:space:]]*}"}"
        # Skip blank and comment lines.
        [[ -z "$line" || "$line" == \#* ]] && continue
        # Require KEY=VALUE shape.
        [[ "$line" != *"="* ]] && continue

        key="${line%%=*}"
        val="${line#*=}"

        # Trim trailing whitespace from key.
        key="${key%"${key##*[![:space:]]}"}"
        [[ -z "$key" ]] && continue

        # Strip matching surrounding quotes on the value.
        if [[ ${#val} -ge 2 ]]; then
            local first="${val:0:1}"
            local last="${val: -1}"
            if [[ "$first" == '"' && "$last" == '"' ]] \
                || [[ "$first" == "'" && "$last" == "'" ]]; then
                val="${val:1:${#val}-2}"
            fi
        fi

        # Don't overwrite values already set by the shell (env > dotenv).
        if [[ -z "${!key:-}" ]]; then
            export "$key=$val"
        fi
    done < "$dotenv"
}
