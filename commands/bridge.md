---
name: bridge
description: "Inspect / stop / restart the remote-approval bridge daemon"
model: haiku
effort: low
arguments:
  - name: action
    description: "status | stop | restart (default: status)"
    required: false
  - name: account
    description: "Account name (default: auto-detected from OTAMAN_ACTIVE_ACCOUNT or .otaman marker)"
    required: false
---

# /otaman:bridge

Inspect or control the bridge daemon without leaving Claude. Wraps
`otaman bridge status|stop` and, for a restart after code changes,
the systemd/launchd service-restart command.

## Arguments

- `{{action}}` — `status` (default), `stop`, or `restart`
- `{{account}}` — account name; defaults to the one this session belongs to

## Steps

1. Default `{{action}}` to `status` if empty.

2. Resolve account: use `{{account}}` if provided; otherwise infer from
   `$OTAMAN_ACTIVE_ACCOUNT` or the `.otaman` marker's `expected_account`
   field. If nothing resolves, ask the user.

3. Dispatch:

   - **`status`** — run `otaman bridge status` via Bash. Output shows
     every configured account + whether its daemon is running, the
     port, pid, uptime, and pending approval count.

   - **`stop`** — run `otaman bridge stop --account {account}`. Auto-
     cleans stale endpoint files if the daemon crashed without cleanup.

   - **`restart`** — detect the install method first (check
     `~/.config/systemd/user/otaman-bridge@.service` for systemd,
     `~/Library/LaunchAgents/com.otaman.bridge.{account}.plist` for
     launchd). Then:
       - systemd: `systemctl --user restart otaman-bridge@{account}`
       - launchd: `launchctl unload <plist> && launchctl load <plist>`
       - neither: tell the user the daemon is in foreground mode and
         they need to Ctrl-C + re-run `otaman bridge run` manually.

4. After `stop` or `restart`, re-run `otaman bridge status` and show
   the result so the user sees the new state.

## When to use

- **Before enabling AFK** — confirm the daemon is reachable.
- **After `git pull`** — if code changed, `restart` picks up the new
  version (systemd/launchd services don't auto-reload Python modules).
- **When the phone isn't buzzing** — `status` will show whether the
  daemon is even running and how many approvals are pending.

## Related

- CLI equivalents: `otaman bridge status|stop|run|install|uninstall`.
- Installed as a service? See `references/messenger-config.md` §2.7.
- Toggle AFK: `/otaman:afk on|off|status`.
