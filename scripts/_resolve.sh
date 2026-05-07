#!/usr/bin/env bash
# Shared maestro root resolution for all bash hooks.
#
# Resolution chain (first match wins):
# 1. .maestro marker file in CWD or ancestors
# 2. MAESTRO_ROOT environment variable
# 3. Walk-up fallback: look for .agents/ownership.json (legacy compat)
#
# Usage: source this file, then call find_maestro_root
#   source "$(dirname "${BASH_SOURCE[0]}")/_resolve.sh"
#   ROOT="$(find_maestro_root)" || exit 0

find_maestro_root() {
    local dir="${1:-$PWD}"

    # 1. .maestro marker file — walk up looking for it
    local check="$dir"
    while [[ "$check" != "/" && "$check" != "." ]]; do
        # Check both .otaman (preferred) and .maestro (legacy) markers
        local marker=""
        if [[ -f "$check/.otaman" ]]; then
            marker="$check/.otaman"
        elif [[ -f "$check/.maestro" ]]; then
            marker="$check/.maestro"
        fi
        if [[ -n "$marker" ]]; then
            local rel
            rel="$(_parse_marker_field "$marker" maestro_root)"
            if [[ -n "$rel" ]]; then
                local candidate
                candidate="$(cd "$check/$rel" 2>/dev/null && pwd)" || true
                if [[ -n "$candidate" ]] && { [[ -f "$candidate/platform.yaml" ]] || [[ -d "$candidate/.agents" ]]; }; then
                    echo "$candidate"
                    return 0
                fi
            fi
        fi
        check="$(dirname "$check")"
    done

    # 2. OTAMAN_ROOT (preferred) or MAESTRO_ROOT (legacy) env var
    local env_root="${OTAMAN_ROOT:-${MAESTRO_ROOT:-}}"
    if [[ -n "$env_root" ]]; then
        if [[ -f "$env_root/platform.yaml" ]] || [[ -d "$env_root/.agents" ]]; then
            echo "$env_root"
            return 0
        fi
    fi

    # 3. Walk-up fallback (legacy layout)
    check="$dir"
    while [[ "$check" != "/" && "$check" != "." ]]; do
        if [[ -f "$check/.agents/ownership.json" ]] || [[ -f "$check/platform.yaml" ]]; then
            echo "$check"
            return 0
        fi
        check="$(dirname "$check")"
    done

    return 1
}

# Parse a .maestro marker file and echo the value of a known field.
#
# Usage: _parse_marker_field <marker_path> <field_name>
# Known fields: maestro_root, expected_account.
# Returns 0 with value on stdout if found, 1 otherwise.
#
# Legacy single-line markers (bare path) resolve to maestro_root for
# backwards compatibility. Unknown `key:` lines are ignored so Windows
# absolute paths (C:/foo) continue to parse as bare maestro_root values.
_parse_marker_field() {
    local marker="$1"
    local field="$2"
    [[ -f "$marker" ]] || return 1

    local line key val bare_path=""
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Trim leading whitespace.
        line="${line#"${line%%[![:space:]]*}"}"
        # Skip blank and comment lines.
        [[ -z "$line" || "$line" == \#* ]] && continue

        if [[ "$line" == *":"* ]]; then
            key="${line%%:*}"
            val="${line#*:}"
            # Trim whitespace on key and val.
            key="${key#"${key%%[![:space:]]*}"}"
            key="${key%"${key##*[![:space:]]}"}"
            val="${val#"${val%%[![:space:]]*}"}"
            val="${val%"${val##*[![:space:]]}"}"

            case "$key" in
                maestro_root|expected_account)
                    if [[ "$key" == "$field" ]]; then
                        echo "$val"
                        return 0
                    fi
                    continue
                    ;;
            esac
        fi

        # Bare line — candidate for maestro_root (keep first).
        [[ -z "$bare_path" ]] && bare_path="$line"
    done < "$marker"

    if [[ "$field" == "maestro_root" && -n "$bare_path" ]]; then
        echo "$bare_path"
        return 0
    fi
    return 1
}

# Walk up from a directory looking for a .maestro marker file.
#
# Usage: find_marker [start_dir]
# Echoes marker path if found, returns 1 otherwise.
find_marker() {
    local dir="${1:-$PWD}"
    local check="$dir"
    while [[ "$check" != "/" && "$check" != "." ]]; do
        if [[ -f "$check/.otaman" ]]; then
            echo "$check/.otaman"
            return 0
        elif [[ -f "$check/.maestro" ]]; then
            echo "$check/.maestro"
            return 0
        fi
        check="$(dirname "$check")"
    done
    return 1
}

# Read the expected_account field from the nearest .maestro marker.
#
# Usage: read_expected_account [start_dir]
# Echoes account name if found and non-empty, returns 1 otherwise.
read_expected_account() {
    local marker
    marker="$(find_marker "${1:-$PWD}")" || return 1
    _parse_marker_field "$marker" expected_account
}

# Expand a config_dir spec for a target shell.
#
# Usage: expand_config_dir <config_dir> [shell] [home_override]
#   config_dir:    raw value from launch-settings.yaml (e.g. ~/.claude-personal)
#   shell:         bash|zsh|fish|powershell|wsl|ssh (default: bash)
#   home_override: override for $HOME (mainly for tests / cross-host)
#
# For wsl / ssh targets the value passes through unchanged — the remote
# shell is responsible for expansion at launch time.
expand_config_dir() {
    local config_dir="${1:-}"
    local shell="${2:-bash}"
    local home_override="${3:-}"

    [[ -z "$config_dir" ]] && { echo ""; return 0; }

    # Normalize backslashes to forward slashes.
    local s="${config_dir//\\//}"

    # Deferred expansion for remote shells.
    case "$shell" in
        wsl|ssh)
            echo "$s"
            return 0
            ;;
    esac

    local home="${home_override:-$HOME}"
    home="${home//\\//}"

    # Expand leading tilde.
    if [[ "$s" == "~" ]]; then
        s="$home"
    elif [[ "$s" == "~/"* ]]; then
        s="$home/${s#\~/}"
    fi

    # Expand $HOME / ${HOME} / $USERPROFILE / ${USERPROFILE} tokens.
    s="${s//\$\{HOME\}/$home}"
    s="${s//\$HOME/$home}"
    s="${s//\$\{USERPROFILE\}/$home}"
    s="${s//\$USERPROFILE/$home}"

    # Native slash form for Windows shells.
    case "$shell" in
        powershell|pwsh|cmd)
            echo "${s//\//\\}"
            ;;
        *)
            echo "$s"
            ;;
    esac
}
