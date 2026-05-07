---
name: afk
description: "Toggle or inspect remote-approval AFK mode (routes tool calls to phone)"
model: haiku
effort: low
arguments:
  - name: action
    description: "on | off | status (default: status)"
    required: false
  - name: duration
    description: "Duration for 'on', e.g. 30s, 15m, 8h, 1w, 1h30m (compound). Omit for indefinite."
    required: false
---

# /otaman:afk

Thin wrapper around the `otaman afk` CLI. Toggle AFK mode on/off or check
the current state without leaving Claude Code. When AFK is **on**, the
PreToolUse bridge hook routes Bash / Write / Edit / NotebookEdit calls
to the configured messenger (Telegram) and waits for your phone tap.

## Arguments

- `{{action}}` — `on`, `off`, or `status` (default: `status`)
- `{{duration}}` — only used with `on`; e.g. `8h`, `30m`, `1w`, `1h30m`

## Steps

1. Default action to `status` if `{{action}}` is empty.

2. Run the `otaman afk` CLI via Bash, matching the argument shape:

   - `status` → `otaman afk status`
   - `off` → `otaman afk off`
   - `on` (no duration) → `otaman afk on`
   - `on 8h` → `otaman afk on 8h`

   Pass `{{duration}}` verbatim; the CLI validates it (`30s`/`15m`/`8h`/`2d`/`1w`/compound).

3. If the command exits nonzero, show the stderr message — usually "no
   otaman folder found" (run from inside a managed repo) or "invalid
   duration" (check the grammar).

4. After `on` or `off`, also show `otaman bridge status` so the user can
   verify the daemon is reachable — AFK is useless without a running
   daemon.

## When to use

- **`/otaman:afk status`** — quick check before starting risky work: is
  my daemon running, is AFK on, how much time is left on the TTL?
- **`/otaman:afk on 8h`** — before a long session where you'll be away
  from the keyboard (commute, meeting, overnight run).
- **`/otaman:afk off`** — back at the keyboard, want the native terminal
  prompt back.

## Related

- Underlying CLI: `otaman afk on|off|status` (same behavior, without
  going through Claude).
- Daemon: `otaman bridge run` or (recommended) `otaman bridge install
  --account <name>` to run as a system service.
- SSH sessions auto-enable AFK via `hooks/ssh-auto-afk.sh` unless
  `OTAMAN_AFK_AUTO=0` is set. Check with `/otaman:afk status` — if it
  shows `source: ssh-auto`, the hook did its job.
- Design: `references/remote-approval-design.md` §5.4, live walkthrough:
  `references/t2-live-test.md`.
