#!/usr/bin/env bash
# SessionStart: the specs owner's session applies the tick backlog it alone
# can write (task-complete-reconciler 2.1).
#
# `otaman complete` files a task-complete on the bus, but only the specs
# owner's tasks.md edit survives the next `git pull --ff-only`. Nothing made
# that owner reconcile, so filings accumulated unseen — ~2 weeks of them on
# pmeets, a lens reporting 5/11 against a real 11/11.
#
# D2: this hook is deliberately thin. The engine is `otaman spec sweep`
# (cli 1.2), runnable by hand, from cron, or from here; everything testable
# lives there and in otaman_plugin.specs_drain.
#
# Never blocks a session: the shim always exits 0 and the VERDICT LINE is the
# signal. `not-checked-*` means the drain did not happen, which is not the
# same as nothing being owed — the log says which.
#
# Diagnostics: <otaman-root>/.otaman/session-start-specs-drain.log
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"
# shellcheck source=../scripts/_log.sh
source "$HOOK_DIR/../scripts/_log.sh"

PROJECT_ROOT="$(find_maestro_root 2>/dev/null)" || exit 0
LOG_DIR="$PROJECT_ROOT/.otaman"
LOG_FILE="$LOG_DIR/session-start-specs-drain.log"
mkdir -p "$LOG_DIR" 2>/dev/null || true
rotate_log "$LOG_FILE"

NOW="$(TZ=UTC0 date -u +%Y-%m-%dT%H:%M:%S+00:00)"
_log() { printf '%s  %s\n' "$NOW" "$1" >> "$LOG_FILE" 2>/dev/null || true; }

if [[ "${OTAMAN_SPECS_DRAIN:-1}" == "0" ]]; then
    _log "skipped: OTAMAN_SPECS_DRAIN=0 (kill switch)"
    exit 0
fi

# Resolve an interpreter that can IMPORT otaman_plugin, not merely one that
# exists. This hook used a bare `command -v python3` chain — the same defect
# deploy-agent measured in resolve_otaman_python (20261002T141745), written
# into a hook I added the day before. specs-drain.py degrades to
# `not-checked-no-deps` under an interpreter without the module, so the drain
# would have reported honestly and done nothing on every deployed tenant.
_PY="$(resolve_otaman_python "$HOOK_DIR/.." otaman_plugin 2>/dev/null)" || _PY=""
if [[ -z "$_PY" ]]; then
    _log "not-checked-no-python: no interpreter can import otaman_plugin — drain did not run"
    printf 'otaman: specs tick drain did not run — no interpreter can import otaman_plugin\n' >&2
    exit 0
fi

VERDICT="$(${_PY} "$HOOK_DIR/../scripts/specs-drain.py" 2>&1)" || VERDICT="failed: shim errored"
_log "$VERDICT"

# Surface only what the operator must act on. A skipped non-owner drain is the
# common case and stays in the log; a drain that could NOT run is not.
case "$VERDICT" in
    not-checked-*)
        printf 'otaman: specs tick drain did not run — %s\n' "${VERDICT#*: }" >&2
        ;;
    failed:*)
        printf 'otaman: specs tick drain FAILED — %s\n' "${VERDICT#*: }" >&2
        ;;
    drained:*)
        printf 'otaman: applied the filed tasks.md tick backlog.\n' >&2
        ;;
esac

exit 0
