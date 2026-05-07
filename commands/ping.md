---
name: ping
description: "Proactively notify the user via Telegram — use when you know you need input and can't rely on the Stop-hook heuristic catching it"
model: haiku
effort: low
arguments:
  - name: message
    description: "What to tell the user (why they need to come back to the terminal)"
    required: true
---

# /otaman:ping

Post a Telegram notification to the user's phone immediately. Complements
the automatic Stop-hook notification (which fires when a Claude response
ends with `?` and AFK is on): use **`/otaman:ping`** when you need a
delivery guarantee — the Stop hook's heuristic might miss, or the debounce
might swallow a follow-up question.

## When to use

- **Claude's perspective** — you've finished a long-running operation and
  genuinely need the user to decide what's next (e.g. two viable approaches,
  no default winner). Ending with "?" often works, but if the stakes are
  real, ping.
- **Claude's perspective** — you hit an ambiguity mid-task that you can't
  resolve without human judgment (missing credentials, ambiguous spec,
  etc.). Don't wait for the user to notice Claude stopped.
- **Human's perspective** — "pretend Claude paged me, test the bot
  roundtrip": `/otaman:ping "test"`.

## When NOT to use

- As a turn-end nicety ("done! anything else?"). Use this for genuine
  human-in-the-loop moments.
- To mirror normal chat. `/otaman:ping` is for blocking moments only.
- More than once in ~60 seconds. It's a phone buzz — respect the user.

## Steps

1. Take the user's `{{message}}` (or if invoked by Claude mid-session,
   compose a clear one-line reason in the agent's voice).

2. Run the CLI via Bash:

   ```bash
   otaman ping "{{message}}"
   ```

   Optional flags:

   ```bash
   otaman ping --account riseapps "..."          # override account
   otaman ping --title "Deploy failed" "..."     # custom title
   otaman ping --severity blocking "..."         # red — bypasses mute
   ```

3. The CLI auto-detects the account from `OTAMAN_ACTIVE_ACCOUNT` /
   `CLAUDE_CONFIG_DIR` / `.otaman` marker. Fails loudly if the daemon
   isn't running (unlike the Stop hook, which is silent-safe).

4. Confirm success by printing the CLI's stdout — something like
   `Sent ping to personal (approval, N char body).` The user's phone
   should buzz within a second.

## Severity levels

| Severity | Emoji | Meaning | Mute behavior |
|---|---|---|---|
| `info` | 🟢 | Heads-up, no decision needed | Respects topic mute |
| `approval` (default) | 🟡 | Needs attention, sync response expected | Respects mute |
| `blocking` | 🔴 | Urgent — something is stuck | Bypasses topic mute |

## Related

- CLI equivalent: `otaman ping "message" [--account N] [--severity S]`.
- Automatic surfacing: Stop hook (`hooks/stop-notify.sh`) — no command
  needed when Claude ends with `?`.
- Toggle AFK: `/otaman:afk on|off|status`.
- Daemon lifecycle: `/otaman:bridge status|restart`.
