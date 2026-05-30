#!/usr/bin/env bash
# PreToolUse hook: blocks writes to repos not owned by the current agent.
# Also enforces spec write-protection and contract file protection.
#
# Pure bash — no Python, no grep -P. Portable across Linux, macOS, WSL,
# and Windows Git Bash.
#
# Input: JSON via stdin with fields:
#   tool_name    — the tool being called (Write, Edit, Bash)
#   tool_input   — object with the tool parameters (e.g. file_path)
#
# Output (JSON to stdout):
#   On block: {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny"},"systemMessage":"..."}
#   On allow: exit 0 (no output needed)
#
# Claude Code validates hookSpecificOutput — `hookEventName` is required.
#
# Exit codes:
#   0 — allow
#   2 — block

set -euo pipefail

# Read stdin
INPUT="$(cat)"

# --- Find project root (shared resolver) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_resolve.sh"

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0

OWNERSHIP_FILE="$PROJECT_ROOT/.agents/ownership.json"

# Resolve agent identity via priority chain: OTAMAN_AGENT env > .otaman agent: field > current-agent fallback
CURRENT_AGENT="$(resolve_agent_identity "$PROJECT_ROOT")" || exit 0
[[ -n "$CURRENT_AGENT" ]] || exit 0

# --- Portable JSON value extraction (no grep -P, no python) ---
# Extracts the value for a given key from a JSON string.
# Works for simple string values: "key": "value"
json_get() {
    local json="$1"
    local key="$2"
    echo "$json" | sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1
}

# --- Extract tool_name ---
TOOL_NAME="$(json_get "$INPUT" "tool_name")"
[[ -n "$TOOL_NAME" ]] || exit 0

# --- Parse ownership map (needed for all tool types) ---
REPO_PATHS="$(sed -n 's/.*"path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$OWNERSHIP_FILE")"
REPO_OWNERS="$(sed -n 's/.*"owner"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$OWNERSHIP_FILE")"

# Read into arrays using while loop (bash 3+ compatible)
i=0
while IFS= read -r line; do
    PATHS_ARR[i]="$line"
    i=$((i + 1))
done <<< "$REPO_PATHS"

i=0
while IFS= read -r line; do
    OWNERS_ARR[i]="$line"
    i=$((i + 1))
done <<< "$REPO_OWNERS"

# --- Spec write-protection ---
# Read specs.path from platform.yaml (if exists)
SPECS_ABS=""
SPECS_OWNER=""
PLATFORM_YAML="$PROJECT_ROOT/platform.yaml"
if [[ -f "$PLATFORM_YAML" ]]; then
    SPECS_REL="$(sed -n '/^specs:/,/^[a-z]/{s/^  path:[[:space:]]*//p;}' "$PLATFORM_YAML" | head -1 | tr -d '[:space:]')"
    if [[ -n "$SPECS_REL" ]]; then
        SPECS_ABS="$(cd "$PROJECT_ROOT/$SPECS_REL" 2>/dev/null && pwd)" || SPECS_ABS=""
    fi
fi

# Find specs owner from ownership map
if [[ -n "$SPECS_ABS" ]]; then
    for idx in "${!PATHS_ARR[@]}"; do
        local_rel="${PATHS_ARR[$idx]}"
        local_abs="$(cd "$PROJECT_ROOT/$local_rel" 2>/dev/null && pwd 2>/dev/null)" || continue
        if [[ "$local_abs" == "$SPECS_ABS" ]]; then
            SPECS_OWNER="${OWNERS_ARR[$idx]:-}"
            break
        fi
    done
fi

# --- Helper: check spec and contract write-protection ---
# Returns 0 if allowed, exits 2 if blocked
check_spec_protection() {
    local CHECK_PATH="$1"
    local CONTEXT="${2:-}"

    # Spec repo protection: only specs owner can write to spec files
    if [[ -n "$SPECS_ABS" && -n "$SPECS_OWNER" ]]; then
        if [[ "$CHECK_PATH" == "$SPECS_ABS"/* || "$CHECK_PATH" == "$SPECS_ABS" ]]; then
            if [[ "$CURRENT_AGENT" != "$SPECS_OWNER" ]]; then
                local MSG="BLOCKED: Agent \\\"${CURRENT_AGENT}\\\" cannot write to specs (owned by ${SPECS_OWNER}). Use /otaman:propose to request spec changes${CONTEXT}"
                echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\"},\"systemMessage\":\"${MSG}\"}"
                exit 2
            fi
        fi
    fi

    # Contract file protection: *.openapi.yaml, *.proto, */contracts/*, */schemas/*
    local BASENAME
    BASENAME="$(basename "$CHECK_PATH")"
    case "$BASENAME" in
        *.openapi.yaml|*.openapi.yml|*.swagger.yaml|*.swagger.yml|*.proto)
            # Contract file — only specs owner or repo owner can modify
            if [[ -n "$SPECS_OWNER" && "$CURRENT_AGENT" == "$SPECS_OWNER" ]]; then
                return 0  # Specs owner can modify contracts anywhere
            fi
            # Check if this is in the agent's own repo — repo owner can update their own contracts
            for idx in "${!PATHS_ARR[@]}"; do
                local repo_rel="${PATHS_ARR[$idx]}"
                local repo_abs
                repo_abs="$(cd "$PROJECT_ROOT/$repo_rel" 2>/dev/null && pwd)" || continue
                if [[ "$CHECK_PATH" == "$repo_abs"/* && "${OWNERS_ARR[$idx]:-}" == "$CURRENT_AGENT" ]]; then
                    return 0  # Repo owner can modify contracts in their own repo
                fi
            done
            local MSG="BLOCKED: Agent \\\"${CURRENT_AGENT}\\\" cannot modify contract files directly. Use /otaman:propose to request contract changes${CONTEXT}"
            echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\"},\"systemMessage\":\"${MSG}\"}"
            exit 2
            ;;
    esac

    # Check path components for contracts/ or schemas/ directories
    case "$CHECK_PATH" in
        */contracts/*|*/schemas/*)
            if [[ -n "$SPECS_OWNER" && "$CURRENT_AGENT" == "$SPECS_OWNER" ]]; then
                return 0
            fi
            for idx in "${!PATHS_ARR[@]}"; do
                local repo_rel="${PATHS_ARR[$idx]}"
                local repo_abs
                repo_abs="$(cd "$PROJECT_ROOT/$repo_rel" 2>/dev/null && pwd)" || continue
                if [[ "$CHECK_PATH" == "$repo_abs"/* && "${OWNERS_ARR[$idx]:-}" == "$CURRENT_AGENT" ]]; then
                    return 0  # Repo owner can modify contracts in their own repo
                fi
            done
            local MSG="BLOCKED: Agent \\\"${CURRENT_AGENT}\\\" cannot modify contract/schema files directly. Use /otaman:propose${CONTEXT}"
            echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\"},\"systemMessage\":\"${MSG}\"}"
            exit 2
            ;;
    esac

    return 0
}

# --- Helper: check a single absolute path against the ownership map ---
# Returns 0 if allowed, exits 2 if blocked
check_path_ownership() {
    local CHECK_PATH="$1"
    local CONTEXT="${2:-}"

    for idx in "${!PATHS_ARR[@]}"; do
        local REPO_REL="${PATHS_ARR[$idx]}"
        local REPO_OWNER="${OWNERS_ARR[$idx]:-}"
        [[ -n "$REPO_REL" && -n "$REPO_OWNER" ]] || continue

        local REPO_ABS
        REPO_ABS="$(cd "$PROJECT_ROOT/$REPO_REL" 2>/dev/null && pwd)" || continue

        if [[ "$CHECK_PATH" == "$REPO_ABS"/* || "$CHECK_PATH" == "$REPO_ABS" ]]; then
            if [[ "$REPO_OWNER" == "$CURRENT_AGENT" ]]; then
                return 0  # Allowed
            else
                local REPO_NAME="$(basename "$REPO_ABS")"
                local MSG="BLOCKED: Agent \\\"${CURRENT_AGENT}\\\" cannot write to ${REPO_NAME} (owned by ${REPO_OWNER})${CONTEXT}"
                echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\"},\"systemMessage\":\"${MSG}\"}"
                exit 2
            fi
        fi
    done
    return 0  # Path is outside any repo — allow
}

# --- For Bash tool, scan for file-writing patterns targeting other repos ---
if [[ "$TOOL_NAME" == "Bash" ]]; then
    COMMAND="$(json_get "$INPUT" "command")"
    [[ -n "$COMMAND" ]] || exit 0

    # Extract potential target paths from redirect operators and common write commands
    # This is best-effort — not all Bash writes can be detected statically
    WRITE_TARGETS=""

    # Redirects: > or >> followed by a path
    for target in $(echo "$COMMAND" | sed -n 's/.*>[>]*[[:space:]]*\([^;|&[:space:]]*\).*/\1/gp'); do
        [[ -n "$target" && "$target" != "/dev/null" ]] && WRITE_TARGETS="$WRITE_TARGETS $target"
    done

    # tee command targets
    for target in $(echo "$COMMAND" | sed -n 's/.*tee[[:space:]]\+\(-a[[:space:]]\+\)\?\([^;|&[:space:]]*\).*/\2/gp'); do
        [[ -n "$target" ]] && WRITE_TARGETS="$WRITE_TARGETS $target"
    done

    if [[ -z "$WRITE_TARGETS" ]]; then
        exit 0  # No detectable file writes — allow
    fi

    # Check each detected write target against ownership
    for raw_target in $WRITE_TARGETS; do
        if [[ "$raw_target" == /* ]]; then
            CHECK_PATH="$raw_target"
        elif [[ -d "$(dirname "$raw_target" 2>/dev/null)" ]]; then
            CHECK_PATH="$(cd "$(dirname "$raw_target")" 2>/dev/null && pwd)/$(basename "$raw_target")" || continue
        else
            continue  # Can't resolve — skip
        fi

        check_spec_protection "$CHECK_PATH" " via Bash redirect"
        check_path_ownership "$CHECK_PATH" " via Bash redirect"
    done
    exit 0  # All targets allowed or unresolvable
fi

# --- For Write/Edit tools: check file_path ---
TARGET_PATH="$(json_get "$INPUT" "file_path")"
[[ -n "$TARGET_PATH" ]] || exit 0

# Resolve to absolute path
if [[ -d "$(dirname "$TARGET_PATH" 2>/dev/null)" ]]; then
    TARGET_PATH="$(cd "$(dirname "$TARGET_PATH")" 2>/dev/null && pwd)/$(basename "$TARGET_PATH")" || true
fi

# Normalize: remove trailing slash
TARGET_PATH="${TARGET_PATH%/}"

check_spec_protection "$TARGET_PATH"
check_path_ownership "$TARGET_PATH"

# Target is outside any repo (e.g., .agents/ directory) — allow
exit 0
