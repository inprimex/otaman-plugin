#!/usr/bin/env bash
# SessionStart: prepend user-install dirs to PATH for Bash tool calls.
#
# Claude Code's non-interactive shell does not source ~/.profile, so the
# standard Debian/Ubuntu snippet that adds ~/.local/bin to PATH never runs.
# This leaves tools installed by pip --user, cargo install, go install,
# uv tool install, or the official gh installer unreachable.
#
# We write exports to $CLAUDE_ENV_FILE, which Claude Code sources for every
# subsequent Bash tool call in the session.
set -eu

[[ -n "${CLAUDE_ENV_FILE:-}" ]] || exit 0
[[ -n "${HOME:-}" ]] || exit 0

for dir in "$HOME/.local/bin" "$HOME/bin"; do
    [[ -d "$dir" ]] || continue
    printf 'export PATH="%s:$PATH"\n' "$dir" >> "$CLAUDE_ENV_FILE"
done

exit 0
