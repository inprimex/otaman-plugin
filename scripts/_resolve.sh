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

# Resolve the current agent identity via the standard priority chain:
#   1. OTAMAN_AGENT env var (process-scoped — set by launcher or OTAMAN_AGENT=x prefix)
#   2. .otaman agent: field — CWD walk up, both file-shape and directory-shape
#   3. current-agent file at $project_root/.agents/current-agent (deprecated fallback)
#
# NOTE (F013, 2026-07-08): this chain is for DISPLAY / convenience use only
# (status lines, non-enforcement bus tooling) — it trusts two signals any
# agent's own tool calls can freely set (OTAMAN_AGENT env, the shared
# current-agent file). PreToolUse enforcement hooks (check-ownership.sh,
# check-blocked.sh) must NOT use this function for their allow/deny
# decision; use resolve_enforcement_identity below instead.
#
# Usage: resolve_agent_identity [project_root]
# Echoes agent name and returns 0 on success; returns 1 if identity cannot be determined.
resolve_agent_identity() {
    local project_root="${1:-}"

    # 1. OTAMAN_AGENT env var
    if [[ -n "${OTAMAN_AGENT:-}" ]]; then
        echo "$OTAMAN_AGENT"
        return 0
    fi

    # 2. .otaman agent: field — walk up from CWD
    local check="$PWD"
    local prev=""
    while [[ "$check" != "/" && "$check" != "." && "$check" != "$prev" ]]; do
        if [[ -f "$check/.otaman" ]]; then
            # File shape: YAML with agent: field
            local agent_val
            agent_val="$(grep '^agent:' "$check/.otaman" 2>/dev/null | sed 's/^agent:[[:space:]]*//' | tr -d '[:space:]')"
            if [[ -n "$agent_val" ]]; then
                echo "$agent_val"
                return 0
            fi
        elif [[ -d "$check/.otaman" && -f "$check/.otaman/agent" ]]; then
            # Directory shape: single-line text file
            local agent_val
            agent_val="$(tr -d '[:space:]' < "$check/.otaman/agent" 2>/dev/null)"
            if [[ -n "$agent_val" ]]; then
                echo "$agent_val"
                return 0
            fi
        fi
        prev="$check"
        check="$(dirname "$check")"
    done

    # 3. current-agent deprecated fallback
    if [[ -n "$project_root" && -f "$project_root/.agents/current-agent" ]]; then
        local agent_val
        agent_val="$(tr -d '[:space:]' < "$project_root/.agents/current-agent")"
        if [[ -n "$agent_val" ]]; then
            echo "$agent_val"
            return 0
        fi
    fi

    return 1
}

# Resolve agent identity for an ENFORCEMENT decision (F013 security fix,
# 2026-07-08). Delegates to the single canonical enforcement-identity
# resolver — otaman_core.identity.resolve_enforcement_identity() — via the
# CLI's thin wrapper `otaman whoami --resolve-only`, instead of
# reimplementing the priority chain here. Prior drift between this file's
# own chain, otaman-cli's identity.py, and bus_server.py's MCP resolver
# caused a real misattribution incident (2026-06-08) — see the otaman-core
# module docstring for the full history.
#
# Deliberately narrower than resolve_agent_identity above: it does NOT
# trust OTAMAN_AGENT env or .agents/current-agent (both agent-writable —
# exactly the spoofing surface this fix closes). Only the per-directory
# .otaman `agent:` marker is honored, resolved from $PWD.
#
# Hardened against a stale/mismatched otaman-cli install: an older build
# without --resolve-only silently falls through to the full human-readable
# `otaman whoami` banner instead of erroring, which — if naively captured —
# would corrupt CURRENT_AGENT with a multi-line box-drawing block and cause
# every ownership check to fail closed. Output is accepted only if it is a
# single line that looks like a bare identifier.
#
# Usage: resolve_enforcement_identity
# Echoes agent name and returns 0 on success; returns 1 (no output) if
# identity cannot be resolved, the `otaman` CLI is unavailable, or its
# output doesn't look like a bare agent name.
resolve_enforcement_identity() {
    command -v otaman >/dev/null 2>&1 || return 1

    local out
    out="$(otaman whoami --resolve-only 2>/dev/null)" || return 1

    # Must be exactly one line and a bare identifier — rejects multi-line
    # banners, blank output, and anything containing whitespace/box-drawing
    # characters.
    if [[ "$out" != *$'\n'* && "$out" =~ ^[A-Za-z0-9_-]+$ ]]; then
        echo "$out"
        return 0
    fi
    return 1
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

# Resolve a Python interpreter capable of importing otaman_core, mirroring
# servers/run-server.sh's resolution chain (otaman uv-workspace venv →
# system python3/py/python). Hooks that need to call into otaman_core
# (e.g. F012's bus-message validator) should use this instead of a bare
# `command -v python3` — a bare system python3 frequently lacks
# otaman_core even when the otaman workspace's own venv has it installed.
#
# Usage: PY="$(resolve_otaman_python "$plugin_root_dir")" || exit 0
#   plugin_root_dir: the otaman-plugin repo root (workspace venv is
#   assumed to live one level up from it, per the uv-workspace layout).
resolve_otaman_python() {
    local plugin_root="${1:-$PWD}"

    local workspace_venv="$plugin_root/../.venv"
    if [[ -x "$workspace_venv/bin/python" ]]; then
        echo "$workspace_venv/bin/python"
        return 0
    elif [[ -x "$workspace_venv/Scripts/python.exe" ]]; then
        echo "$workspace_venv/Scripts/python.exe"
        return 0
    fi

    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return 0
    elif command -v py >/dev/null 2>&1; then
        echo "py"
        return 0
    elif command -v python >/dev/null 2>&1; then
        echo "python"
        return 0
    fi

    return 1
}

