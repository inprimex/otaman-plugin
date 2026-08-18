# Connection Resilience for Remote Agents

Why this exists: when you launch Claude Code agents over SSH on an unstable
network, a single dropped connection kills the in-flight session and loses
work. The launcher's per-connection `reliability:` setting wraps each tab
so the agent process keeps running on the server through network blips,
laptop sleep, even client crashes.

## TL;DR

In `launch-settings.yaml`, on each SSH/mesh connection:

```yaml
connections:
  greenbin:
    type: ssh                    # or 'mesh' if you reach the host via VPN
    ssh_default_host: user@srv
    ssh_remote_root: /home/user/greenbin-otaman
    reliability: tmux            # none | tmux | tmux+mosh
```

Run `otaman doctor` to confirm tmux is installed. Done.

## The three reliability modes

| Mode | What it does | Recovery UX | Requirements |
|---|---|---|---|
| **none** | Bare SSH, no wrapping. Current default for back-compat. | Drop = lose the session. Relaunch starts a fresh agent. | Nothing extra. |
| **tmux** ★ recommended | Wraps the inner command in `tmux new -A -s '<name>' bash -lc '<cmd>'` on the remote. The `-A` flag means "create new OR attach to existing" — relaunching the same tab from the launcher reattaches to the in-flight conversation. | Drop = SSH client errors, tab needs relaunch. Relaunch = tmux reattaches; you see your conversation history and the agent picks up where it left off. | `tmux` installed on the remote. |
| **tmux+mosh** | Same tmux wrapping, but the SSH client is replaced with `mosh`. Mosh uses UDP and reconnects automatically on network changes. | Drop = tab pauses with yellow `[disconnected]` indicator, then auto-resumes when the network returns. No relaunch needed. | `tmux` AND `mosh-server` on the remote, plus UDP 60000–61000 reachable from your client. |

## Session naming

Each tab's tmux session is named:

```
otaman-{project}-{repo-name-sanitised}
```

- `{project}` is the `project:` field from `platform.yaml`.
- `{repo-name-sanitised}` strips characters that tmux disallows in session
  names. Dots, colons, and other non-`[A-Za-z0-9_-]` characters become
  underscores. Example: `GreenBin.Resources` => `GreenBin_Resources`.

This is deterministic — relaunching the same tab from the same launcher
always resolves to the same session name, which is how reattach-on-drop
works. Two different projects on the same host don't collide because the
project name namespaces the session.

## Mosh + VPN compatibility

Mosh's auto-reconnect is the best UX, but UDP availability matters. Most
home labs are reached either directly (port-forwarded SSH) or through a
mesh VPN (Tailscale / WireGuard / NetBird). The compatibility matrix:

| Setup | Mosh works? | Why |
|---|---|---|
| **Tailscale** (peer-to-peer or via DERP) | ✅ Yes | Tailscale tunnels everything (UDP + TCP). Mosh's UDP rides inside Tailscale's UDP encapsulation. CGNAT and dynamic IPs are handled by Tailscale's relay layer. Zero firewall config needed. |
| **WireGuard** (direct or via overlay) | ✅ Yes | WireGuard is UDP-based, but it tunnels UDP traffic too. Mosh's UDP packets ride inside the WireGuard tunnel. No extra firewall changes. |
| **NetBird** | ✅ Yes | Built on WireGuard underneath. Same dynamic. |
| **Direct SSH-to-home-lab via DDNS + port-forward** | ⚠️ Friction | Forward UDP 60000–61000 in the home router in addition to TCP 22. Some residential ISPs CGNAT inbound UDP, which makes this flaky. |
| **Mobile hotspot / coffee-shop wifi to port-forwarded server** | ⚠️ Friction | Carrier-grade NAT often kills inbound UDP. The VPN path sidesteps this entirely. |

**Recommendation by situation:**

- You reach your remote via VPN => use `reliability: tmux+mosh`. Auto-reconnect is essentially free.
- You reach your remote via direct port-forward => start with `reliability: tmux`. Add mosh later if you're willing to forward the UDP range.
- You're inside a corporate network with strict firewalls => `reliability: tmux`. Don't fight the firewall for mosh.

## Troubleshooting

### "tmux: command not found" during launch

Install on the remote:

```bash
# Debian/Ubuntu
apt install tmux

# RHEL/Fedora
dnf install tmux

# macOS
brew install tmux
```

### "I can't see my old session" after relaunch

The tmux session name is deterministic, so this usually means:

- Server rebooted (tmux sessions don't survive host restarts — Phase 8's
  conversation-persistence work in `.agents/conversations/` is the long-term
  fix; for now, restart kills sessions).
- The `project:` field in `platform.yaml` changed.
- The repo `name:` changed.
- Someone ran `tmux kill-session` on the remote.

List active sessions on the remote:

```bash
ssh user@host "tmux ls"
```

Find a stuck/orphan session and kill it:

```bash
ssh user@host "tmux kill-session -t otaman-<project>-<repo>"
```

### Mosh handshake failure ("mosh-server: command not found")

`mosh-server` must be installed on the remote (same package as `mosh`):

```bash
apt install mosh
```

### Mosh handshake works but session never reconnects

Check that UDP 60000–61000 is reachable. Common culprits:

- Home router not forwarding UDP (check forwarding rules).
- Cloud provider's security group allows TCP 22 but blocks UDP (add UDP 60000–61000).
- VPN client only routing TCP (very rare; check your VPN's split-tunnel rules).

Diagnostic: from your client, `nc -uvz <host> 60001` should report a usable
state. If it hangs, UDP isn't getting through.

### "agent thinks it's another agent" after relaunch

Unrelated to resilience — see the per-repo identity fix
(commit `f652290`, 2026-04-30). Make sure your otaman install includes
that fix.

## Server-side persistence: what tmux does NOT solve

- **Server reboots / `kill -9` of the tmux server** — sessions die. The
  Phase 8 `.agents/conversations/<session-id>/*.jsonl` work (see
  `references/phase-8-roadmap.md` §4 decision 3) preserves transcripts
  through this kind of failure. Until then, expect to lose state on
  unplanned reboots.
- **Claude Code's own context compaction** — sessions can drop history
  internally even if tmux holds the process up. Same Phase 8 work applies.

For now, treat tmux as the resilience layer for *network* failures. Combine
with regular bus messages, frequent commits, and short focused tasks to
minimise the cost of any other failure mode.

## When NOT to use tmux/mosh

- Local development (no SSH involved). The launcher's `type: local`
  ignores `reliability:` because there's no SSH wrapper to apply.
- Read-only or one-shot remote commands. The wrapping costs nothing
  measurable, but if you genuinely just want `ssh user@host date` and
  exit, set `reliability: none` to keep things simple.

## How the launcher applies this

Reference for what the launcher generates per mode:

```bash
# reliability: none  (current behaviour)
ssh -t user@host "cd /repo && claude /otaman:check"

# reliability: tmux  (current shape — base64 + UX defaults; chained with && so
# Windows Terminal's wt.exe doesn't split on `;` as a tab separator)
ssh -t user@host "tmux set -gq mouse on && tmux set -gq history-limit 50000 && tmux set -gq default-terminal 'tmux-256color' && tmux new -A -s 'otaman-greenbin-greenbin_backend' bash -c 'echo BASE64== | base64 -d | bash -l'"

# reliability: tmux+mosh  (same wrap, mosh client instead of ssh)
mosh user@host -- tmux set -gq mouse on && tmux set -gq history-limit 50000 && tmux set -gq default-terminal 'tmux-256color' && tmux new -A -s 'otaman-greenbin-greenbin_backend' bash -c 'echo BASE64== | base64 -d | bash -l'
```

## Tmux UX defaults applied automatically

The launcher's tmux wrapper sets three options on the remote tmux server before creating the session, so the resilient path Just Works for normal interaction:

| Option | Value | Why |
|---|---|---|
| `mouse` | `on` | Scroll wheel scrolls the scrollback buffer; click-and-drag enters copy mode and selects text. Without this, mouse events drop through to Claude Code which ignores them, so scrolling silently does nothing. |
| `history-limit` | `50000` | Default tmux scrollback is 2000 lines, exhausted in a few seconds of busy Claude output. 50k is generous and costs ~few MB of RAM per session. |
| `default-terminal` | `tmux-256color` | The default `screen` profile clamps to 8 colours, making Claude's TUI render dim. `tmux-256color` enables the full palette. |

Set with `set -gq` (server-wide global, quiet) so the options apply to existing tmux sessions on the host too — and tmux versions that don't recognise an option stay silent. Run once per session creation; idempotent.

**To override** (e.g. you intentionally want mouse mode off): add explicit overrides to your `~/.tmux.conf` on the remote AFTER the launcher's settings take effect. Or edit `Wrap-WithTmux` in `scripts/launch-agents.ps1` if you maintain your own fork. A per-connection opt-out flag (`tmux_mouse: false`) hasn't been added yet — there's no demand for it; ping back if you need it.

## Mouse mode quick reference

When mouse mode is on (the default with otaman's wrap):

| Action | Effect |
|---|---|
| Scroll wheel up | Scroll back through scrollback |
| Scroll wheel down | Scroll forward; reaches bottom -> exit copy mode |
| Click-and-drag | Enter copy mode, select text |
| Click outside selection | Exit copy mode |
| `Ctrl+b [` | Enter copy mode manually (keyboard) |
| Arrow keys / PageUp / PageDown (in copy mode) | Navigate scrollback |
| `q` (in copy mode) | Exit copy mode |
| `Ctrl+Shift+C` (Windows Terminal) | Copy selected text out of tmux into Windows clipboard |

## Future work

Tracked in `references/phase-8-roadmap.md` backlog:

- Auto-detect VPN tunnel and suggest `tmux+mosh` during `otaman doctor` /
  `otaman init` setup wizard.
- Phase 8 `.agents/conversations/<session-id>/*.jsonl` for compaction +
  reboot resilience (orthogonal to network resilience but solves the
  remaining gaps).
- `otaman tmux ls` / `otaman tmux kill <session>` CLI helpers for
  managing remote sessions without ssh-and-grep.
