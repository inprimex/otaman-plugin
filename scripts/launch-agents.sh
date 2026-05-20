#!/usr/bin/env bash
# Launch Claude Code agents for a maestro project (bash parity with
# launch-agents.ps1). Set CLAUDE_CONFIG_DIR from the active connection's
# account, load .maestro/secrets.env, then exec claude or spawn tmux.
#
# USAGE
#   launch-agents.sh [options] [-- <extra args to claude>]
#
# OPTIONS
#   -c, --connection NAME   Named connection from launch-settings.yaml
#       --shell MODE        bash (default, exec claude here) | tmux | print
#       --repo NAME         For tmux: launch claude in that repo's directory
#       --list-repos        Print repo names and exit
#   -d, --dry-run           Print resolved state and commands, don't execute
#   -h, --help              Show this help
#
# EXAMPLES
#   ./launch-agents.sh                          # exec claude with resolved env
#   ./launch-agents.sh -c lan                   # use 'lan' connection
#   ./launch-agents.sh --list-repos
#   ./launch-agents.sh --shell tmux             # one tmux window per repo
#   ./launch-agents.sh -d                       # show what would run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_resolve.sh
source "$SCRIPT_DIR/_resolve.sh"

# ------------------------------------------------------------------
# CLI parsing

CONNECTION=""
SHELL_MODE="bash"   # bash | tmux | print
REPO_FILTER=""
LIST_REPOS=0
DRY_RUN=0
EXTRA_ARGS=()

usage() {
    sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--connection)
            CONNECTION="${2:-}"
            shift 2
            ;;
        --shell)
            SHELL_MODE="${2:-}"
            shift 2
            ;;
        --repo)
            REPO_FILTER="${2:-}"
            shift 2
            ;;
        --list-repos)
            LIST_REPOS=1
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            EXTRA_ARGS=("$@")
            break
            ;;
        *)
            echo "unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

case "$SHELL_MODE" in
    bash|tmux|print) ;;
    *)
        echo "error: --shell must be one of: bash, tmux, print (got: $SHELL_MODE)" >&2
        exit 2
        ;;
esac

# ------------------------------------------------------------------
# Resolve maestro root + determine python interpreter

MAESTRO_ROOT="$(find_maestro_root "$PWD" 2>/dev/null || true)"
if [[ -z "$MAESTRO_ROOT" ]]; then
    echo "error: no maestro folder found from $PWD" >&2
    echo "hint: run from inside a managed repo, set MAESTRO_ROOT, or create a .maestro marker" >&2
    exit 1
fi

# Prefer python3; on Windows-with-py-launcher, fall back to `py -3`.
PYTHON=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v py >/dev/null 2>&1; then
    PYTHON="py -3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "error: no python3 interpreter found on PATH" >&2
    exit 1
fi

# ------------------------------------------------------------------
# Invoke resolver, eval its exports

RESOLVE_OUT="$(${PYTHON} "$SCRIPT_DIR/launch-resolve.py" \
    --maestro-root "$MAESTRO_ROOT" \
    ${CONNECTION:+--connection "$CONNECTION"} \
    ${REPO_FILTER:+--repo "$REPO_FILTER"} \
    --shell bash)"

# Separate the machine-readable "# repos: ..." comment from exports.
REPOS_LINE="$(printf '%s\n' "$RESOLVE_OUT" | grep '^# repos:' || true)"
REPOS_CSV="${REPOS_LINE#\# repos: }"
EXPORTS="$(printf '%s\n' "$RESOLVE_OUT" | grep -v '^# repos:')"

# Eval in current shell so CLAUDE_CONFIG_DIR + secrets propagate.
eval "$EXPORTS"

# Auto-register this maestro folder so `maestro upgrade` knows about it.
# Best-effort and silent — never block the launch on registration failure.
# Only when launch-settings.yaml exists (otherwise there's nothing for
# upgrade to walk later).
if [[ "$DRY_RUN" -ne 1 && -f "$MAESTRO_ROOT/launch-settings.yaml" ]]; then
    ${PYTHON} "$SCRIPT_DIR/../cli/maestro.py" launcher register "$MAESTRO_ROOT" >/dev/null 2>&1 || true
fi

# ------------------------------------------------------------------
# --list-repos shortcut

if [[ "$LIST_REPOS" -eq 1 ]]; then
    if [[ -z "$REPOS_CSV" ]]; then
        echo "(no repos found in platform.yaml)"
    else
        printf '%s\n' "$REPOS_CSV" | tr ',' '\n'
    fi
    exit 0
fi

# ------------------------------------------------------------------
# Display resolved state (stderr — doesn't pollute exports for piping)

{
    echo "otaman launcher"
    echo "  otaman root:     $MAESTRO_ROOT"
    echo "  connection:      ${OTAMAN_ACTIVE_CONNECTION:-${MAESTRO_ACTIVE_CONNECTION:-<none>}}"
    echo "  routing:         ${OTAMAN_ACTIVE_ROUTING:-${OTAMAN_ACTIVE_ACCOUNT:-${MAESTRO_ACTIVE_ACCOUNT:-<none>}}}"
    echo "  CLAUDE_CONFIG_DIR=${CLAUDE_CONFIG_DIR:-<unset>}"
    echo "  mode:            $SHELL_MODE"
} >&2

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "" >&2
    echo "--- resolved exports ---" >&2
    printf '%s\n' "$EXPORTS" >&2
    echo "" >&2
    case "$SHELL_MODE" in
        bash)
            echo "would exec: claude -c ${EXTRA_ARGS[*]:-/otaman:check} || claude ${EXTRA_ARGS[*]:-/otaman:check}" >&2
            ;;
        tmux)
            echo "would spawn tmux windows for repos: $REPOS_CSV" >&2
            ;;
        print)
            echo "would print exec-line for sourcing" >&2
            ;;
    esac
    exit 0
fi

# ------------------------------------------------------------------
# Dispatch

# `-c` (continue) resumes the prior session in this cwd. On a fresh cwd
# it exits non-zero with "No conversation found to continue", so we fall
# back to a no-flag launch — that makes the launcher idempotent across
# SSH reconnects (the second-and-later launches keep context) without
# breaking the first launch. (Backlog M-3 + first-run fix.)
claude_cmd_continue=("claude" "-c" "/otaman:check")
claude_cmd_fresh=("claude" "/otaman:check")
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    claude_cmd_continue=("claude" "-c" "${EXTRA_ARGS[@]}")
    claude_cmd_fresh=("claude" "${EXTRA_ARGS[@]}")
fi

case "$SHELL_MODE" in
    bash)
        if ! command -v claude >/dev/null 2>&1; then
            echo "error: 'claude' not on PATH" >&2
            exit 1
        fi
        # Try continue; fall back to fresh launch on non-zero (no prior
        # session in this cwd). `exec` is on the fresh path so the parent
        # shell still gets replaced — same behavior as before for the
        # common case.
        "${claude_cmd_continue[@]}" || exec "${claude_cmd_fresh[@]}"
        ;;

    print)
        # Emit a shell snippet the user can `source` or copy. stdout only —
        # stderr already has the status banner.
        printf '%s\n' "$EXPORTS"
        printf '%s || exec %s\n' "${claude_cmd_continue[*]}" "${claude_cmd_fresh[*]}"
        ;;

    tmux)
        if ! command -v tmux >/dev/null 2>&1; then
            echo "error: tmux not installed" >&2
            exit 1
        fi
        if [[ -z "$REPOS_CSV" ]]; then
            echo "error: no repos in platform.yaml; tmux mode needs at least one" >&2
            exit 1
        fi
        session="otaman-${OTAMAN_ACTIVE_CONNECTION:-${MAESTRO_ACTIVE_CONNECTION:-default}}"
        # Resolve per-repo paths using platform.yaml via Python (keeps bash
        # free of YAML parsing). Paths are relative to MAESTRO_ROOT.
        mapfile -t repo_paths < <(
            ${PYTHON} - <<EOF
import sys, yaml, pathlib
root = pathlib.Path("$MAESTRO_ROOT")
with open(root / "platform.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}
for r in cfg.get("repos", []) or []:
    if not isinstance(r, dict) or r.get("disabled"):
        continue
    p = r.get("path", "")
    resolved = (root / p).resolve() if p else root
    print(f"{r.get('name','')}|{resolved}")
EOF
        )

        if [[ -z "$REPO_FILTER" ]]; then
            filtered=("${repo_paths[@]}")
        else
            filtered=()
            for row in "${repo_paths[@]}"; do
                name="${row%%|*}"
                [[ "$name" == "$REPO_FILTER" ]] && filtered+=("$row")
            done
            if [[ ${#filtered[@]} -eq 0 ]]; then
                echo "error: --repo '$REPO_FILTER' not found in platform.yaml" >&2
                exit 1
            fi
        fi

        # Respawn loop: if claude exits (/exit, Ctrl-D, crash), prompt the
        # user to press Enter for a fresh attach instead of stranding the
        # tmux window at a bare bash prompt. Ctrl-C at the prompt drops
        # to the shell as before. `-c` falls back to a no-flag launch
        # when there's no prior session in that cwd. (Backlog M-13a.)
        claude_loop="while :; do claude -c /otaman:check || claude /otaman:check; printf '\\n[claude exited — Enter to respawn, Ctrl-C to drop to shell] '; read -r || break; done"

        if tmux has-session -t "$session" 2>/dev/null; then
            echo "tmux: attaching to existing session '$session'" >&2
        else
            first="${filtered[0]}"
            first_name="${first%%|*}"
            first_path="${first#*|}"
            tmux new-session -d -s "$session" -n "$first_name" -c "$first_path"
            tmux send-keys -t "$session:$first_name" "$claude_loop" C-m
            filtered=("${filtered[@]:1}")
        fi

        for row in "${filtered[@]}"; do
            name="${row%%|*}"
            path="${row#*|}"
            tmux new-window -t "$session" -n "$name" -c "$path"
            tmux send-keys -t "$session:$name" "$claude_loop" C-m
        done

        if [[ -n "${TMUX:-}" ]]; then
            tmux switch-client -t "$session"
        else
            exec tmux attach -t "$session"
        fi
        ;;
esac
