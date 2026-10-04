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

# Attribute the commit to the owner of the REPO it happened in.
#
# This used to read "$PROJECT_ROOT/.agents/current-agent", which is a single
# tenant-wide file — so every repo's commits were labelled with whatever agent
# last wrote it. Measured 2026-10-03: 43 review-requests in one day, about four
# different repos, every one of them claiming `from: fswatch-agent`, who had
# committed nothing. It is also step 5 of cli's 6-step identity chain and
# DEPRECATED; cwd-ownership was made authoritative by team-mode B1 precisely so
# a stale shared value cannot claim someone else's repo.
#
# `otaman whoami --resolve-only` is that chain, and is documented as cheap
# enough for a hook. Exit 3 means "asked, found nothing"; anything else nonzero
# means "could not ask". Both fall back to the repo name, which is still a
# better answer than another repo's agent.
AGENT_NAME=""
if command -v otaman >/dev/null 2>&1; then
    AGENT_NAME="$(otaman whoami --resolve-only 2>/dev/null)" || AGENT_NAME=""
fi
AGENT_NAME="$(printf '%s' "$AGENT_NAME" | tr -d '[:space:]')"
AGENT_NAME="${AGENT_NAME:-$REPO_NAME}"

# Resolve observers. THE DEFAULT IS TO SEND NOTHING.
#
# This hook's header has always claimed it "checks observer triggers from
# platform.yaml". It never did: it hardcoded `to: human` and told the human
# that "observers matching these triggers should review this commit". With no
# observer concept declared anywhere in the platform schema, that produced 953
# messages into one queue over four months — a notifier with no recipients
# notifying a bystander.
#
# So: send to the agents declared under a top-level `observers:` list, and when
# none are declared send NOTHING. An unresolved recipient is not a reason to
# pick one. The note goes to stderr, which git shows to whoever ran the commit,
# rather than to a queue nobody asked.
#
# The `observers:` shape is deliberately minimal (a flat list of agent names)
# and is NOT a ratified schema — flagged to spec-agent. Honouring a key if
# someone declares it is not the same as inventing a contract, and the
# default-off behaviour is correct either way.
OBSERVERS="$(awk '
    /^observers:[[:space:]]*$/ { inlist=1; next }
    inlist && /^[[:space:]]*-[[:space:]]*/ { sub(/^[[:space:]]*-[[:space:]]*/, ""); gsub(/["'"'"']/, ""); print; next }
    inlist && /^[^[:space:]-]/ { inlist=0 }
' "$PLATFORM_YAML" 2>/dev/null)"

if [[ -z "$OBSERVERS" ]]; then
    echo "otaman: commit matched [$TRIGGERS] but no observers are declared in platform.yaml — no review-request sent" >&2
    exit 0
fi

# Create message with timestamp-based ID
mkdir -p "$BUS_ACTIVE/acks"

MSG_ID="${MSG_TIMESTAMP}-${COMMIT_HASH}"
PRIMARY="$(printf '%s\n' "$OBSERVERS" | head -1)"
CC_LIST="$(printf '%s\n' "$OBSERVERS" | tail -n +2 | paste -sd, -)"
MSG_FILE="$BUS_ACTIVE/${MSG_TIMESTAMP}-${AGENT_NAME}-to-${PRIMARY}-post-commit-review.md"

TRIGGER_LIST=""
for t in $TRIGGERS; do
    TRIGGER_LIST="$TRIGGER_LIST- $t"$'\n'
done

cat > "$MSG_FILE" << EOF
---
id: ${MSG_ID}
from: ${AGENT_NAME}
to: ${PRIMARY}${CC_LIST:+
cc: [${CC_LIST}]}
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

You are a declared observer for these trigger categories.
EOF

exit 0
