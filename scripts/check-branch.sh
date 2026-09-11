#!/usr/bin/env bash
# Git pre-commit hook: enforces branch naming and blocks commits to protected branches.
#
# Installed by generate-agent-config.py in each repo's .git/hooks/pre-commit.
# Uses GitFlow convention: agents work on agent/{owner}/{feature} branches,
# main/master/develop are protected.
#
# Human override: OTAMAN_ALLOW_MAIN=1 git commit ...
#
# Exit codes:
#   0 — allow commit
#   1 — block commit

set -euo pipefail

# Human override
[[ "${OTAMAN_ALLOW_MAIN:-}" == "1" ]] && exit 0

# Find otaman root
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

ROOT="$(find_maestro_root 2>/dev/null)" || exit 0

# Get current branch
BRANCH="$(git symbolic-ref --short HEAD 2>/dev/null)" || exit 0

# Protected branches — block commits
PROTECTED="main master develop"
for pb in $PROTECTED; do
    if [[ "$BRANCH" == "$pb" ]]; then
        echo ""
        echo "  BLOCKED: Direct commits to '$BRANCH' are not allowed."
        echo ""
        echo "  GitFlow: work on a feature branch, then create a PR."
        echo "  Create a branch:  git checkout -b agent/<your-name>/<feature>"
        echo "  Human override:   OTAMAN_ALLOW_MAIN=1 git commit ..."
        echo ""
        exit 1
    fi
done

# Validate branch naming (only when agent identity exists).
# team-mode-registers-and-sessions 2.1 (B1, Roman ruling 2026-09-11):
# .agents/current-agent is RETIRED (one shared file, N sessions,
# last-writer-wins — the incident class B1 exists to close). Delegate to
# the shared resolve_agent_identity (cwd-ownership authoritative,
# OTAMAN_AGENT override, kernel-implemented) instead of a per-repo copy —
# a git pre-commit hook can afford the one python3 spawn it costs, unlike
# a per-prompt hook. Any failure (no python3, no otaman_core, genuinely
# unresolved) degrades to no-agent-context — this check is a naming
# WARNING, never a hard block on identity.
AGENT="$(resolve_agent_identity "$ROOT" 2>/dev/null || true)"

# No agent context = human working directly, allow any branch name
[[ -z "$AGENT" ]] && exit 0

# Agent branches should match agent/{owner}/{feature}
if [[ ! "$BRANCH" =~ ^agent/ ]]; then
    echo ""
    echo "  WARNING: Branch '$BRANCH' doesn't follow the agent naming convention."
    echo "  Expected: agent/$AGENT/<feature-name>"
    echo "  Example:  git checkout -b agent/$AGENT/add-payment-endpoint"
    echo ""
    # Warning only, not a hard block — agent might be on a human-created branch
fi

exit 0
