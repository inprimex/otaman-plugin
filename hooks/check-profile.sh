#!/usr/bin/env bash
# SessionStart: warn when the active otaman profile disagrees with the
# .otaman marker's expected_profile (or legacy expected_account). Never blocks — only writes to stderr.
#
# Resolution order (mirrors bridge_approval.py's _derive_account):
#   1. ${OTAMAN_ACTIVE_PROFILE:-${OTAMAN_ACTIVE_ACCOUNT:-${MAESTRO_ACTIVE_ACCOUNT:-}}}  — set by the launcher, most reliable
#   2. CLAUDE_CONFIG_DIR basename  — ~/.claude-<name> → <name>
#                                    (plain ~/.claude → "default")
#   3. Custom CLAUDE_CONFIG_DIR that doesn't match the .claude-* convention
#      → silently skip (user opted out of the sanity net)
#
# OTAMAN_ACTIVE_PROFILE takes priority because it's how projects that
# share a single CLAUDE_CONFIG_DIR (one login per subscription, many
# Telegram groups) tell the hook which profile is *actually* active.
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"

expected="$(read_expected_profile "$PWD")" || exit 0
[[ -n "$expected" ]] || exit 0

actual=""
source_desc=""

if [[ -n "${OTAMAN_ACTIVE_PROFILE:-${OTAMAN_ACTIVE_ACCOUNT:-${MAESTRO_ACTIVE_ACCOUNT:-}}}" ]]; then
    actual="${OTAMAN_ACTIVE_PROFILE:-${OTAMAN_ACTIVE_ACCOUNT:-${MAESTRO_ACTIVE_ACCOUNT:-}}}"
    source_desc="OTAMAN_ACTIVE_PROFILE=$actual"
elif [[ -z "${CLAUDE_CONFIG_DIR:-}" ]]; then
    actual="default"
    source_desc="CLAUDE_CONFIG_DIR=~/.claude (default)"
else
    base="$(basename "$CLAUDE_CONFIG_DIR")"
    case "$base" in
        .claude)
            actual="default"
            source_desc="CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR"
            ;;
        .claude-*)
            actual="${base#.claude-}"
            source_desc="CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR"
            ;;
        *)
            # Custom layout — can't infer, silently skip.
            exit 0
            ;;
    esac
fi

if [[ "$expected" != "$actual" ]]; then
    marker="$(find_marker "$PWD")" || marker="(unknown)"
    printf 'otaman: warning: account mismatch\n' >&2
    printf 'otaman:   expected: %s  (from %s)\n' "$expected" "$marker" >&2
    printf 'otaman:   actual:   %s  (from %s)\n' "$actual" "$source_desc" >&2
    printf 'otaman:   run "otaman accounts list" to see configured accounts\n' >&2
fi

exit 0
