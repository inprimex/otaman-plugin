#!/usr/bin/env bash
# PreToolUse hook: requires fresh, in-turn confirmation before a Bash call
# matching a curated destructive-command pattern executes — regardless of
# the session's permission-mode configuration, and uniformly for the
# top-level orchestrating session AND any forked/delegated subagent.
#
# Why "uniformly for forks": written instructions ("do not commit") do not
# bind a fork acting on self-discovered work — a fork inherits the parent's
# full context, including many legitimately-modeled autonomous merges
# earlier in the same session. PreToolUse hooks fire on every Bash
# invocation the same way regardless of caller, because hook config is
# repo/session-level, not conversational state (destructive-op-guard D1/D2,
# incident otaman-plugin#24, commit 9258903, 2026-09-01).
#
# Two curated classes (v1 — changes only by spec delta, D5):
#   publish/merge  — ALWAYS confirm (no working-tree check): `gh pr merge`;
#                    `git push` to main/master or with
#                    --force/--force-with-lease; `gh repo delete`;
#                    `git branch -D`/`git push --delete` targeting
#                    main/master, or any remote branch delete (inherently
#                    shared — it exists on origin).
#   working-tree   — confirm ONLY when `git status --porcelain` is
#                    non-empty in cwd (D4 — a clean tree passes silently to
#                    avoid confirmation fatigue): `git reset --hard`,
#                    `git checkout -f`, `git clean -f` (folds in the
#                    deferred 2026-07-02 otaman-runner incident: a
#                    stash-first instruction did not stop this command
#                    class from destroying uncommitted edits).
#
# Local widening (D3/D5): a repo may add extra patterns to
# .claude/destructive-op-patterns.local (one per line, "<class>:<literal
# substring>", class is "merge" or "worktree"; # comments and blank lines
# ignored) — `otaman init --update` never overwrites this file once it
# exists. The baseline list above ships in THIS script and changes only by
# a spec delta to destructive-op-guard, never ad-hoc.
#
# Input: JSON via stdin (PreToolUse protocol) — only Bash reaches this
#        hook (see hooks.json matcher), so tool_input.command is present.
# Output: a match emits
#   {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask",
#    "permissionDecisionReason":"..."},"systemMessage":"..."}
#   naming the matched pattern — "ask" (not "deny") re-prompts for approval
#   in THIS turn regardless of permission mode, the same convention used by
#   hooks/bridge-approval.sh. No match: exit 0, no output (silent allow).
#
# Exit codes:
#   0 — always (allow = no output; ask = JSON on stdout)

set -euo pipefail

INPUT="$(cat)"

json_get() {
    local json="$1" key="$2"
    echo "$json" | sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1
}

TOOL_NAME="$(json_get "$INPUT" "tool_name")"
[[ "$TOOL_NAME" == "Bash" ]] || exit 0

COMMAND="$(json_get "$INPUT" "command")"
[[ -n "$COMMAND" ]] || exit 0

# Emit a PreToolUse "ask" (fresh confirmation required this turn) with the
# reason in BOTH permissionDecisionReason (to the model) and systemMessage
# (to the operator), then exit 0 — matching check-blocked.sh/
# check-ownership.sh's exit-0-not-2 convention (exit 2 discards stdout
# JSON, issue #73).
_ask() {
    local reason="$1"
    local esc
    esc="$(printf '%s' "$reason" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"%s"},"systemMessage":"%s"}\n' "$esc" "$esc"
    exit 0
}

# --- publish/merge class: always confirm, no working-tree check -----------

case "$COMMAND" in
    *"gh pr merge"*)
        _ask "destructive-op-guard: 'gh pr merge' requires fresh confirmation this turn, regardless of permission mode — a forked/delegated session merging a PR it opened on its own initiative is exactly the incident this guard exists to catch (otaman-plugin#24, 2026-09-01). Confirm you intend THIS merge, right now."
        ;;
    *"gh repo delete"*)
        _ask "destructive-op-guard: 'gh repo delete' is irreversible and requires fresh confirmation this turn."
        ;;
esac

if [[ "$COMMAND" == *"git push"* ]]; then
    if echo "$COMMAND" | grep -qE '(^|[[:space:]])(--force|--force-with-lease|-f)([[:space:]]|$)'; then
        _ask "destructive-op-guard: force-push requires fresh confirmation this turn — a history rewrite on a shared branch cannot be undone by the pusher alone."
    fi

    if [[ "$COMMAND" == *"--delete"* ]]; then
        _ask "destructive-op-guard: deleting a remote branch is a shared, hard-to-reverse operation — requires fresh confirmation this turn."
    fi

    # Matches an EXPLICIT main/master mention only (boundary chars exclude
    # /.- so a branch merely containing "main" as a fragment, e.g.
    # feature/main-fix, does not false-positive). v1 deliberately does NOT
    # try to resolve a bare `git push`/`git push origin` (no branch named)
    # against the current checkout — reliably distinguishing "no branch
    # argument at all" from "a real non-main branch argument" from the
    # command string alone is not robust; start narrow (D5), widen via a
    # spec delta if a bare-push-to-main incident is ever observed.
    if echo "$COMMAND" | grep -qE '(^|[^A-Za-z0-9_/.-])(main|master)([^A-Za-z0-9_/.-]|$)'; then
        _ask "destructive-op-guard: pushing to 'main'/'master' requires fresh confirmation this turn."
    fi
fi

if [[ "$COMMAND" == *"git branch -D"* || "$COMMAND" == *"git branch --delete --force"* ]]; then
    if echo "$COMMAND" | grep -qE '(^|[[:space:]])(main|master)([[:space:]]|$)'; then
        _ask "destructive-op-guard: force-deleting 'main'/'master' requires fresh confirmation this turn."
    fi
fi

# --- working-tree-destructive class: confirm only on a dirty tree (D4) ----

case "$COMMAND" in
    *"git reset --hard"*|*"git checkout -f"*|*"git checkout --force"*|*"git clean -f"*|*"git clean --force"*)
        if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
            _ask "destructive-op-guard: the working tree has uncommitted modifications — this command would destroy them irrecoverably. Requires fresh confirmation this turn (the 2026-07-02 otaman-runner incident: a standing stash-first instruction did not stop this same command class from destroying uncommitted edits)."
        fi
        ;;
esac

# --- local widening (D3/D5): extra repo-specific patterns -----------------

LOCAL_PATTERNS=".claude/destructive-op-patterns.local"
if [[ -f "$LOCAL_PATTERNS" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" == \#* ]] && continue
        local_class="${line%%:*}"
        local_pattern="${line#*:}"
        [[ -n "$local_pattern" ]] || continue
        case "$COMMAND" in
            *"$local_pattern"*)
                if [[ "$local_class" == "worktree" ]]; then
                    if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
                        _ask "destructive-op-guard (locally widened, .claude/destructive-op-patterns.local): '${local_pattern}' matched with uncommitted modifications in the working tree — requires fresh confirmation this turn."
                    fi
                else
                    _ask "destructive-op-guard (locally widened, .claude/destructive-op-patterns.local): '${local_pattern}' requires fresh confirmation this turn."
                fi
                ;;
        esac
    done < "$LOCAL_PATTERNS"
fi

exit 0
