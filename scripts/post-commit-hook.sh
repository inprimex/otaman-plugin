#!/usr/bin/env bash
# Git post-commit hook for otaman-managed repos.
#
# Install by adding to .git/hooks/post-commit or via core.hooksPath.
# Triggers observer reviews based on what changed in the commit.
#
# This hook:
# 1. Detects what files changed in the latest commit
# 2. Checks observer triggers from platform.yaml
# 3. Creates review-request bus messages in bus/active/
#
# Set OTAMAN_PROJECT_ROOT to override project root detection.

set -euo pipefail

# Find project root (shared resolver)
# When installed via otaman init, SCRIPT_DIR points to the plugin scripts/ dir.
# The hook shim in .git/hooks/post-commit sources the plugin's _resolve.sh.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/_resolve.sh" ]]; then
    source "$SCRIPT_DIR/_resolve.sh"
else
    # Fallback: look for _resolve.sh relative to the plugin
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

PLATFORM_YAML="$PROJECT_ROOT/platform.yaml"
BUS_ACTIVE="$PROJECT_ROOT/.agents/bus/active"

if [[ ! -f "$PLATFORM_YAML" ]]; then
    exit 0
fi

# Get changed files in the latest commit
CHANGED_FILES="$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null)" || exit 0

if [[ -z "$CHANGED_FILES" ]]; then
    exit 0
fi

# Detect trigger categories from changed files
TRIGGERS=""

# Check for spec changes
if echo "$CHANGED_FILES" | grep -qiE '(openapi|swagger|\.proto|schema|spec)'; then
    TRIGGERS="$TRIGGERS spec-change"
fi

# Check for architecture changes (new services, major config)
if echo "$CHANGED_FILES" | grep -qiE '(docker-compose|\.env\.example|package\.json|go\.mod|Cargo\.toml)'; then
    TRIGGERS="$TRIGGERS architecture-change"
fi

# Check for dependency updates
if echo "$CHANGED_FILES" | grep -qiE '(package-lock|yarn\.lock|pnpm-lock|requirements\.txt|Pipfile\.lock|Cargo\.lock|go\.sum)'; then
    TRIGGERS="$TRIGGERS dependency-update"
fi

# Check for auth changes
if echo "$CHANGED_FILES" | grep -qiE '(auth|login|token|session|password|jwt|oauth|permission|rbac|acl)'; then
    TRIGGERS="$TRIGGERS auth-change"
fi

# Check for infra changes
if echo "$CHANGED_FILES" | grep -qiE '(terraform|\.tf$|pulumi|helm|k8s|kubernetes)'; then
    TRIGGERS="$TRIGGERS infra-change"
fi

# Check for dockerfile changes
if echo "$CHANGED_FILES" | grep -qiE '(Dockerfile|docker-compose|\.dockerignore)'; then
    TRIGGERS="$TRIGGERS dockerfile-change"
fi

# Check for CI changes
if echo "$CHANGED_FILES" | grep -qiE '(\.github/workflows|\.gitlab-ci|Jenkinsfile|\.circleci|bitbucket-pipelines)'; then
    TRIGGERS="$TRIGGERS ci-change"
fi

# General code changes (source files that didn't match specific categories above)
if [[ -z "$TRIGGERS" ]]; then
    if echo "$CHANGED_FILES" | grep -qiE '\.(py|js|ts|jsx|tsx|go|rs|java|cs|cpp|c|h|rb|php|swift|kt|scala|sh|sql)$'; then
        TRIGGERS="code-change"
    fi
fi

if [[ -z "$TRIGGERS" ]]; then
    exit 0
fi

# Get current repo name
REPO_NAME="$(basename "$PWD")"
COMMIT_HASH="$(git rev-parse --short HEAD)"
COMMIT_MSG="$(git log -1 --format='%s')"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date +%Y-%m-%dT%H:%M:%SZ)"
MSG_TIMESTAMP="$(date -u +%Y%m%dT%H%M%S 2>/dev/null || date +%Y%m%dT%H%M%S)"

# Get agent identity
AGENT_NAME=""
if [[ -f "$PROJECT_ROOT/.agents/current-agent" ]]; then
    AGENT_NAME="$(cat "$PROJECT_ROOT/.agents/current-agent" | tr -d '[:space:]')"
fi
AGENT_NAME="${AGENT_NAME:-$REPO_NAME}"

# Create message with timestamp-based ID
mkdir -p "$BUS_ACTIVE/acks"

MSG_ID="${MSG_TIMESTAMP}-${COMMIT_HASH}"
MSG_FILE="$BUS_ACTIVE/${MSG_TIMESTAMP}-${AGENT_NAME}-to-all-post-commit-review.md"

TRIGGER_LIST=""
for t in $TRIGGERS; do
    TRIGGER_LIST="$TRIGGER_LIST- $t"$'\n'
done

cat > "$MSG_FILE" << EOF
---
id: ${MSG_ID}
from: ${AGENT_NAME}
to: all
priority: normal
type: review-request
timestamp: ${TIMESTAMP}
status: pending
---

## Subject: Post-commit review triggered for ${REPO_NAME}

Commit \`${COMMIT_HASH}\`: ${COMMIT_MSG}

**Triggered categories**:
${TRIGGER_LIST}
**Changed files**:
$(echo "$CHANGED_FILES" | sed 's/^/- /')

Observers matching these triggers should review this commit.
EOF

exit 0
