#!/usr/bin/env bash
# Shared otaman root resolution for all bash hooks.
#
# Resolution chain (first match wins):
# 1. .otaman/.maestro marker file in CWD or ancestors  # legacy: .maestro marker supported
# 2. OTAMAN_ROOT / MAESTRO_ROOT environment variable  # legacy: MAESTRO_ROOT supported
# 3. Walk-up fallback: look for .agents/ownership.json (legacy compat)
#
# Usage: source this file, then call find_maestro_root
#   source "$(dirname "${BASH_SOURCE[0]}")/_resolve.sh"
#   ROOT="$(find_maestro_root)" || exit 0

find_maestro_root() {
    local dir="${1:-$PWD}"

    # First try resolving from the cwd directly.
    local result
    if result="$(_find_maestro_root_from "$dir")"; then
        echo "$result"
        return 0
    fi

    # If cwd is inside a linked git worktree, the worktree directory likely
    # has no .otaman/.maestro marker (worktrees are created after init).  # legacy: .maestro supported
    # Try again from the main repo's working tree, where the marker lives.
    local worktree_main
    worktree_main="$(resolve_worktree_main "$dir")"
    if [[ -n "$worktree_main" ]]; then
        if result="$(_find_maestro_root_from "$worktree_main")"; then
            echo "$result"
            return 0
        fi
    fi

    return 1
}

# Internal: run the three-step resolution chain (marker → env → walk-up)
# starting from a given directory. Echoes the resolved otaman root on
# stdout and returns 0 on success; returns 1 with no output on failure.
#
# The `prev != check` fixed-point guard on each walk loop is the Windows-
# native-path safety: bash's `dirname C:` returns `C:` forever, so the
# unguarded while-loop hangs on `C:/...` cwd inputs. Ported from the
# legacy 2026-05-05 fix.
_find_maestro_root_from() {
    local dir="$1"

    # 1. .otaman (preferred) or .maestro marker file — walk up  # legacy: .maestro supported
    local check="$dir"
    local prev=""
    while [[ "$check" != "/" && "$check" != "." && "$check" != "$prev" ]]; do
        local marker=""
        if [[ -f "$check/.otaman" ]]; then
            marker="$check/.otaman"
        elif [[ -f "$check/.maestro" ]]; then  # legacy: .maestro marker supported
            marker="$check/.maestro"  # legacy: .maestro marker path
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
        prev="$check"
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
    prev=""
    while [[ "$check" != "/" && "$check" != "." && "$check" != "$prev" ]]; do
        if [[ -f "$check/.agents/ownership.json" ]] || [[ -f "$check/platform.yaml" ]]; then
            echo "$check"
            return 0
        fi
        prev="$check"
        check="$(dirname "$check")"
    done

    return 1
}

# Resolve a git worktree path to the main repo's working tree.
#
# Walks up from the given path looking for a .git entry:
# - .git is a regular file → worktree marker, parse gitdir:, return main
# - .git is a directory     → ordinary repo (not a worktree); empty result
# - no .git found           → not in any repo; empty result
#
# A linked worktree has `.git` as a *file* containing a single line:
#   gitdir: <main_repo>/.git/worktrees/<name>
# The main repo's working tree is the great-grandparent of that gitdir.
#
# Usage:
#   MAIN="$(resolve_worktree_main "$CWD")"
#
# Echoes the absolute path to the main repo on success, empty on no
# match or any parse failure. Never fails (returns 0).
resolve_worktree_main() {
    local dir="${1:-$PWD}"
    local check="$dir"
    local prev=""
    while [[ "$check" != "/" && "$check" != "." && "$check" != "$prev" ]]; do
        if [[ -f "$check/.git" ]]; then
            local gitdir line
            gitdir=""
            while IFS= read -r line || [[ -n "$line" ]]; do
                line="${line#"${line%%[![:space:]]*}"}"
                if [[ "$line" == gitdir:* ]]; then
                    gitdir="${line#gitdir:}"
                    gitdir="${gitdir#"${gitdir%%[![:space:]]*}"}"
                    gitdir="${gitdir%"${gitdir##*[![:space:]]}"}"
                    break
                fi
            done < "$check/.git"
            [[ -z "$gitdir" ]] && { echo ""; return 0; }
            if [[ "$gitdir" != /* && "$gitdir" != [a-zA-Z]:* ]]; then
                gitdir="$(cd "$check" 2>/dev/null && cd "$gitdir" 2>/dev/null && pwd)" || gitdir=""
            fi
            [[ -z "$gitdir" ]] && { echo ""; return 0; }
            local parent grandparent
            parent="$(dirname "$gitdir")"
            grandparent="$(dirname "$parent")"
            if [[ "$(basename "$parent")" == "worktrees" && "$(basename "$grandparent")" == ".git" ]]; then
                local main
                main="$(cd "$(dirname "$grandparent")" 2>/dev/null && pwd)" || main=""
                echo "$main"
                return 0
            fi
            echo ""
            return 0
        fi
        if [[ -d "$check/.git" ]]; then
            echo ""
            return 0
        fi
        prev="$check"
        check="$(dirname "$check")"
    done
    echo ""
    return 0
}

# Parse a .otaman/.maestro marker file and echo the value of a known field.  # legacy: .maestro supported
#
# Usage: _parse_marker_field <marker_path> <field_name>
# Known fields: maestro_root (legacy alias for otaman_root), expected_account.  # legacy: maestro_root field
# Returns 0 with value on stdout if found, 1 otherwise.
#
# Legacy single-line markers (bare path) resolve to maestro_root  # legacy: maestro_root field name
# for backward-compat. Unknown `key:` lines are ignored so Windows
# absolute paths (C:/foo) continue to parse as bare otaman_root values.
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
                maestro_root|expected_account)  # legacy: maestro_root field name kept for backward-compat
                    if [[ "$key" == "$field" ]]; then
                        echo "$val"
                        return 0
                    fi
                    continue
                    ;;
            esac
        fi

        # Bare line — candidate for otaman_root / maestro_root (keep first).  # legacy: maestro_root field name
        [[ -z "$bare_path" ]] && bare_path="$line"
    done < "$marker"

    if [[ "$field" == "maestro_root" && -n "$bare_path" ]]; then  # legacy: maestro_root field name
        echo "$bare_path"
        return 0
    fi
    return 1
}

# Walk up from a directory looking for a .otaman or .maestro marker file.  # legacy: .maestro supported
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
        elif [[ -f "$check/.maestro" ]]; then  # legacy: .maestro marker supported
            echo "$check/.maestro"  # legacy: .maestro marker path
            return 0
        fi
        check="$(dirname "$check")"
    done
    return 1
}

# Read the expected_account field from the nearest .otaman/.maestro marker.  # legacy: .maestro supported
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

# Routing resolution (formerly "account", briefly "profile" — see
# otaman-core/_resolve.py docstring for full history).
# read_expected_routing prefers expected_routing:, falls back to expected_account:.
read_expected_routing() {
    local start="${1:-$PWD}"
    local marker
    marker="$(find_marker "$start")" || return 0
    [[ -n "$marker" ]] || return 0
    # Try new key first, fall back to legacy.
    local val
    val="$(grep -E '^expected_routing:' "$marker" 2>/dev/null | head -1 | sed 's/^expected_routing:[[:space:]]*//')"
    if [[ -z "$val" ]]; then
        val="$(grep -E '^expected_account:' "$marker" 2>/dev/null | head -1 | sed 's/^expected_account:[[:space:]]*//')"
    fi
    [[ -n "$val" ]] && echo "$val"
}

