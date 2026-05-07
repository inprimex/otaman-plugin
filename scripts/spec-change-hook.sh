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

# Create message with timestamp-based ID
mkdir -p "$BUS_ACTIVE/acks"

MSG_ID="${MSG_TIMESTAMP}-${COMMIT_HASH}"
MSG_FILE="$BUS_ACTIVE/${MSG_TIMESTAMP}-specs-to-all-spec-change.md"

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
to: all
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

All agents should review specs relevant to their repos and adapt implementation if needed.
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
        # Find python interpreter
        PYTHON=""
        if command -v python3 &>/dev/null; then
            PYTHON="python3"
        elif command -v py &>/dev/null; then
            PYTHON="py"
        elif command -v python &>/dev/null; then
            PYTHON="python"
        fi

        if [[ -n "$PYTHON" ]]; then
            # Run map-tasks.py on each changed tasks.md
            while IFS= read -r tasks_file; do
                if [[ -f "$PWD/$tasks_file" ]]; then
                    $PYTHON "$MAP_TASKS" "$PWD/$tasks_file" >/dev/null 2>&1 || true
                fi
            done <<< "$(echo "$CHANGED_FILES" | grep -iE 'tasks\.md$')"
        fi
    fi
fi

exit 0
