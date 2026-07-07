#!/usr/bin/env bash
# Launch Claude Code agents for an otaman project (bash parity with
# launch-agents.ps1). Set CLAUDE_CONFIG_DIR from the active connection's
# account, load secrets.env (.otaman/secrets.env preferred;
# legacy: .maestro/secrets.env fallback honored), then exec claude or spawn tmux.
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
#       --no-runner         Skip otaman-runner; spawn tmux sessions directly
#                           (legacy / offline mode). Default is to call the
#                           runner's HTTP /spawn first per ADR-009; the launcher
#                           already falls back automatically when the endpoint
#                           file is missing, so this flag is mainly for users
#                           who explicitly want to bypass a running daemon.
#       --via-runner        Deprecated no-op (runner is now the default in tmux
#                           mode). Kept for backward compatibility.
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
# Dispatch to otaman-runner via HTTP API (per ADR-009).
# Runner-first is the default in tmux mode (auto-session-spawn-implementation
# task 4.2). Falls back to direct tmux spawn when the runner endpoint file is
# missing or any /spawn call fails — preserves Mode 1 (no daemon) operation
# and dev/offline use. Pass --no-runner to skip the runner entirely.
#
# Implements just enough of the runner client protocol to spawn one
# session per repo in interactive (tmux) mode. Each /spawn returns an
# AttachInfo; we exec the first one (or print all if --dry-run).

read_runner_endpoint() {
    local path="${HOME}/.otaman/runner.endpoint"
    [[ -f "$path" ]] || return 1
    local host port token
    while IFS='=' read -r key val; do
        case "$key" in
            host) host="$val" ;;
            port) port="$val" ;;
            token) token="$val" ;;
        esac
    done < "$path"
    [[ -n "$host" && -n "$port" && -n "$token" ]] || return 1
    printf '%s\n%s\n%s\n' "$host" "$port" "$token"
    return 0
}

# Spawn one repo via runner HTTP API. Echoes the validated session_name on
# success, returns non-zero on any error. Builds and parses JSON via
# small Python helpers (avoids a jq dependency).
#
# F072: the /spawn reply comes back over the network. We return only the
# structured `attach.session_name` (never the runner's `attach_command`
# string, which the caller used to `eval`). The name is charset-validated
# here so the caller can use it as a literal tmux target with no shell eval.
runner_spawn_one() {
    local host="$1" port="$2" token="$3"
    local agent="$4" repo="$5" project_root="$6" account="${7:-}" human="${8:-}"
    local body
    # Body shape per auto-session-spawn-implementation proposal §4 and the
    # runner daemon's _request_from_dict: agent/repo/project_root/mode are
    # required by the runner; account + human are forwarded when set; the
    # runner uses `human` (bridge-facing alias for `user`) for session-registry
    # dedup keys (per Q1 of auto-session-spawn-on-bus-events/design.md).
    body=$(${PYTHON} -c '
import json, sys
agent, repo, project_root, account, human = sys.argv[1:6]
print(json.dumps({
    "agent": agent,
    "repo": repo,
    "project_root": project_root,
    "mode": "interactive",
    "account": account or None,
    "human": human or None,
}))
' "$agent" "$repo" "$project_root" "$account" "$human")
    local resp
    resp=$(curl -sS --max-time 30 \
        -X POST "http://${host}:${port}/spawn" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$body" 2>&1) || {
        echo "runner_spawn_one: HTTP error: $resp" >&2
        return 1
    }
    ${PYTHON} -c '
import json, re, sys
data = json.loads(sys.argv[1])
attach = data.get("attach")
if not attach:
    sys.exit("runner_spawn_one: no attach info in response: " + repr(data))
# F072: return the structured session name, not the runner-supplied
# attach_command. Enforce a strict charset so the caller can attach via
# argv (tmux exact-match target) instead of eval-ing network text.
session = attach.get("session_name")
if not session or not re.match(r"^[A-Za-z0-9._:=-]+$", session):
    sys.exit("runner_spawn_one: missing or invalid session_name: " + repr(session))
print(session)
' "$resp"
}

# ------------------------------------------------------------------
# CLI parsing

CONNECTION=""
SHELL_MODE="bash"   # bash | tmux | print
REPO_FILTER=""
LIST_REPOS=0
DRY_RUN=0
# Runner-first is the default in tmux mode (auto-session-spawn-implementation
# task 4.2). `--no-runner` opts out for direct tmux spawn. The legacy
# `--via-runner` flag remains accepted as a no-op for back-compat.
VIA_RUNNER=1
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
        --via-runner)
            # Deprecated no-op — runner-first is now the default in tmux mode.
            shift
            ;;
        --no-runner)
            VIA_RUNNER=0
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
# Resolve otaman root + determine python interpreter

MAESTRO_ROOT="$(find_maestro_root "$PWD" 2>/dev/null || true)"
if [[ -z "$MAESTRO_ROOT" ]]; then
    echo "error: no otaman folder found from $PWD" >&2
    echo "hint: run from inside a managed repo, set OTAMAN_ROOT, or create a .otaman marker" >&2
    echo "      (legacy: MAESTRO_ROOT / .maestro marker still honored)" >&2
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
    --otaman-root "$MAESTRO_ROOT" \
    ${CONNECTION:+--connection "$CONNECTION"} \
    ${REPO_FILTER:+--repo "$REPO_FILTER"} \
    --shell bash)"

# Separate the machine-readable "# repos: ..." comment from exports.
REPOS_LINE="$(printf '%s\n' "$RESOLVE_OUT" | grep '^# repos:' || true)"
REPOS_CSV="${REPOS_LINE#\# repos: }"
EXPORTS="$(printf '%s\n' "$RESOLVE_OUT" | grep -v '^# repos:')"

# Eval in current shell so CLAUDE_CONFIG_DIR + secrets propagate.
eval "$EXPORTS"

# Auto-register this otaman folder so `otaman upgrade` knows about it.
# Best-effort and silent — never block the launch on registration failure.
# Only when launch-settings.yaml exists (otherwise there's nothing for
# upgrade to walk later).
#
# Calls the `otaman` CLI on PATH; the polyrepo split moved the launcher-
# register subcommand out of the plugin tree, so the legacy `cli/maestro.py`  # legacy: cli/maestro.py path
# reference here is dead. If `otaman` isn't on PATH, the redirect + `|| true`
# keep the launch silent.
if [[ "$DRY_RUN" -ne 1 && -f "$MAESTRO_ROOT/launch-settings.yaml" ]]; then
    otaman launcher register "$MAESTRO_ROOT" >/dev/null 2>&1 || true
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
        # Readiness probe (M-15): cold first launch can race the slash-command
        # resolver before plugin slash commands finish registering, surfacing
        # as a one-off "Unknown command" flicker. `claude --version` forces
        # the runtime to initialize without consuming the prompt arg.
        claude --version >/dev/null 2>&1 || true
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
        printf 'claude --version >/dev/null 2>&1 || true\n'
        printf '%s || exec %s\n' "${claude_cmd_continue[*]}" "${claude_cmd_fresh[*]}"
        ;;

    tmux)
        # Runner-first dispatch (default in tmux mode per
        # auto-session-spawn-implementation task 4.2). Each repo's spawn goes
        # through otaman-runner's HTTP /spawn endpoint; the runner creates the
        # tmux session with the canonical ${project}:${owner} name and returns
        # the attach_command. If the endpoint file is missing or any /spawn
        # fails, the launcher warns and falls back to the direct-tmux path
        # below. `--no-runner` skips this branch entirely (offline / dev mode).
        if [[ "$VIA_RUNNER" -eq 1 ]]; then
            if mapfile -t _endpoint < <(read_runner_endpoint); then
                _host="${_endpoint[0]}"
                _port="${_endpoint[1]}"
                _token="${_endpoint[2]}"
                _human="${USER:-${LOGNAME:-}}"
                echo "runner: spawning via http://${_host}:${_port} (human=${_human:-<unset>})" >&2
                # Build the repo list using same Python parse as the local path
                mapfile -t _repo_rows < <(
                    ${PYTHON} - <<EOF
import yaml, pathlib
root = pathlib.Path("$MAESTRO_ROOT")
with open(root / "platform.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}
for r in cfg.get("repos", []) or []:
    if not isinstance(r, dict) or r.get("disabled"):
        continue
    name = r.get("name", "")
    owner = r.get("owner", name)
    print(f"{name}|{owner}")
EOF
                )
                _session_first=""
                for _row in "${_repo_rows[@]}"; do
                    _repo_name="${_row%%|*}"
                    _agent_name="${_row#*|}"
                    if [[ -n "$REPO_FILTER" && "$_repo_name" != "$REPO_FILTER" ]]; then
                        continue
                    fi
                    _session=$(runner_spawn_one "$_host" "$_port" "$_token" \
                        "$_agent_name" "$_repo_name" "$MAESTRO_ROOT" \
                        "${MAESTRO_ACTIVE_ACCOUNT:-}" "$_human") || {
                        echo "runner: spawn failed for $_repo_name; falling back to direct tmux spawn" >&2
                        VIA_RUNNER=0
                        break
                    }
                    echo "  spawned $_agent_name@$_repo_name → session $_session" >&2
                    [[ -z "$_session_first" ]] && _session_first="$_session"
                done
                if [[ "$VIA_RUNNER" -eq 1 && -n "$_session_first" ]]; then
                    echo "" >&2
                    echo "attaching to first session: $_session_first" >&2
                    # F072: attach via argv — never eval runner-supplied text.
                    # runner_spawn_one already validated the session-name
                    # charset; tmux receives '=<session>' as a single literal
                    # exact-match target (the '=' guards the ':' in the name).
                    exec tmux attach -t "=$_session_first"
                fi
            else
                echo "runner: no endpoint file at ~/.otaman/runner.endpoint; falling back to direct tmux spawn (start the runner daemon or pass --no-runner to silence)" >&2
                VIA_RUNNER=0
            fi
        fi
        if ! command -v tmux >/dev/null 2>&1; then
            echo "error: tmux not installed" >&2
            exit 1
        fi
        if [[ -z "$REPOS_CSV" ]]; then
            echo "error: no repos in platform.yaml; tmux mode needs at least one" >&2
            exit 1
        fi
        # Read top-level `project:` field from platform.yaml. Session names
        # are constructed as "${project}:${owner}" per fix-launcher-tmux-session-naming.
        project=$(${PYTHON} - <<EOF
import yaml, pathlib
root = pathlib.Path("$MAESTRO_ROOT")
with open(root / "platform.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}
print(cfg.get("project", "otaman"))
EOF
)
        # Resolve per-repo paths and owners using platform.yaml via Python
        # (keeps bash free of YAML parsing). Paths are relative to MAESTRO_ROOT.
        # Output format per repo: <name>|<resolved_path>|<owner>
        # `owner` falls back to `name` when absent (with no warning here — the
        # PS1 launcher emits the warning; bash trusts the YAML).
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
    name = r.get("name", "")
    owner = r.get("owner") or name
    print(f"{name}|{resolved}|{owner}")
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
        #
        # The leading `claude --version` is M-15's readiness probe — forces
        # the runtime to initialize so plugin slash commands are registered
        # before the first `/otaman:check` reaches the prompt parser. Cheap
        # (~50ms) and silent. Subsequent loop iterations rely on the
        # already-warm process state.
        claude_loop="claude --version >/dev/null 2>&1 || true; while :; do claude -c /otaman:check || claude /otaman:check; printf '\\n[claude exited -- Enter to respawn, Ctrl-C to drop to shell] '; read -r || break; done"

        # One session per repo. Session name: "${project}:${owner}". The `=`
        # prefix on -t forces exact match (tmux 2.5+) so `otaman:plugin-agent`
        # is not parsed as session `otaman`, window `plugin-agent`.
        #
        # Window name is set to the repo name (task 1.5) so the tmux status
        # bar reads "<project>:<owner>:<repo>" — surfaces project + agent +
        # program at a glance without context-switching.
        first_session=""
        for row in "${filtered[@]}"; do
            IFS='|' read -r name path owner <<< "$row"
            session="${project}:${owner}"
            if tmux has-session -t "=${session}" 2>/dev/null; then
                echo "tmux: session '$session' already running; not respawning" >&2
            else
                tmux new-session -d -s "$session" -n "$name" -c "$path"
                tmux send-keys -t "=${session}" "$claude_loop" C-m
            fi
            [[ -z "$first_session" ]] && first_session="$session"
        done

        if [[ -n "${TMUX:-}" ]]; then
            tmux switch-client -t "=${first_session}"
        else
            exec tmux attach -t "=${first_session}"
        fi
        ;;
esac
