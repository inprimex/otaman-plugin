#!/usr/bin/env bash
# Git post-commit hook for the specs repo.
#
# Watches for changes in spec files and writes bus notifications
# so all agents are informed regardless of how specs changed:
#   (a) agent-initiated via otaman approval flow
#   (b) human using /opsx: commands directly
#   (c) manual edits
#
# Installed automatically by /otaman:init in the specs repo.
# Set OTAMAN_PROJECT_ROOT to override project root detection.

set -euo pipefail

# Find project root (shared resolver)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/_resolve.sh" ]]; then
    source "$SCRIPT_DIR/_resolve.sh"
else
    for candidate in \
        "$(dirname "$SCRIPT_DIR")/scripts/_resolve.sh" \
        "$(dirname "$(dirname "$SCRIPT_DIR")")/scripts/_resolve.sh"; do
        if [[ -f "$candidate" ]]; then
            source "$candidate"
            break
        fi
    done
fi

# Allow legacy OTAMAN_PROJECT_ROOT env var
[[ -n "${OTAMAN_PROJECT_ROOT:-}" ]] && export OTAMAN_ROOT="${OTAMAN_PROJECT_ROOT}"

# Say something when the hook cannot load its own dependency. deploy-agent's
# point (20260921T184535): three silences were stacked on this path — the
# git-hook shim's `|| true`, this `|| exit 0`, and the annotation loop skipping
# unmatched repos — and together they made a completely DEAD hook
# indistinguishable from a quiet one. Each is individually defensible; the
# combination is what cost haulops a working dispatch path unnoticed.
#
# Distinguish "I could not load _resolve.sh" (a broken install — say so) from
# "no otaman root here" (normal for an unmanaged repo — stay quiet).
if ! declare -F find_maestro_root >/dev/null 2>&1; then
    echo "[spec-change-hook] cannot load scripts/_resolve.sh — this install is" \
         "incomplete and the hook is inert. Task dispatch will NOT happen;" \
         "use \`otaman notify-change\` after spec commits until it is fixed." >&2
    exit 0
fi

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0

BUS_ACTIVE="$PROJECT_ROOT/.agents/bus/active"
REPO_NAME="$(basename "$PWD")"

# Get changed files in the latest commit
CHANGED_FILES="$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null)" || exit 0

if [[ -z "$CHANGED_FILES" ]]; then
    exit 0
fi

# Detect what kind of spec changes occurred
CHANGE_CATEGORIES=""

# Spec content changes (markdown specs, proposals, designs)
if echo "$CHANGED_FILES" | grep -qiE '\.(md|yaml|yml|json)$'; then
    CHANGE_CATEGORIES="$CHANGE_CATEGORIES spec-content"
fi

# Contract changes (OpenAPI, schemas)
if echo "$CHANGED_FILES" | grep -qiE '(openapi|swagger|schema|contract|\.proto)'; then
    CHANGE_CATEGORIES="$CHANGE_CATEGORIES contract-change"
fi

# Task changes (task lists, assignments)
if echo "$CHANGED_FILES" | grep -qiE '(task|todo|backlog|sprint)'; then
    CHANGE_CATEGORIES="$CHANGE_CATEGORIES task-update"
fi

if [[ -z "$CHANGE_CATEGORIES" ]]; then
    exit 0
fi

# Detect which spec subdirectories changed (these map to affected repos/domains)
AFFECTED_DIRS=""
while IFS= read -r file; do
    # Get top-level directory of the changed file
    top_dir="$(echo "$file" | cut -d'/' -f1)"
    if [[ "$top_dir" != "$file" && -n "$top_dir" ]]; then
        # Deduplicate
        if ! echo "$AFFECTED_DIRS" | grep -qw "$top_dir" 2>/dev/null; then
            AFFECTED_DIRS="$AFFECTED_DIRS $top_dir"
        fi
    fi
done <<< "$CHANGED_FILES"

COMMIT_HASH="$(git rev-parse --short HEAD)"
COMMIT_MSG="$(git log -1 --format='%s')"
COMMIT_AUTHOR="$(git log -1 --format='%an')"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date +%Y-%m-%dT%H:%M:%SZ)"
MSG_TIMESTAMP="$(date -u +%Y%m%dT%H%M%S 2>/dev/null || date +%Y%m%dT%H%M%S)"

# Derive spec-change recipients from tasks.md @otaman-<repo> annotations.
# Per targeted-bus-messaging spec (D3): route to involved agents only.
# Fallbacks: no tasks.md → spec-agent; no annotations → spec-agent, human.
PLATFORM_YAML="$PROJECT_ROOT/platform.yaml"
_SPEC_CHANGE_DIRS=""
while IFS= read -r _f; do
    if [[ "$_f" =~ ^openspec/changes/([^/]+)/ ]]; then
        _cn="${BASH_REMATCH[1]}"
        if [[ -n "$_cn" ]] && ! echo "$_SPEC_CHANGE_DIRS" | grep -qxF "$_cn" 2>/dev/null; then
            _SPEC_CHANGE_DIRS="${_SPEC_CHANGE_DIRS}${_cn}"$'\n'
        fi
    fi
done <<< "$CHANGED_FILES"

TO_FIELD="spec-agent, human"  # default: no openspec/changes/ files in this commit

if [[ -n "$_SPEC_CHANGE_DIRS" ]]; then
    _agents_found=""
    _any_tasks_md="false"
    _any_annotations="false"

    while IFS= read -r _cn; do
        [[ -z "$_cn" ]] && continue
        _tasks_file="$PWD/openspec/changes/$_cn/tasks.md"
        if [[ -f "$_tasks_file" ]]; then
            _any_tasks_md="true"
            _anns="$(grep -oiE '@otaman-[a-z0-9-]+' "$_tasks_file" 2>/dev/null | sort -u || true)"
            if [[ -n "$_anns" ]]; then
                _any_annotations="true"
                while IFS= read -r _ann; do
                    [[ -z "$_ann" ]] && continue
                    # Try the annotation AS-IS, then prefix-stripped — the
                    # same two-step otaman-cli's notify_change._lookup_owners
                    # does, so both naming conventions resolve.
                    #
                    # This used to look up only "otaman-<suffix>", which
                    # happens to work on this fleet by coincidence of naming
                    # (@otaman-cli -> otaman-cli) and never matches for a
                    # program whose repos are not otaman-prefixed: haulops'
                    # @otaman-haulops-firmware looked up
                    # "otaman-haulops-firmware" against a repo actually named
                    # "haulops-firmware", missed, and fell back to
                    # "spec-agent, human" without a word. `repos[].name` has
                    # no documented prefix constraint. Verified against
                    # haulops' real platform.yaml (deploy-agent 20260921T184535).
                    _repo="${_ann#@}"          # "otaman-<suffix>" as written
                    _repo_alt="${_repo#otaman-}"  # "<suffix>" for unprefixed programs
                    _owner=""
                    if [[ -f "$PLATFORM_YAML" ]]; then
                        for _candidate in "$_repo" "$_repo_alt"; do
                            [[ -z "$_candidate" ]] && continue
                            _owner="$(awk -v r="$_candidate" '
                                $0 ~ ("name: +" r "$") { found=1; next }
                                found && /owner:/ { sub(/.*owner:[[:space:]]*/, ""); sub(/[[:space:]]*$/, ""); print; exit }
                                found && /^[^[:space:]]/ { exit }
                            ' "$PLATFORM_YAML" 2>/dev/null | head -1 || true)"
                            [[ -n "$_owner" ]] && break
                        done
                    fi
                    if [[ -n "$_owner" ]] && ! echo "$_agents_found" | grep -qxF "$_owner" 2>/dev/null; then
                        _agents_found="${_agents_found}${_owner}"$'\n'
                    fi
                done <<< "$_anns"
            fi
        fi
    done <<< "$_SPEC_CHANGE_DIRS"

    if [[ "$_any_tasks_md" == "false" ]]; then
        TO_FIELD="spec-agent"
    elif [[ "$_any_annotations" == "false" ]] || [[ -z "$_agents_found" ]]; then
        TO_FIELD="spec-agent, human"
    else
        _to=""
        while IFS= read -r _agent; do
            [[ -z "$_agent" ]] && continue
            if [[ -z "$_to" ]]; then
                _to="$_agent"
            else
                _to="$_to, $_agent"
            fi
        done <<< "$_agents_found"
        TO_FIELD="$_to"
    fi
fi

# Create message with timestamp-based ID
mkdir -p "$BUS_ACTIVE/acks"

MSG_ID="${MSG_TIMESTAMP}-${COMMIT_HASH}"
MSG_FILE="$BUS_ACTIVE/${MSG_TIMESTAMP}-specs-spec-change.md"

# Build affected dirs list
AFFECTED_LIST=""
for d in $AFFECTED_DIRS; do
    AFFECTED_LIST="$AFFECTED_LIST- $d"$'\n'
done

# Build categories list
CATEGORY_LIST=""
for c in $CHANGE_CATEGORIES; do
    CATEGORY_LIST="$CATEGORY_LIST- $c"$'\n'
done

cat > "$MSG_FILE" << EOF
---
id: ${MSG_ID}
from: ${REPO_NAME}
to: ${TO_FIELD}
priority: high
type: spec-change
timestamp: ${TIMESTAMP}
status: pending
---

## Subject: Specs changed in ${REPO_NAME}

Commit \`${COMMIT_HASH}\` by ${COMMIT_AUTHOR}: ${COMMIT_MSG}

**Change categories**:
${CATEGORY_LIST}
**Affected spec areas**:
${AFFECTED_LIST}
**Changed files**:
$(echo "$CHANGED_FILES" | sed 's/^/- /')

Recipients are derived from \`tasks.md\` \`@otaman-<repo>\` annotations in affected change directories.
Fallback: \`spec-agent\` when no tasks.md exists; \`spec-agent, human\` when no annotations.
Use \`/otaman:check\` to see this notification.
EOF

# Auto-map tasks when tasks.md files are changed
if echo "$CHANGED_FILES" | grep -qiE 'tasks\.md$'; then
    # Find the map-tasks.py script (co-located with this hook script)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # When installed via otaman, the hook calls this script from the plugin's scripts/ dir
    # Try common locations for map-tasks.py
    MAP_TASKS=""
    for candidate in \
        "$SCRIPT_DIR/map-tasks.py" \
        "$(dirname "$SCRIPT_DIR")/scripts/map-tasks.py" \
        "$(dirname "$(dirname "$SCRIPT_DIR")")/scripts/map-tasks.py"; do
        if [[ -f "$candidate" ]]; then
            MAP_TASKS="$candidate"
            break
        fi
    done

    if [[ -n "$MAP_TASKS" ]]; then
        # map-tasks is now a shim over otaman_plugin.map_tasks, so the
        # interpreter MUST be able to import otaman_plugin. A bare `python3`
        # frequently cannot even when the workspace venv can, which is what
        # resolve_otaman_python exists for (and what the archive sweep below
        # already uses). The old bare-python3 chain is why this path could
        # only ever have worked by accident.
        PYTHON="$(resolve_otaman_python "$(dirname "$SCRIPT_DIR")" 2>/dev/null)" || PYTHON=""

        if [[ -n "$PYTHON" ]]; then
            # Run map-tasks on each changed tasks.md.
            #
            # `|| true` stays — a post-commit hook must never fail a commit —
            # but stderr is NO LONGER discarded. Silence was the actual
            # defect: the script returned 0 on every failure path, so even
            # removing `|| true` would have changed nothing, and >/dev/null
            # 2>&1 hid the one message that said dispatch had not happened.
            while IFS= read -r tasks_file; do
                if [[ -f "$PWD/$tasks_file" ]]; then
                    "$PYTHON" "$MAP_TASKS" "$PWD/$tasks_file" >/dev/null || {
                        echo "[spec-change-hook] map-tasks failed for $tasks_file" \
                             "— agents were NOT dispatched for it" >&2
                    }
                fi
            done <<< "$(echo "$CHANGED_FILES" | grep -iE 'tasks\.md$')"
        else
            echo "[spec-change-hook] no Python able to import otaman_plugin;" \
                 "task dispatch SKIPPED (use \`otaman notify-change\` manually)" >&2
        fi
    fi
fi

# Archive backstop (blocked-entry-lifecycle 1.2): a change moving into
# openspec/changes/archive/ sweeps any live blocked entry — either Kind —
# whose **Change**: field names it, across EVERY agent's blocked file. The
# safety net for the case where the terminating spec-change-approved /
# task-complete message was never delivered yet the change shipped anyway.
# This is itself a write path that bypasses `otaman_send`/MCP (a raw git
# post-commit hook, same class of producer as `otaman approve`), so it
# calls the same shared tombstone matcher directly rather than duplicating
# it. Never allowed to fail the hook: any error is swallowed.
if echo "$CHANGED_FILES" | grep -qE '^openspec/changes/archive/'; then
    SWEEP_PYTHON="$(resolve_otaman_python 2>/dev/null)" || SWEEP_PYTHON=""
    if [[ -n "$SWEEP_PYTHON" ]]; then
        "$SWEEP_PYTHON" -c '
import sys
from pathlib import Path
try:
    from otaman_plugin.servers.bus_server import archived_change_names, sweep_archived_blocked
    root = Path(sys.argv[1])
    sweep_archived_blocked(root, archived_change_names(root))
except Exception:
    pass
' "$PROJECT_ROOT" >/dev/null 2>&1 || true
    fi
fi

exit 0
