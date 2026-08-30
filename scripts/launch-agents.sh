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
#       --interactive       Force interactive acting mode. Interactive launches
#                           pass --preempt to `otaman acting-lock run` so they
#                           may cooperatively take over a background holder.
#       --background        Force background acting mode. Background launches
#                           never preempt; a held identity refuses (exit 2).
#                           Default (neither flag): inferred from a TTY.
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
# single-acting-session-guard (tasks 1.1-1.4) — plugin (launcher) half.
#
# INTEROP RULING 20260829T222512: the launcher is a THIN WRAPPER over the CLI
# verb `otaman acting-lock`. The lock primitive lives in
# `otaman_core.acting_lock` and is exposed via cli — the launcher MUST NOT
# reimplement any of it (no flock, no lock-key derivation, no lockfile paths,
# no sidecar, no preempt marker). The launcher only:
#   * DECIDES the acting mode (interactive vs background) and whether to
#     pass --preempt (task 1.3),
#   * routes the launch through the identity tmux session and does
#     attach-first (task 1.2),
#   * wraps the claude respawn loop in `otaman acting-lock run` so the lock
#     is held (by cli) across respawns (task 1.1),
#   * in the no-tmux case runs the wrapper in the foreground and, on a
#     held-lock refusal (exit 2), surfaces the holder via
#     `otaman acting-lock probe` and optionally runs a passive read-only
#     mirror — never a second acting session (task 1.4).
#
# The CLI verb contract wrapped here (otaman-cli commit d64a21a):
#   otaman acting-lock run --mode interactive|background [--preempt] -- <cmd…>
#     resolves the acting identity itself (org/program/agent from the CE
#     layout + OTAMAN_AGENT), derives the lock key, ACQUIRES the flock, and
#     runs <cmd> as a CHILD while holding the fd for the run's lifetime.
#     Exit codes: child's exit code on success; exit 2 if the lock is held
#     and not preemptible (message names holder pid + tmux attach command);
#     with --preempt (interactive only) it writes a preempt marker, waits a
#     10s handoff window, then acquires or exits 2 naming the wedged holder.
#   otaman acting-lock probe [--json]
#     reports the live holder. Exit 0 = held, 1 = free. --json prints
#     {"held": bool, "holder": {"pid","mode","tmux_session","started_at"}|null}.
#
# Because cli resolves identity and owns the lock file, the launcher needs
# NONE of that — no org/program/agent derivation for the lock, no lockfile
# paths. It still needs project/owner ONLY to name the tmux session (as the
# existing tmux path does).

# Detect this launch's acting mode. Explicit flags win; otherwise infer from a
# TTY on stdin/stdout (interactive when attached to a terminal, background
# otherwise). Task 1.3 — the launcher only DECIDES mode; cli owns the lock.
acting_detect_mode() {
    local forced="$1"  # "interactive" | "background" | ""
    if [[ -n "$forced" ]]; then
        printf '%s\n' "$forced"
        return 0
    fi
    if [[ -t 0 || -t 1 ]]; then
        printf 'interactive\n'
    else
        printf 'background\n'
    fi
}

# Sanitize a "${project}:${owner}" pair into a tmux-safe session name. tmux
# rejects '.' and ':' in session names and silently rewrites them to '_' on
# new-session (tmux 3.x). We pre-sanitize so create / has-session / attach all
# key on the SAME literal string tmux stores — otherwise
# `has-session -t "=proj:agent"` never matches the stored `proj_agent` and
# attach-first (task 1.2) would spuriously start a second session.
acting_session_name() {
    local project="$1" owner="$2"
    printf '%s:%s' "$project" "$owner" | tr '.:' '__'
}

# ------------------------------------------------------------------
# CLI parsing

CONNECTION=""
SHELL_MODE="bash"   # bash | tmux | print
REPO_FILTER=""
LIST_REPOS=0
DRY_RUN=0
# single-acting-session-guard: forced acting mode (empty = infer from TTY).
FORCE_MODE=""
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
        --interactive)
            FORCE_MODE="interactive"
            shift
            ;;
        --background)
            FORCE_MODE="background"
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
# single-acting-session-guard: resolve project + owner (for the identity tmux
# session name ONLY) and this launch's acting mode. cli owns the lock key and
# lockfile — the launcher does NOT derive them. <project> is platform.yaml
# `project:` (same value the tmux path uses for session names); <owner> is the
# selected repo's owner (--repo when given, else the FIRST enabled repo — the
# one the launcher attaches to first).
ACTING_PROGRAM=""
ACTING_OWNER=""
if [[ "$LIST_REPOS" -ne 1 ]]; then
    _acting_meta="$(${PYTHON} - "$MAESTRO_ROOT" "$REPO_FILTER" <<'EOF'
import sys, yaml, pathlib
root = pathlib.Path(sys.argv[1])
repo_filter = sys.argv[2] if len(sys.argv) > 2 else ""
try:
    with open(root / "platform.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
except OSError:
    cfg = {}
program = cfg.get("project", "otaman")
owner = ""
first_owner = ""
for r in cfg.get("repos", []) or []:
    if not isinstance(r, dict) or r.get("disabled"):
        continue
    name = r.get("name", "")
    o = r.get("owner") or name
    if not first_owner:
        first_owner = o
    if repo_filter and name == repo_filter:
        owner = o
        break
if not owner:
    owner = first_owner or program
print(program)
print(owner)
EOF
)"
    ACTING_PROGRAM="$(printf '%s\n' "$_acting_meta" | sed -n '1p')"
    ACTING_OWNER="$(printf '%s\n' "$_acting_meta" | sed -n '2p')"
fi
ACTING_MODE="$(acting_detect_mode "$FORCE_MODE")"
ACTING_SESSION="$(acting_session_name "${ACTING_PROGRAM:-otaman}" "${ACTING_OWNER:-otaman}")"
# Interactive launches preempt (cli does the marker + 10s handoff); background
# launches NEVER preempt (task 1.3). PREEMPT_FLAG expands to nothing or
# "--preempt".
ACTING_PREEMPT_FLAG=""
[[ "$ACTING_MODE" == "interactive" ]] && ACTING_PREEMPT_FLAG="--preempt"

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
    echo "  acting mode:     $ACTING_MODE"
    echo "  acting session:  $ACTING_SESSION"
} >&2

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "" >&2
    echo "--- resolved exports ---" >&2
    printf '%s\n' "$EXPORTS" >&2
    echo "" >&2
    case "$SHELL_MODE" in
        bash)
            echo "would route acting launch through identity tmux session '${ACTING_SESSION}'" >&2
            echo "  - if that session is live: probe/has-session then attach into it (no second acting process)" >&2
            echo "  - else: wrap the claude respawn loop in:" >&2
            echo "      otaman acting-lock run --mode ${ACTING_MODE} ${ACTING_PREEMPT_FLAG:-<no --preempt>} -- <respawn loop>" >&2
            echo "    (cli acquires the flock, resolves identity, holds it across respawns)" >&2
            echo "  - acting mode=${ACTING_MODE}; interactive passes --preempt (cli does the 10s handoff)" >&2
            echo "  - no tmux available: run the wrapper in the foreground; on a held-lock refusal (exit 2)" >&2
            echo "    print the holder from 'otaman acting-lock probe --json' and run a passive read-only mirror" >&2
            echo "  (dry-run: no probe, no lock acquired, nothing spawned)" >&2
            ;;
        tmux)
            echo "would spawn tmux windows for repos: $REPOS_CSV" >&2
            ;;
        print)
            echo "would print exec-line wrapping 'otaman acting-lock run --mode ${ACTING_MODE}' for sourcing" >&2
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

# single-acting-session-guard: build the claude RESPAWN LOOP that cli's
# `acting-lock run` will hold the lock across (task 1.1). The loop preserves
# the M-15 `claude --version` readiness probe and the respawn/Enter semantics
# of the existing tmux path. Passing the loop (not a bare `claude`) as the
# wrapped command means the lock is held for the whole respawn lifetime — a
# /exit + respawn does not drop and re-take the lock, so it cannot split-brain.
#
# The continue-or-fresh commands are embedded as literal argv via printf %q so
# any --  EXTRA_ARGS survive intact inside the `bash -lc` string.
_acting_build_loop() {
    local cont fresh
    cont="$(printf '%q ' "${claude_cmd_continue[@]}")"
    fresh="$(printf '%q ' "${claude_cmd_fresh[@]}")"
    printf 'claude --version >/dev/null 2>&1 || true; while :; do %s|| %s|| true; printf "\\n[claude exited -- Enter to respawn, Ctrl-C to drop to shell] "; read -r || break; done' "$cont" "$fresh"
}

# Surface the current acting holder (pid + reattach command) from cli's probe
# after a held-lock refusal (exit 2). cli's own refusal message already names
# the pid + attach command; this is the launcher's structured fallback for the
# no-tmux path (task 1.4) using `otaman acting-lock probe --json`.
acting_print_holder() {
    local session="$1"
    local probe_json
    probe_json="$(otaman acting-lock probe --json 2>/dev/null || true)"
    if [[ -n "$probe_json" ]]; then
        ${PYTHON} - "$probe_json" "$session" <<'EOF' >&2 || true
import json, sys
raw = sys.argv[1]
fallback_session = sys.argv[2] if len(sys.argv) > 2 else ""
try:
    data = json.loads(raw)
except ValueError:
    sys.exit(0)
holder = (data or {}).get("holder") or {}
pid = holder.get("pid", "?")
sess = holder.get("tmux_session") or fallback_session or "?"
mode = holder.get("mode", "?")
print(f"acting: role already held (pid={pid}, mode={mode}, session={sess}).")
print(f"  reattach with: tmux attach-session -t '={sess}'")
EOF
    else
        echo "acting: role already held; could not probe holder (otaman acting-lock probe failed)." >&2
        echo "  reattach with: tmux attach-session -t '=${session}'" >&2
    fi
}

case "$SHELL_MODE" in
    bash)
        if ! command -v claude >/dev/null 2>&1; then
            echo "error: 'claude' not on PATH" >&2
            exit 1
        fi
        # single-acting-session-guard (tasks 1.1-1.4): route the bash-mode
        # launch through the identity tmux session and wrap the respawn loop
        # in `otaman acting-lock run`. cli owns the flock; the launcher never
        # reimplements it and never starts a SECOND acting process under the
        # same identity.
        acting_loop="$(_acting_build_loop)"
        # Build the wrapper argv once. --mode is always passed; --preempt only
        # on interactive launches (task 1.3). The loop runs under `bash -lc`
        # so the M-15 probe + respawn semantics are preserved.
        acting_run_cmd=(otaman acting-lock run --mode "$ACTING_MODE")
        [[ -n "$ACTING_PREEMPT_FLAG" ]] && acting_run_cmd+=("$ACTING_PREEMPT_FLAG")
        acting_run_cmd+=(-- bash -lc "$acting_loop")

        if command -v tmux >/dev/null 2>&1; then
            # Attach-first (task 1.2): if the identity session is already live,
            # attach the user INTO it (survives pane / auto-update resets) —
            # never a second acting process, never a second `acting-lock run`.
            if tmux has-session -t "=${ACTING_SESSION}" 2>/dev/null; then
                echo "acting: identity session '${ACTING_SESSION}' is live — attaching (no second acting process)." >&2
                if [[ -n "${TMUX:-}" ]]; then
                    exec tmux switch-client -t "=${ACTING_SESSION}"
                else
                    exec tmux attach-session -t "=${ACTING_SESSION}"
                fi
            fi
            # No live identity session: create it and run the wrapper INSIDE
            # the pane via send-keys. cli's `run` holds the lock in its own
            # process inside the pane for the pane's lifetime (no re-exec
            # machinery needed). If cli refuses (held elsewhere), its exit-2
            # message naming the holder pid + attach command lands in the pane.
            echo "acting: creating identity session '${ACTING_SESSION}' and wrapping otaman acting-lock run (mode=${ACTING_MODE})." >&2
            tmux new-session -d -s "$ACTING_SESSION" -n "${ACTING_OWNER:-agent}" -c "$PWD"
            # Compose the send-keys command line with each argv element quoted
            # so --  EXTRA_ARGS / the loop string survive tmux's shell parse.
            _sendline=""
            for _tok in "${acting_run_cmd[@]}"; do
                _sendline+="$(printf '%q' "$_tok") "
            done
            tmux send-keys -t "=${ACTING_SESSION}" "exec ${_sendline}" C-m
            if [[ -n "${TMUX:-}" ]]; then
                exec tmux switch-client -t "=${ACTING_SESSION}"
            else
                exec tmux attach-session -t "=${ACTING_SESSION}"
            fi
        fi

        # ---- No tmux available (containers / minimal images) — task 1.4 ----
        # Run the wrapper in the FOREGROUND; cli acquires the lock or refuses.
        # On a held-lock refusal (exit 2) print the holder (from probe --json)
        # and the exact reattach command, then optionally run claude -c
        # READ-ONLY (no acting slash-command) as a passive mirror. Never a
        # second acting session.
        # Capture the exit code without tripping `set -e` — exit 2 (held) is a
        # normal, handled outcome here, not a launcher error.
        _rc=0
        "${acting_run_cmd[@]}" || _rc=$?
        if [[ "$_rc" -eq 2 ]]; then
            acting_print_holder "$ACTING_SESSION"
            echo "acting: no tmux here — running claude -c as a PASSIVE read-only mirror (NOT acting on the bus)." >&2
            exec claude -c
        fi
        exit "$_rc"
        ;;

    print)
        # Emit a shell snippet the user can `source` or copy. stdout only —
        # stderr already has the status banner. The snippet now wraps
        # `otaman acting-lock run` too, so a copy/pasted launch still goes
        # through cli's flock rather than the old bare split-brain line.
        acting_loop="$(_acting_build_loop)"
        acting_run_cmd=(otaman acting-lock run --mode "$ACTING_MODE")
        [[ -n "$ACTING_PREEMPT_FLAG" ]] && acting_run_cmd+=("$ACTING_PREEMPT_FLAG")
        acting_run_cmd+=(-- bash -lc "$acting_loop")
        printf '%s\n' "$EXPORTS"
        _printline=""
        for _tok in "${acting_run_cmd[@]}"; do
            _printline+="$(printf '%q' "$_tok") "
        done
        # NOTE: print mode emits the wrapper as a single foreground line — it
        # does NOT reproduce the tmux attach-first routing (that needs live
        # tmux state the snippet can't carry). Sourcing the snippet still gets
        # cli's flock via `acting-lock run`, so it cannot split-brain; it just
        # won't auto-attach into an existing identity session.
        printf 'exec %s\n' "$_printline"
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
