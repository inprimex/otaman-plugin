#!/usr/bin/env bash
# SessionStart: team-mode-registers-and-sessions 2.1 (B1) — plugin's reader
# half. Bridge writes <otaman-root>/.otaman/acting-human.json when a
# multi-human tenant's runner-spawned session has a resolved attach-JWT
# human (otaman_bridge.acting_human.write_acting_human); this hook:
#
#   1. Injects the acting-human + their roster roles into the session's
#      context (additionalContext) so the model knows whose behalf it's
#      acting on.
#   2. Exports GIT_AUTHOR_NAME/EMAIL + GIT_COMMITTER_NAME/EMAIL into
#      $CLAUDE_ENV_FILE so every `git commit` made for the rest of the
#      session is attributed to the acting human, not the repo's default
#      git identity — satisfies "commits carry acting-human" without a
#      new prepare-commit-msg hook.
#
# Inert on single-human / CE tenants: the file is simply absent there
# (bridge's own inert gate), so this hook is a silent no-op — SessionStart
# runs once per session, so the one python3 spawn here (JSON parsing) is
# not a hot-path concern the way UserPromptSubmit hooks are.
#
# acting-human.json does NOT carry bus/registry/commit stamping itself —
# that's each consumer's own job reading the same file (bus_server.py's
# otaman_send for bus messages; this hook for git commit identity).
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/_resolve.sh
source "$HOOK_DIR/../scripts/_resolve.sh"

ROOT="$(find_maestro_root 2>/dev/null)" || exit 0
ACTING_FILE="$ROOT/.otaman/acting-human.json"
[[ -f "$ACTING_FILE" ]] || exit 0

PLUGIN_ROOT="$(dirname "$HOOK_DIR")"
PY="$(resolve_otaman_python "$PLUGIN_ROOT" 2>/dev/null)" || exit 0

# One python3 call: parse the file, print four lines (email, name, roles
# csv, context text) so bash can build both outputs without a second
# parse. Any parse failure (malformed JSON) degrades to silent no-op —
# never block session start on a corrupt state file.
PARSED="$("$PY" -c '
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(1)
email = str(data.get("email") or "").strip()
if not email:
    sys.exit(1)
name = str(data.get("name") or "").strip() or email
roles = data.get("roles") or []
roles_csv = ",".join(str(r) for r in roles if str(r).strip())
print(email)
print(name)
print(roles_csv)
' "$ACTING_FILE" 2>/dev/null)" || exit 0

EMAIL="$(printf '%s\n' "$PARSED" | sed -n '1p')"
NAME="$(printf '%s\n' "$PARSED" | sed -n '2p')"
ROLES="$(printf '%s\n' "$PARSED" | sed -n '3p')"

[[ -z "$EMAIL" ]] && exit 0

# 1. Git author/committer attribution for the rest of the session.
if [[ -n "${CLAUDE_ENV_FILE:-}" ]]; then
    {
        printf 'export GIT_AUTHOR_NAME=%q\n' "$NAME"
        printf 'export GIT_AUTHOR_EMAIL=%q\n' "$EMAIL"
        printf 'export GIT_COMMITTER_NAME=%q\n' "$NAME"
        printf 'export GIT_COMMITTER_EMAIL=%q\n' "$EMAIL"
    } >> "$CLAUDE_ENV_FILE"
fi

# 2. Context injection.
CONTEXT="You are operating on behalf of ${NAME} <${EMAIL}> in this multi-human session (team-mode B1)."
if [[ -n "$ROLES" ]]; then
    CONTEXT="${CONTEXT} Roster roles: ${ROLES}."
fi
CONTEXT="${CONTEXT} Commits in this session are attributed to this human; bus messages you send carry acting-human: ${EMAIL}."

# Escape for JSON.
CONTEXT_JSON="$(printf '%s' "$CONTEXT" | sed 's/\\/\\\\/g; s/"/\\"/g')"

printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$CONTEXT_JSON"
exit 0
