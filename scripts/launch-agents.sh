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
#       --interactive       Force interactive mode (may preempt a background
#                           acting holder via cooperative handoff). Default:
#                           inferred from a TTY on stdin/stdout.
#       --background        Force background mode (never preempts; runs as a
#                           passive mirror if the acting role is already held).
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
# Every acting claude session must hold an flock(2) keyed on the RESOLVED,
# program-scoped identity so a second launch under the same identity can
# never split-brain (double-send / double-commit / divergent history).
# The kernel releases the flock on ANY exit — including `kill -9` — so a
# crashed holder never wedges a successor (task 1.1 acceptance).
#
# The flock is the source of truth. A `.info` sidecar carries pid / mode /
# tmux session / started-at for humans, error messages, and cooperative
# preemption. A `.preempt` marker (task 1.3) lets an INTERACTIVE launch ask
# a BACKGROUND holder to demote — flock is never force-broken (no lock
# stealing); the holder cooperatively releases its fd, which frees the lock.
#
# NOTE: the authoritative demote-on-marker behaviour lives in the bus CLI
# (cli-agent's half, a separate repo/task). The launcher writes the marker
# and waits; it must NEVER silently fork a second acting session.

# Derive the org segment for the lock key from the CE directory layout:
#   orgs/<org>/programs/<program>/<meta-dir>
# The otaman root ($MAESTRO_ROOT) is the <meta-dir>. This mirrors
# otaman_plugin.bus_target_port.derive_local_context (positional
# interpretation of the declared layout, NOT discovery). When the tree does
# not conform (legacy / flat layouts) we fall back to the program name so
# the key is still program-scoped and deterministic — a bare agent name can
# legitimately run in two programs, so program scoping is the load-bearing
# part; org is a finer-grained prefix when the layout provides it.
acting_lock_org() {
    local root="$1" program="$2"
    local resolved program_dir programs_dir org_dir
    resolved="$(cd "$root" 2>/dev/null && pwd -P)" || { printf '%s\n' "$program"; return 0; }
    program_dir="$(dirname "$resolved")"
    programs_dir="$(dirname "$program_dir")"
    org_dir="$(dirname "$programs_dir")"
    if [[ "$(basename "$programs_dir")" == "programs" && "$(basename "$(dirname "$org_dir")")" == "orgs" ]]; then
        printf '%s\n' "$(basename "$org_dir")"
    else
        printf '%s\n' "$program"
    fi
}

# Compose the program-scoped lock key: <org>--<program>--<agent>.
acting_lock_key() {
    local org="$1" program="$2" agent="$3"
    printf '%s--%s--%s\n' "$org" "$program" "$agent"
}

# Resolve the lock file path for a key. Prefers $XDG_RUNTIME_DIR/otaman/,
# falls back to ~/.otaman/locks/ when XDG_RUNTIME_DIR is unset/empty.
# Deliberately NOT under .agents/ — that tree is committed program-bus
# canon; runtime ephemera don't belong there. PURE: computes the path only,
# no side effects (so --dry-run can print it without touching the fs). The
# parent dir is created at acquisition time by acting_ensure_lockdir.
acting_lock_path() {
    local key="$1" base
    if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
        base="${XDG_RUNTIME_DIR}/otaman"
    else
        base="${HOME}/.otaman/locks"
    fi
    printf '%s/%s.lock\n' "$base" "$key"
}

# Create the lock file's parent dir. Called only at real acquisition, never
# from the --dry-run display path.
acting_ensure_lockdir() {
    local lockfile="$1"
    mkdir -p "$(dirname "$lockfile")" 2>/dev/null || true
}

# Write the informational sidecar beside the lock (path + ".info").
# Fields: pid, mode, session (tmux session name), started (ISO-8601).
# Informational only — the flock is the source of truth, not this file.
acting_write_sidecar() {
    local lockfile="$1" pid="$2" mode="$3" session="$4"
    local started
    started="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
    {
        printf 'pid=%s\n' "$pid"
        printf 'mode=%s\n' "$mode"
        printf 'session=%s\n' "$session"
        printf 'started=%s\n' "$started"
    } > "${lockfile}.info" 2>/dev/null || true
}

# Read one field from a sidecar (echoes empty when absent).
acting_read_sidecar_field() {
    local lockfile="$1" field="$2"
    [[ -f "${lockfile}.info" ]] || return 0
    local key val
    while IFS='=' read -r key val; do
        [[ "$key" == "$field" ]] && { printf '%s\n' "$val"; return 0; }
    done < "${lockfile}.info"
}

# Detect this launch's mode. Explicit flags win; otherwise infer from a TTY
# on stdin/stdout (interactive attached to a terminal, background otherwise).
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

# Write a preempt marker (task 1.3) asking a background holder to demote.
# INTERACTIVE launches only — a background launch must NEVER call this.
acting_write_preempt() {
    local lockfile="$1" mode="$2"
    local now
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
    {
        printf 'pid=%s\n' "$$"
        printf 'mode=%s\n' "$mode"
        printf 'requested=%s\n' "$now"
    } > "${lockfile}.preempt" 2>/dev/null || true
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
# HIDDEN internal re-entry state (set by --_acting-inner).
ACTING_INNER=0
ACTING_INNER_LOCKFILE=""
ACTING_INNER_MODE=""
ACTING_INNER_SESSION=""
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
        --_acting-inner)
            # HIDDEN: internal re-entry used by acting_launch to run the
            # acting claude INSIDE the freshly-created identity tmux session.
            # Args: <lockfile> <mode> <session>. Not for direct use.
            ACTING_INNER=1
            ACTING_INNER_LOCKFILE="${2:-}"
            ACTING_INNER_MODE="${3:-}"
            ACTING_INNER_SESSION="${4:-}"
            shift 4
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
# single-acting-session-guard: resolve identity (org / program / agent),
# the lock key + path, and this launch's mode. Shared by the bash and tmux
# acting-dispatch paths so both key on the SAME program-scoped identity.
#
# <program> is platform.yaml `project:` (same value the tmux path uses for
# session names). <agent> is this repo's `owner`. When --repo is given we
# use that repo's owner; otherwise the FIRST enabled repo's owner (the one
# the launcher would attach to first). <org> comes from the CE path layout.
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
ACTING_ORG="$(acting_lock_org "$MAESTRO_ROOT" "${ACTING_PROGRAM:-otaman}")"
ACTING_KEY="$(acting_lock_key "$ACTING_ORG" "${ACTING_PROGRAM:-otaman}" "${ACTING_OWNER:-otaman}")"
ACTING_MODE="$(acting_detect_mode "$FORCE_MODE")"
# Identity tmux session name follows the "${project}:${owner}" convention the
# existing tmux path uses. tmux rejects '.' and ':' in session names and
# silently rewrites them to '_' on new-session (tmux 3.x). We pre-sanitize so
# create / has-session / attach all key on the SAME literal string tmux stores
# — otherwise `has-session -t "=proj:agent"` never matches the stored
# `proj_agent` and attach-first (task 1.2) would spuriously start a second
# session. (The runner-created tmux path is unaffected; the acting path
# creates and attaches its identity session self-consistently.)
ACTING_SESSION="$(printf '%s:%s' "${ACTING_PROGRAM}" "${ACTING_OWNER}" | tr '.:' '__')"

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
    echo "  acting identity: ${ACTING_KEY:-<unresolved>} (${ACTING_MODE})"
    echo "  acting session:  ${ACTING_SESSION}"
    echo "  acting lockfile: $(acting_lock_path "$ACTING_KEY")"
} >&2

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "" >&2
    echo "--- resolved exports ---" >&2
    printf '%s\n' "$EXPORTS" >&2
    echo "" >&2
    case "$SHELL_MODE" in
        bash)
            echo "would route acting launch through identity tmux session '${ACTING_SESSION}'" >&2
            echo "  - if that session is live: attach into it (no second acting process)" >&2
            echo "  - else: acquire flock $(acting_lock_path "$ACTING_KEY") and run:" >&2
            echo "      claude -c ${EXTRA_ARGS[*]:-/otaman:check} || claude ${EXTRA_ARGS[*]:-/otaman:check}" >&2
            echo "  - mode=${ACTING_MODE}; interactive may preempt a background holder (cooperative handoff)" >&2
            echo "  - no tmux available: passive read-only mirror (never a second acting session)" >&2
            echo "  (dry-run: no lock acquired, nothing spawned)" >&2
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

# ------------------------------------------------------------------
# single-acting-session-guard — acting-launch orchestration (tasks 1.2-1.4).
#
# acting_run_inside_lock: acquire the flock, write the sidecar, run the
# continue-or-fresh claude command while HOLDING the fd for the process
# lifetime. Executed inside the identity tmux session (or, degenerate no-tmux
# case, in the foreground). The plain `exec {fd}>file` fd survives the exec
# into claude (no close-on-exec) so the kernel releases the lock only when
# the acting process finally exits — including on `kill -9` (task 1.1).
acting_run_inside_lock() {
    local lockfile mode session
    lockfile="$1"; mode="$2"; session="$3"
    acting_ensure_lockdir "$lockfile"
    local lockfd
    exec {lockfd}>"$lockfile"
    if ! flock -n "$lockfd"; then
        # Someone else already holds it. Name the holder from the sidecar so
        # the human knows what to reach for — NEVER fork a second acting
        # session.
        local holder_pid holder_session
        holder_pid="$(acting_read_sidecar_field "$lockfile" pid)"
        holder_session="$(acting_read_sidecar_field "$lockfile" session)"
        echo "acting lock held by pid=${holder_pid:-?} session=${holder_session:-?}; not starting a second acting session." >&2
        echo "  reattach with: tmux attach-session -t '=${holder_session:-$session}'" >&2
        return 3
    fi
    acting_write_sidecar "$lockfile" "$$" "$mode" "$session"
    # Consume any stale preempt marker we may have inherited — we ARE the
    # acting session now.
    rm -f "${lockfile}.preempt" 2>/dev/null || true
    # Readiness probe (M-15) — see the historical note on the bash path.
    claude --version >/dev/null 2>&1 || true
    # Respawn loop mirrors the tmux path so a /exit or crash inside the
    # identity session offers a clean re-attach rather than stranding a bare
    # shell. The lock fd stays open across each claude invocation.
    while :; do
        "${claude_cmd_continue[@]}" || "${claude_cmd_fresh[@]}" || true
        printf '\n[claude exited -- Enter to respawn, Ctrl-C to drop to shell] '
        read -r || break
    done
}

# acting_try_preempt: INTERACTIVE-only cooperative handoff (task 1.3). If the
# lock is held by a BACKGROUND session, write a preempt marker and wait up to
# 10s for the holder to demote (its fd closes -> flock frees). A dead holder's
# lock is already free via the kernel, so still-held after the wait means the
# holder is alive and wedged — we keep waiting with a message naming the pid,
# never forking a second acting session. Returns 0 if the caller may proceed
# to acquire (lock is/looks free or holder is background), non-zero to defer.
acting_try_preempt() {
    local lockfile="$1"
    local holder_mode holder_pid
    holder_mode="$(acting_read_sidecar_field "$lockfile" mode)"
    holder_pid="$(acting_read_sidecar_field "$lockfile" pid)"
    if [[ "$holder_mode" == "interactive" ]]; then
        # Interactive never preempts interactive — the attach path should have
        # handled this; if we got here (no tmux), fall through to mirror.
        return 1
    fi
    echo "acting: interactive launch preempting background holder pid=${holder_pid:-?} (cooperative handoff, 10s)" >&2
    acting_write_preempt "$lockfile" "interactive"
    local waited=0
    while (( waited < 10 )); do
        # Probe the lock non-destructively in a subshell so we never hold it
        # here — acquisition happens later in acting_run_inside_lock.
        if ( exec {pfd}>"$lockfile"; flock -n "$pfd" ) 2>/dev/null; then
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done
    holder_pid="$(acting_read_sidecar_field "$lockfile" pid)"
    echo "acting: holder pid=${holder_pid:-?} did not demote within 10s; still waiting." >&2
    echo "  the background holder appears alive and wedged — kill pid ${holder_pid:-?} to release, or attach to its session." >&2
    # Keep waiting rather than fork a second acting session.
    while :; do
        if ( exec {pfd}>"$lockfile"; flock -n "$pfd" ) 2>/dev/null; then
            return 0
        fi
        sleep 2
    done
}

# acting_passive_mirror: last-resort degenerate path (task 1.4) — tmux is
# genuinely unavailable AND the acting role is held. Print the holder pid +
# session + exact reattach command, then run claude READ-ONLY (no acting
# slash-command). Never becomes a second acting session.
acting_passive_mirror() {
    local lockfile="$1" session="$2"
    local holder_pid holder_session
    holder_pid="$(acting_read_sidecar_field "$lockfile" pid)"
    holder_session="$(acting_read_sidecar_field "$lockfile" session)"
    {
        echo "acting: role already held (pid=${holder_pid:-?}, session=${holder_session:-$session})."
        echo "tmux is unavailable here, so this launch runs as a PASSIVE read-only mirror — it is NOT acting on the bus."
        if command -v tmux >/dev/null 2>&1; then
            echo "reattach to the live session with: tmux attach-session -t '=${holder_session:-$session}'"
        else
            echo "no multiplexer available; reach the holder (pid ${holder_pid:-?}) on its host to interact with the live session."
        fi
    } >&2
    # A passive mirror opens claude with NO acting slash-command so it cannot
    # double-send/commit. `-c` resumes read-only context if any.
    exec claude -c
}

# acting_launch: the create-or-attach entry point shared by the bash path
# (task 1.2). Routes ALL acting launches through the identity tmux session so
# a fresh process after a pane/auto-update reset re-lands in the SAME session
# under the SAME lock — the -c continue-vs-fresh distinction can no longer
# split-brain.
acting_launch() {
    local lockfile session mode
    lockfile="$1"; session="$2"; mode="$3"
    acting_ensure_lockdir "$lockfile"

    if command -v tmux >/dev/null 2>&1; then
        if tmux has-session -t "=${session}" 2>/dev/null; then
            # Attach the user INTO the live session (the real acting one),
            # never a shadow / second process. Survives pane + auto-update
            # resets because we attach to the SESSION, not a dead pane.
            echo "acting: identity session '${session}' is live — attaching (no second acting process)." >&2
            if [[ -n "${TMUX:-}" ]]; then
                exec tmux switch-client -t "=${session}"
            else
                exec tmux attach-session -t "=${session}"
            fi
        fi
        # No live identity session. Interactive launches may preempt a
        # background holder (marker-based cooperative handoff).
        if [[ "$mode" == "interactive" && -f "${lockfile}.info" ]]; then
            if ( exec {pfd}>"$lockfile"; flock -n "$pfd" ) 2>/dev/null; then
                : # lock free (crashed/exited holder) — just acquire it.
            else
                acting_try_preempt "$lockfile" || true
            fi
        fi
        # Create the identity session, then run the lock+claude loop INSIDE it.
        # The flock fd cannot cross the tmux-server boundary (fds are not
        # inherited by the detached pane), so we can't acquire here and hand
        # the fd in. Instead the pane re-execs THIS script with the hidden
        # --_acting-inner flag: that process re-resolves the same env, acquires
        # the lock, and runs the acting claude — the flock now lives for the
        # lifetime of the pane's process.
        echo "acting: creating identity session '${session}' and acquiring lock." >&2
        tmux new-session -d -s "$session" -n "${ACTING_OWNER:-agent}" -c "$PWD"
        local self="${BASH_SOURCE[0]}"
        tmux send-keys -t "=${session}" \
            "exec '$self' --_acting-inner $(printf '%q' "$lockfile") $(printf '%q' "$mode") $(printf '%q' "$session")" C-m
        if [[ -n "${TMUX:-}" ]]; then
            exec tmux switch-client -t "=${session}"
        else
            exec tmux attach-session -t "=${session}"
        fi
    fi

    # ---- No tmux available (containers / minimal images) ----
    # Try to acquire the lock directly. If free (or a crashed holder left it
    # free), we become the acting session in the foreground. If held, degrade
    # to a passive mirror — never a silent second acting session (task 1.4).
    if ( exec {pfd}>"$lockfile"; flock -n "$pfd" ) 2>/dev/null; then
        echo "acting: no tmux; running acting session in foreground under lock." >&2
        acting_run_inside_lock "$lockfile" "$mode" "$session"
        return
    fi
    if [[ "$mode" == "interactive" ]]; then
        # Interactive with no tmux and a background holder: try the marker
        # handoff, then acquire.
        if acting_try_preempt "$lockfile"; then
            acting_run_inside_lock "$lockfile" "$mode" "$session"
            return
        fi
    fi
    acting_passive_mirror "$lockfile" "$session"
}

# single-acting-session-guard: hidden inner re-entry. When acting_launch
# created the identity tmux session it send-keys'd a re-exec of this script
# with --_acting-inner; that process has re-resolved the env identically and
# now just acquires the lock and runs the acting claude loop. Short-circuit
# BEFORE acting_launch so we never nest another tmux session.
if [[ "$ACTING_INNER" -eq 1 ]]; then
    acting_run_inside_lock "$ACTING_INNER_LOCKFILE" "$ACTING_INNER_MODE" "$ACTING_INNER_SESSION"
    exit 0
fi

case "$SHELL_MODE" in
    bash)
        if ! command -v claude >/dev/null 2>&1; then
            echo "error: 'claude' not on PATH" >&2
            exit 1
        fi
        # single-acting-session-guard (task 1.2): route the bash-mode launch
        # through the identity tmux session (create-or-attach) instead of the
        # old bare `claude -c ... || exec claude ...`. A second launch (SSH,
        # auto-update reset) attaches into the live session or waits for the
        # lock — it can never start a SECOND acting process under the same
        # identity.
        acting_launch "$(acting_lock_path "$ACTING_KEY")" "$ACTING_SESSION" "$ACTING_MODE"
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
