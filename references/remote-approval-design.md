# Remote Approval & Multi-Account Isolation — Design

Status: **Draft v0** (2026-04-23)
Scope: Two tightly-related problems solved in one architecture.

1. **Remote approval** — route Claude Code's interactive permission prompts to Telegram (and optionally Slack) so the human can unblock agents from a phone.
2. **Multi-account isolation** — generalize the Windows PowerShell `CLAUDE_CONFIG_DIR` pattern to WSL, Linux, and remote hosts, and make it declarative so other devs can adopt it.

These are designed together because the routing rule for approvals depends on which account/project an agent belongs to (corporate vs. personal bot, client-specific Telegram groups, etc.).

---

## 1. Problem statement

Current state:
- Claude Code asks for tool-call permission dozens of times per session. When the human is away from the keyboard, agents sit idle.
- The user already runs **two Claude accounts** on Windows (`claude-personal`, `claude-riseapps`) via PowerShell functions that set `CLAUDE_CONFIG_DIR` before launching. This is un-documented in otaman, hard-coded per user, and has no equivalent on WSL or remote Linux hosts.
- Otaman already orchestrates multiple projects across multiple repos. One Telegram chat for all of them would be unreadable.

Target state:
- When the human is away, any pending permission prompt (Bash, Write, Edit, MCP tool, …) shows up as a Telegram message with `Approve / Reject / Details` buttons, scoped to a per-project topic in a per-account group. Tapping Approve unblocks the agent.
- A single declarative config (`launch-settings.yaml`) describes the user's accounts, which shells they're available in, and how each maps to a Telegram bot and group. The launcher uses it to set `CLAUDE_CONFIG_DIR` and spawn the right shells; the bridge daemon uses the same file to route messages.
- Works on Windows (PowerShell), WSL (bash), and remote Linux servers (SSH) without per-platform code forks.

---

## 2. Non-goals (v1)

- Replacing Claude Code with a custom CLI or IDE fork. We extend via the officially supported hook + settings surface.
- Building a hosted service. The bridge daemon runs locally next to Claude Code; no external hosting required.
- Supporting messengers beyond Telegram in v1. Slack/Discord/Matrix drop in via a pluggable transport layer (see §10).
- Routing Claude Code's streaming assistant output to Telegram. The bridge handles **approvals and agent bus messages**, not full chat mirroring.

---

## 3. Architecture at a glance

```
┌──────────────────────────────────────────────────────────────────┐
│                      Telegram client (phone)                      │
│                                                                   │
│  Group: "Otaman · Personal"      Group: "Otaman · Riseapps"     │
│   └ topic: otaman-plugin          └ topic: client-a-platform     │
│   └ topic: revlet                  └ topic: client-b-platform     │
│   └ topic: _approvals_inbox        └ topic: _approvals_inbox      │
└──────────┬─────────────────────────────────────┬─────────────────┘
           │ long-polling                         │ long-polling
           ▼                                      ▼
┌──────────────────────┐                 ┌──────────────────────┐
│  otaman-bridge      │                 │  otaman-bridge      │
│  daemon (personal)   │                 │  daemon (riseapps)   │
│  bot: @your_p_bot    │                 │  bot: @your_c_bot    │
│  listens on          │                 │  listens on          │
│  unix:/run/.../p.sock│                 │  unix:/run/.../c.sock│
└──────────┬───────────┘                 └──────────┬───────────┘
           │ local IPC (unix socket / named pipe)   │
           ▼                                        ▼
┌──────────────────────────────────────────────────────────────────┐
│              PreToolUse hooks across Claude sessions              │
│                                                                   │
│  session A:  CLAUDE_CONFIG_DIR=~/.claude-personal                 │
│              project=otaman-plugin   → personal daemon           │
│                                                                   │
│  session B:  CLAUDE_CONFIG_DIR=~/.claude-riseapps                 │
│              project=client-a-platform → riseapps daemon          │
│                                                                   │
│  session C:  CLAUDE_CONFIG_DIR=~/.claude-personal                 │
│              project=revlet           → personal daemon           │
└──────────────────────────────────────────────────────────────────┘
```

Three layers, each independently testable:

1. **Hook layer** — a `PreToolUse` hook installed per session. Reads a per-session config to know which daemon socket to talk to. Blocks waiting for an allow/deny reply, with a configurable timeout.
2. **Daemon layer** — one long-running process per account. Owns a Telegram bot via long-polling. Exposes a local IPC endpoint (unix socket on Linux/macOS/WSL, named pipe on Windows). Maps incoming hook requests to Telegram messages in the right topic.
3. **Config layer** — `launch-settings.yaml` declares accounts + Telegram bindings. The launcher consumes it to set `CLAUDE_CONFIG_DIR` and start shells. The daemons consume the same file to know which bot/group they own.

---

## 4. Part A — Multi-account isolation (cross-platform)

### 4.1 The principle

Every Claude Code session reads auth, history, and settings from `$CLAUDE_CONFIG_DIR` (or `~/.claude` if unset). So account isolation is fully solved by **setting one env var before launching `claude`**. The existing Windows PowerShell pattern does this manually; we generalize it.

### 4.2 Declarative account config

New block in `launch-settings.yaml` (the same file the launcher already uses for connections):

```yaml
# launch-settings.yaml
accounts:
  personal:
    config_dir: "~/.claude-personal"          # expanded per-shell (see 4.3)
    label: "Personal (max)"
    telegram:
      group_id: -1001111111111
      bot_token_env: OTAMAN_TG_BOT_PERSONAL  # read from env, never stored in YAML
      # optional per-account bridge socket, defaults to ~/.otaman/bridge-{account}.sock
      bridge_socket: ~/.otaman/bridge-personal.sock

  riseapps:
    config_dir: "~/.claude-riseapps"
    label: "Riseapps (corp)"
    telegram:
      group_id: -1002222222222
      bot_token_env: OTAMAN_TG_BOT_RISEAPPS
      bridge_socket: ~/.otaman/bridge-riseapps.sock

# Existing fields continue to work
active_connection: lan
connections:
  local:
    type: local
    local_root: "C:/work/Personal/otaman-plugin"
    local_shell: wsl
    account: personal          # NEW — which account this connection uses
  lan:
    type: ssh
    ssh_client: ssh
    ssh_default_host: user@1.2.3.4
    ssh_key: ~/.ssh/id_ed25519
    ssh_remote_root: /home/user/client-a/client-a-otaman
    account: riseapps          # NEW
```

Key rules:
- **Secrets never go in YAML**. Only the *name* of an env var holding the bot token. The env var itself is populated from one of the sources in §4.7.
- **One account = one Telegram group = one daemon = one bot**. Clean blast radius — a leaked corporate bot token can't post to a personal group.
- **`config_dir` is the same string everywhere**; the resolver expands `~` per shell.

### 4.3 Cross-platform path expansion

The `config_dir` value `~/.claude-personal` is normalized differently depending on where the shell is running. Add a small helper to `scripts/_resolve.py`:

| Shell / platform | Resolved path |
|---|---|
| PowerShell (Windows) | `C:\Users\<you>\.claude-personal` |
| WSL (Ubuntu under Windows) | `/home/<wsl-user>/.claude-personal` (WSL has its own `$HOME`, *not* shared with Windows by default — this is a **feature**, because WSL can keep its own auth) |
| macOS / Linux local | `$HOME/.claude-personal` |
| SSH remote | `$HOME/.claude-personal` on the remote box, resolved at launch time from `ssh_remote_root` / user shell |

Important: on a Windows host, the PowerShell `~/.claude-personal` and WSL's `~/.claude-personal` **are different directories**. That's fine — they are different environments. The user can either:

- **Auth each environment independently** (recommended — each gets its own credentials, cleanest isolation), or
- **Opt-in symlink** WSL `~/.claude-personal` → `/mnt/c/Users/<you>/.claude-personal` if they want shared auth. Document this but default to independent.

### 4.4 Launcher integration

`launch-agents.ps1` (and the bash equivalent we'll add as `launch-agents.sh`) currently sets `local_shell` per connection. Extended behavior:

1. Resolve `connections.<active>.account` → `accounts.<name>`.
2. Expand `config_dir` for the target shell.
3. Set `CLAUDE_CONFIG_DIR` in the spawned terminal *before* running `claude`.

For Windows Terminal tabs:

```powershell
# Before (today)
wsl.exe -d Ubuntu -- bash -ic "cd '$wslPath' && claude /otaman:check"

# After
wsl.exe -d Ubuntu -- bash -ic "cd '$wslPath' && CLAUDE_CONFIG_DIR='$configDir' claude /otaman:check"
```

For SSH:

```bash
# Before
ssh -t user@host "cd /path && source ~/.nvm/nvm.sh && claude /otaman:check"

# After
ssh -t user@host "cd /path && source ~/.nvm/nvm.sh && CLAUDE_CONFIG_DIR=~/.claude-personal claude /otaman:check"
```

This replaces the ad-hoc PowerShell `claude-personal` / `claude-riseapps` functions with one declarative file. Other devs run `otaman launcher setup`, fill in their accounts once, and get the same isolation.

### 4.5 Shell profile helpers (optional)

For users who *also* want bare shell aliases outside the launcher:

```
otaman accounts install-shell-aliases
```

Reads `launch-settings.yaml` `accounts:` and emits:
- PowerShell: functions `claude-personal`, `claude-riseapps` appended to `$PROFILE`
- bash/zsh: functions appended to `~/.bashrc` / `~/.zshrc`
- fish: appended to `~/.config/fish/config.fish`

This is idempotent (bracketed with `# BEGIN MAESTRO ACCOUNTS` / `# END MAESTRO ACCOUNTS`) so re-running updates, not appends.

### 4.6 Account-aware `.otaman` marker

Today the `.otaman` marker file in each managed repo points to the otaman folder. Extend it to record the expected account so the hook can sanity-check:

```yaml
# .otaman (in each managed repo, gitignored)
otaman_root: ../client-a-otaman
expected_account: riseapps
```

If a session opens with `CLAUDE_CONFIG_DIR=~/.claude-personal` but the `.otaman` file says `expected_account: riseapps`, the SessionStart hook warns. Prevents the "I'm using the wrong account on a client repo" footgun that comes with running multiple accounts.

### 4.7 Secrets — tiered source abstraction

Secrets (Telegram bot tokens in T2, PATs in backlog items, future API keys) never belong in git. YAML only references secrets by *name*; an abstraction resolves the name to a value through one of several sources, in priority order:

1. **Process env** (`source: env`) — if the variable is already set in the shell, use it. Highest priority, no file read.
2. **`.otaman/secrets.env`** (`source: dotenv`) — simple `KEY=value` file inside the otaman folder, **forcibly gitignored** by `/otaman:init` / `/otaman:scan`. Default source for local dev. Loaded by both launchers before spawning `claude`.
3. **OS keychain** (`source: keyring`) — Windows Credential Manager / macOS Keychain / libsecret on Linux. Recommended for anything beyond a solo laptop. `otaman accounts add` offers to store there when available.
4. **External KMS / Vault** (`source: vault | aws-sm | gcp-sm | azure-kv`) — future, for teams. Plugs into the same interface, pulls at launcher-start time.

YAML shape:

```yaml
accounts:
  personal:
    telegram:
      # Short form (backwards compat, defaults to env)
      bot_token_env: OTAMAN_TG_BOT_PERSONAL

      # Long form — explicit source chain
      bot_token:
        sources:
          - { type: env,     name: OTAMAN_TG_BOT_PERSONAL }
          - { type: dotenv,  name: OTAMAN_TG_BOT_PERSONAL }
          - { type: keyring, service: otaman, account: tg-personal }
          # - { type: vault, path: secret/otaman/tg-personal, field: token }
```

The launcher (and later the daemon) walks the chain; first non-empty value wins. If the chain exhausts, fail fast with a clear error naming every source tried.

**`.otaman/secrets.env` contract:**
- Lives at the otaman-folder root, **never** in a managed repo.
- Mode `0600` on Linux/macOS; Windows ACL'd to the user's SID.
- `/otaman:init` and `/otaman:scan` both (a) create `.gitignore` entries for `.otaman/secrets.env` *and* the file itself, (b) emit a starter `.otaman/secrets.env.example` with all expected keys and empty values, committed to git.
- Loaded by launchers **before** spawning `claude`, so sessions see tokens in their process env without the file ever leaving the otaman folder.
- The `otaman doctor` command flags any `secrets.env` that slipped into git history (grep-based check), emits remediation.

**Secret-source Protocol** (lives in `scripts/_secrets.py`, usable from any script or daemon):

```python
class SecretSource(Protocol):
    def resolve(self, ref: SecretRef) -> str | None: ...

# Built-ins: EnvSource, DotenvSource, KeyringSource
# Post-v1:   VaultSource, AwsSecretsManagerSource, GcpSecretManagerSource, AzureKeyVaultSource
```

New KMS integrations plug in as a module drop, same pattern as the messenger Transport abstraction (§10). Config is a registry: adding `aws-sm` means shipping `scripts/secret_sources/aws_sm.py` and registering the `type: aws-sm` handler.

**Why layered instead of one-size-fits-all:** solo developers want zero-ceremony (`.env` is fine). Small teams want keychain. Enterprises mandate Vault/KMS. Forcing any one option alienates at least two of the three groups. The abstraction means the user changes one YAML line to upgrade security posture — not the bridge code.

---

## 5. Part B — Telegram bridge

### 5.1 Topology

- **One Telegram supergroup per account.** (Not per project — we'd hit the 100-topics-per-group cap, and managing groups scales worse than topics.)
- **One forum topic per project** (= per `platform.yaml`). Auto-created by `otaman bridge init` via Telegram's `createForumTopic` API.
- **One extra topic per group** called `_approvals_inbox` — catch-all for approvals that arrive before the bridge has auto-classified the project (rare, but defensive).
- **Per-message tags**: agent name, severity emoji, repo slug. Keeps the topic readable when multiple agents post.

Why forum topics (not threads / reply chains): Telegram's topics have their own unread counters, mute state, and pin, which means the human can mute `cto-reviewer` chatter project-wide without losing sight of blocking approvals from owner agents. This is the biggest productivity win vs. single-chat or single-topic.

### 5.2 Message schema (Telegram → human)

```
🟡 [client-a-platform] auth-service · backend-agent
Tool: Bash
Command: npm install jsonwebtoken@9.0.2
Working dir: /home/user/client-a/auth-service
Reason: installing dependency for JWT signing (spec §3.2)

[Approve]  [Reject]  [Details]  [Snooze 15m]
```

Inline keyboard callback data encodes `{account, project, request_id, action}` so a tap routes back to the right daemon → right hook → right Claude session.

Severity rules:
- 🟢 info — non-blocking notifications (agent finished task, spec updated). No buttons.
- 🟡 approval — tool call pending. `Approve / Reject / Details / Snooze`.
- 🔴 blocking — `priority: urgent` bus message or approval pending >5 min. Bypasses topic's silent-mode setting.

"Details" expands the full tool payload (diff for Edit/Write, full command for Bash). Two-step disclosure so the phone notification stays short but the decision is informed.

### 5.3 Hook → daemon protocol

Local IPC over **HTTP on `127.0.0.1`**, same on every platform. Each daemon binds an ephemeral port in `49152–65535` and writes `{port, token}` to `~/.otaman/bridge-<account>.endpoint` (file mode `0600`). Callers read the endpoint file, send requests to `http://127.0.0.1:<port>`, and authenticate with `Authorization: Bearer <token>`. Requests without the token are rejected with 401.

Why loopback HTTP instead of unix sockets + named pipes:
- **One implementation across Windows, Linux, macOS, WSL** — no platform branches.
- **Trivially debuggable** with `curl`, Postman, browser devtools.
- **Reusable substrate** — a future local UI (desktop app, VS Code panel, browser extension) can talk to the same daemon with zero protocol work. This is why we pick HTTP over unix sockets even on Linux, where unix sockets would be slightly simpler.
- **No OS-specific permission model to reason about** — bearer token in a 0600 file is uniform and explicit.

Threat model notes: anything running as the same OS user can read the endpoint file and impersonate the hook. That's acceptable — same trust boundary as unix socket `0600`. Anything running as a *different* local user cannot read the endpoint file, so it cannot connect. The bind is `127.0.0.1` (not `0.0.0.0`), so no network exposure. Tokens rotate on daemon restart; endpoint file is unlinked on clean shutdown.

**Hook request → daemon:**

**Hook request → daemon:**
```json
POST /approval
{
  "request_id": "20260423T153000-a7f2",
  "account": "riseapps",
  "project": "client-a-platform",
  "repo": "auth-service",
  "agent": "backend-agent",
  "tool_name": "Bash",
  "tool_input": { "command": "npm install jsonwebtoken@9.0.2" },
  "reason": "installing dependency for JWT signing",
  "priority": "normal",
  "timeout_seconds": 540
}
```

**Daemon response (after human taps):**
```json
{
  "decision": "allow",      // allow | deny | ask | timeout
  "updated_input": null,    // optional: modified tool_input (e.g., human edited the command)
  "message": null,          // optional: note passed back to Claude on deny
  "responder": "telegram:@roman"
}
```

**Audit**: every request+response is appended to `.agents/approvals.jsonl` for compliance (HIPAA/ISO audit trail, matches otaman's existing compliance story).

### 5.4 Hook behavior — the AFK toggle

Two modes, controlled by the `.otaman/afk` flag file:

- **AFK on**: hook makes the IPC call, blocks until the daemon replies or the hook timeout fires. Returns `allow`/`deny` based on the reply. If the daemon is unreachable (not running), falls back to `ask` so the normal terminal prompt still works — fail-safe, never harder-to-use than stock Claude Code.
- **AFK off (default on local sessions)**: hook returns `ask` immediately so Claude Code's native terminal prompt shows. Daemon receives a **fire-and-forget notification only** ("FYI, a tool call is pending here"), with no buttons — useful if you want your phone to ping but you'll answer at the terminal.

#### Flag file format

`.otaman/afk` is a tiny YAML file (not empty marker), so we can carry TTL and provenance:

```yaml
# .otaman/afk
enabled_at: 2026-04-23T19:30:00Z
expires_at: 2026-04-24T03:30:00Z    # omit = indefinite
source: manual                        # manual | ssh-auto | idle-auto
enabled_by: roman                     # user name for audit
```

The hook reads the file and compares `expires_at` to now. If expired, it treats AFK as off AND removes the file lazily. No background timer needed — this survives restarts, sleep/wake, and SSH reconnects cleanly.

#### CLI

```bash
# Indefinite
otaman afk on

# With duration (accepts 30s / 15m / 8h / 2d / 1w)
otaman afk on 8h
otaman afk on 30m
otaman afk on 1d

# Off
otaman afk off

# Status shows source + remaining TTL
otaman afk status
# AFK: on  (source: manual, 7h 23m remaining)
```

Duration parser lives in a shared helper so the same grammar works in `otaman afk on`, `otaman bridge ... --timeout`, and future scheduled commands. Accepts compound forms too: `1h30m`, `2d4h`.

#### Auto-enable rules

The SessionStart hook decides whether to flip AFK on automatically:

| Trigger | Default | Rationale |
|---|---|---|
| `$SSH_CONNECTION` or `$SSH_TTY` set | **AFK on, source=ssh-auto, no expiry** | Remote sessions almost always mean the human isn't at the same box as Claude. Turn on by default; the user can `otaman afk off` if they're actively SSH'd from the next room. |
| `$WSL_DISTRO_NAME` set and no `SSH_CONNECTION` | off | WSL-on-laptop is "local"; the terminal is right there. |
| Interactive local terminal | off | Default. |
| Detached / nohup / no TTY | **on, source=ssh-auto** | Treated same as SSH: no human nearby. |

Users can opt out globally by setting `accounts.<name>.afk.auto_on_ssh: false` in `launch-settings.yaml`, or per-session via an env var `OTAMAN_AFK_AUTO=0` passed by the launcher for specific connections. The launcher could even make this a per-connection field (`connections.lan.afk_auto: false`) if a specific remote host is always manned.

When the hook auto-enables, it writes `source: ssh-auto` so `otaman afk status` makes clear *why* it's on — no confusion when the user wonders why their approvals are going to Telegram. Auto-enabled AFK is never given a TTL; it clears on session end via the SessionEnd hook.

Future polish (out of scope for v1): idle-auto mode — flip AFK on after N minutes of no terminal input on local sessions. Needs a separate watchdog process; deferred until v1 data shows it's actually useful.

### 5.5 Timeouts & fail modes

| Situation | Behavior |
|---|---|
| Daemon reachable, human replies in time | Use reply (allow/deny). |
| Daemon reachable, no reply within `timeout_seconds` | Hook returns `ask` (so user can answer at terminal if they come back). Telegram message edited to "⏱️ expired". |
| Daemon unreachable | Hook logs warning, returns `ask`. Never blocks Claude Code if the bridge is broken. |
| Hook killed mid-wait | Daemon cleans up pending request on next heartbeat. Telegram message edited to "🚫 aborted". |

The `timeout_seconds` defaults to Claude Code's hook timeout minus 30s buffer (so the hook can always return cleanly before Claude kills it). Configurable per-account.

### 5.6 Agent bus message surfacing

The daemon has a second responsibility beyond tool-call approvals: it drains `.agents/bus/active/` for messages that need human attention and surfaces them to Telegram. This is what turns the bridge from "remote tool-call approver" into "remote otaman cockpit."

#### Which messages surface

Defined by a default policy table, overridable per-account in `launch-settings.yaml`:

| Message type | Surface? | Severity | Interactive? |
|---|---|---|---|
| `spec-change-request` | **always** | 🟡 approval | `Approve` / `Reject` / `View diff` / `Comment` |
| `priority: urgent` (any type) | **always** | 🔴 blocking | context-dependent |
| `priority: high` (any type) | **always** | 🟡 approval | if addressed to human, buttons; else info |
| `to: human` (any type) | always | 🟡 | `Acknowledge` + free-text reply |
| `question` addressed to human | always | 🟡 | free-text reply (becomes `answer` bus message) |
| `review-request` | configurable | 🟢 info | link to review file |
| `task-complete` | configurable | 🟢 info (silent) | none |
| `spec-change-approved` / `-rejected` | configurable | 🟢 info | none |
| `task-assignment` (agent→agent) | **no** | — | — |
| `info` broadcasts | **no** | — | — |

Rationale: anything that needs a human decision surfaces by default; anything agent-to-agent stays in the file bus. The `configurable` rows default off (reduce noise) but can be enabled per-account.

```yaml
# launch-settings.yaml excerpt
accounts:
  personal:
    telegram:
      group_id: -1001111111111
      surface:
        review_request: true    # want CTO reviews on my phone
        task_complete: false    # too noisy
        spec_change_outcome: true
```

#### How buttons map to bus writes

When the human taps Approve on a `spec-change-request` message, the daemon:
1. Writes a new `spec-change-approved` message into `.agents/bus/active/` as `from: human, to: all`.
2. Writes an ack file `{orig-msg-stem}.human.ack` containing `resolved`.
3. Triggers the existing `/otaman:approve` logic that invokes `openspec` CLI, same as if the human had run it locally.
4. Edits the Telegram message to show `✓ approved 19:42 by Roman`.

When the human Comments or free-text replies to a question, the daemon writes the answer as a bus message (`type: info, to: <asker>`) and acks the original. Normal bus flow picks it up.

Net effect: the existing bus + `/otaman:approve` machinery keeps working locally *unchanged*. Telegram just becomes a second front-end on top of the same state. Auditability is preserved — every Telegram-originated decision becomes a real bus message with a real ack file.

#### File watching

- **Linux/WSL/macOS**: `inotify` / `fsevents` via `watchdog` library. Zero-poll, instant latency.
- **Windows**: `FileSystemWatcher` equivalent via `watchdog`.
- **Fallback**: 2-second polling if filesystem events aren't reliable (network mounts, some WSL configs).

Debouncing: 500ms after a write event to let `{msg-stem}.tmp` rename-dance settle before reading.

### 5.7 Daemon lifecycle

One daemon per account. Options for keeping it alive:

- **Linux/WSL**: `systemd --user` service (`otaman-bridge@personal.service`). `otaman bridge install --service` writes the unit file.
- **macOS**: launchd agent.
- **Windows (PowerShell host)**: NSSM service or Task Scheduler on-login trigger. `otaman bridge install --service` handles both.
- **Ad-hoc**: `otaman bridge run --account personal` for dev/testing.

Daemons auto-restart on crash. A single `otaman bridge status` command shows health of all configured daemons.

---

## 6. Part C — Multi-host & future relay

Today's design assumes **one host runs the daemons** and other hosts route to it. Three shapes, in order of complexity:

### 6.1 Single-host (v1 — ship this first)

All Claude Code sessions and the daemon live on the same box (laptop, dev VM, or single remote server). Trivial; just unix sockets. Solves 80% of the problem.

### 6.2 Multi-host via Tailscale + HTTP (v1.5)

When the user has Claude Code on the laptop **and** on a remote dev server, each host runs its own daemon. Both use Telegram's long-polling (outbound only — no inbound config). Messages get a `host:` tag so the human can tell which box is asking.

Only concern: Telegram's single-poller rule means you can't share a bot token across two daemons. Solutions:
- **Two bots per account** (simple; ugly usernames like `@personal_laptop_bot`, `@personal_srv_bot`).
- **Central relay** — see next.

### 6.3 Central relay (v2 — when >1 host per account)

A single small process owns the bot for each account and exposes an HTTP API that per-host daemons call. Relay can run:
- On the user's always-on home server
- On a free Fly.io / Oracle Always Free VM
- On one of the dev servers, reached via Tailscale by the others

Architecture:

```
[Telegram] ← long-poll → [relay, one bot per account]
                              ↕ HTTP (over Tailscale / LAN)
     ┌────────────┬─────────┴────────┬────────────┐
  [laptop]    [dev-server-1]     [dev-server-2]   [...]
   daemon       daemon              daemon
```

Same JSON contract as the single-host daemon, just over TCP instead of unix socket. Zero changes to the hook layer.

Do **not** build this in v1. Ship v1, confirm the primitive works, then add the relay when a real user needs multi-host.

---

## 7. Config schema — full additions

Consolidated for review. All new fields are optional; omitting them = feature off.

```yaml
# launch-settings.yaml — additions

accounts:
  <name>:
    config_dir: "~/.claude-<name>"         # required
    label: "Human-readable label"          # optional (for menus)
    telegram:                              # optional; omit = no bridge for this account
      group_id: -1001234567890             # required if telegram: present
      bot_token_env: OTAMAN_TG_BOT_<NAME> # required; env var name (not the token itself)
      bridge_socket: ~/.otaman/...        # optional; default derived from account name
      topic_map:                           # optional; explicit project→topic_id pinning
        <project-name>: 42
    defaults:                              # optional; inherited by connections using this account
      wsl_distro: Ubuntu
      ssh_key: ~/.ssh/id_ed25519

connections:
  <name>:
    account: <account-name>                # optional; inherits CLAUDE_CONFIG_DIR from account
    # ... all existing fields unchanged
```

```yaml
# platform.yaml — one addition (per-project override)

telegram:                                  # optional; omit = use account default
  topic_id: auto                           # auto | <int> | <string> (topic name, resolved on init)
  mute_levels: [info]                      # severities to send silently
  broadcast_agents: [cto-reviewer]         # agents whose messages go to a shared "reviews" topic
```

```
# .otaman (per-repo marker)
otaman_root: ../client-a-otaman
expected_account: riseapps
```

---

## 8. Setup flow

### 8.1 First-time user (new account)

```bash
otaman accounts add personal
# ? Config dir path [~/.claude-personal]:
# ? Label [Personal]:
# ? Set up Telegram bridge now? [Y/n]:
# → Opens BotFather link, waits for bot token
# ? Paste bot token:
# → Stores token in OS keychain under OTAMAN_TG_BOT_PERSONAL
# ? Telegram group ID (or create new?):
# → Creates group via bot, enables forum topics, pins bot
# ✓ Account 'personal' configured
```

One command, maybe three minutes end-to-end.

### 8.2 Adding a project

On `otaman init` or `otaman scan`, if the active connection's account has a Telegram binding:

```bash
# Auto-runs during init
otaman bridge link-project
# → Creates forum topic "auth-platform" in the account's group
# → Writes topic_id to platform.yaml telegram.topic_id
```

### 8.3 Installing hooks in sessions

`otaman init` already writes per-repo CLAUDE.md + hooks. Extend to install the PreToolUse bridge hook. Hook config lives in the otaman folder's `.claude/settings.json`, not per-repo, so it's one place.

### 8.4 Running daemons

```bash
# Foreground (dev)
otaman bridge run --account personal

# Install as service
otaman bridge install --account personal    # auto-detects systemd / launchd / NSSM
otaman bridge install --all                 # install services for every configured account

# Status
otaman bridge status
# personal    running  pid=12345  bot=@your_p_bot  pending=0
# riseapps    running  pid=12346  bot=@your_c_bot  pending=2 (oldest: 3m ago)
```

---

## 9. Security considerations

1. **Bot tokens / any secret**: never in YAML or git. Resolved through the tiered source chain in §4.7 (`env` → `.otaman/secrets.env` → OS keychain → KMS/Vault). `otaman accounts add` prompts once for each secret and writes it to the highest-available tier (keychain if present, else dotenv). `/otaman:init` and `/otaman:scan` both enforce gitignore of `.otaman/secrets.env` and commit a `.example` stub. `otaman doctor` grep-checks git history for leaked secrets.
2. **Telegram user allowlist**: bridge rejects replies from any user ID not in `accounts.<name>.telegram.allowed_user_ids`. A leaked bot token ≠ remote code execution: the bot can send messages but buttons tapped by strangers are ignored.
3. **Request ID opaqueness**: callback data uses random IDs, not incrementing counters. Prevents guessing approval callbacks for other requests.
4. **IPC auth**: daemon binds `127.0.0.1:<ephemeral>` and writes `{port, token}` to `~/.otaman/bridge-<account>.endpoint` with mode `0600` (Windows: ACL'd to user's SID). Every hook request carries `Authorization: Bearer <token>`; unauthenticated requests get 401. Same-user processes can impersonate — acceptable, matches the unix-socket threat model. Token rotates on daemon restart. Loopback bind means no network exposure. A future local UI reuses the same auth envelope.
5. **Audit log**: every approval decision (allow/deny/timeout) appended to `.agents/approvals.jsonl` with timestamp, user ID, request payload. Part of otaman's existing compliance-report.py output.
6. **Corporate/personal bleed**: physically separate bots + groups per account. Even if the user accidentally sets the wrong `CLAUDE_CONFIG_DIR`, the `expected_account` check in `.otaman` marker fires a SessionStart warning before any work happens.

---

## 10. Extensibility — messenger abstraction (load-bearing)

This is not an "add other transports later" note — it's an **architectural contract for v1**. The outsource-company context means different clients will mandate different messengers (Slack for corp, Matrix for compliance-sensitive, Discord for gaming/indie). Retrofitting the abstraction after shipping a Telegram-flavored daemon is expensive; preserving it from day one is cheap.

### 10.1 The contract

Everything north of the transport module must be transport-agnostic:

- **Hook → daemon IPC payload** carries domain concepts (`ApprovalRequest`, `BusMessageSurface`, `InfoNotice`) — never Telegram message markup, chat IDs, or inline-button JSON.
- **Config schema** uses `accounts.<name>.transport: telegram | slack | discord | matrix` + a `transport_config:` sub-block for per-transport keys. `telegram:` at the account level is kept as backwards-compat sugar for `transport: telegram` + `transport_config: { ... }`.
- **Bus surfacing policy** (§5.6) expresses actions as abstract verbs (`approve`, `reject`, `comment`, `view-diff`, `snooze`). Each transport maps them to its native UI (Telegram inline buttons → Slack block-kit actions → Discord components → Matrix reactions + threads).
- **Audit log** (`.agents/approvals.jsonl`) stores `transport: <name>` and `responder: <transport>:<user-id>` so the origin is clear but the log itself is transport-neutral.

### 10.2 Transport Protocol

```python
class Transport(Protocol):
    name: str  # "telegram" | "slack" | ...

    async def send_approval(self, req: ApprovalRequest) -> TransportHandle: ...
    async def send_info(self, msg: InfoMessage) -> TransportHandle: ...
    async def update(self, handle: TransportHandle, status: str) -> None: ...
    async def listen(self) -> AsyncIterator[InboundReply]: ...
    async def allowlist_check(self, user_id: str) -> bool: ...
```

`ApprovalRequest`, `InfoMessage`, `InboundReply`, and `TransportHandle` live in `bridge/core.py` and import nothing transport-specific. Telegram-specific types live in `bridge/transports/telegram.py` and are never referenced elsewhere.

### 10.3 v1 implementation commitment

- `TelegramTransport` — the only production transport in v1.
- `NullTransport` — ships alongside in v1, lives under `bridge/transports/null.py`, logs instead of sending. Used by tests and as a ratchet: **if `NullTransport` can't satisfy a feature, the abstraction is leaking** and the PR is rejected until the offending code moves into a transport module.

### 10.4 Planned transports (post-v1)

- `SlackTransport` (Phase T5) — Socket Mode, block-kit Approve/Reject actions, threads for per-project scoping.
- `DiscordTransport` — components v2, thread per project, forum channel per account mirrors the Telegram supergroup model.
- `MatrixTransport` — rooms per project, reactions as quick actions, threads for long context; attractive for self-hosted / HIPAA-sensitive clients.
- Generic `WebhookTransport` fallback — posts JSON to an arbitrary URL, for ad-hoc integrations (Teams, Mattermost, custom internal tools) where a full native transport is overkill.

### 10.5 Enforcement

A lint check in CI (`scripts/check_transport_boundary.py`) fails the build if any file outside `bridge/transports/` imports a transport-specific symbol or library (`telegram`, `slack_sdk`, `discord.py`, `matrix-nio`). Cheap to write, high leverage against accidental coupling.

---

## 11. Rollout phases

**Phase T1 — Account isolation (no Telegram) — ~3 days**
- Extend `launch-settings.yaml` schema (`accounts:` block + per-connection `account:`).
- Extend `launch-agents.ps1` with account resolution + `CLAUDE_CONFIG_DIR` export.
- New `scripts/launch-agents.sh` — parity bash launcher for Linux/macOS devs.
- `.env` + secret-source abstraction (§4.7): `scripts/_secrets.py` with `env`/`dotenv`/`keyring` sources, gitignore enforcement for `.otaman/secrets.env`, `.example` stub emission.
- `otaman accounts add|list|remove|install-shell-aliases` CLI.
- Update `.otaman` marker with `expected_account`.
- SessionStart hook: warn on `CLAUDE_CONFIG_DIR` ↔ `expected_account` mismatch.
- `otaman doctor` grep-check for leaked secrets in git history.
- Docs: migration guide for existing PS `claude-personal` / `claude-riseapps` users.

Ship-ready milestone: same multi-account workflow, now declarative and cross-platform on both Windows and Linux/macOS. Secrets infra ready for T2's tokens. No Telegram yet. Independently useful.

**Phase T2 — Telegram bridge (single host) — ~3-4 days**
- `otaman bridge run|install|status` daemons.
- PreToolUse hook + loopback HTTP IPC (see §5.3).
- `otaman afk on|off|status` flag.
- Telegram bot setup wizard (`otaman accounts add` with `telegram:` step).
- Per-project topic auto-creation on `otaman init`.
- Audit log.
- **Per-project surface overrides** (`platform.yaml surface:` merging over account-level).

Ship-ready milestone: single-host user can approve from phone.

**Phase T2.5 — Learned-pattern grooming — ~1 day**
- `otaman approvals learn` CLI: scan `.agents/approvals.jsonl`, group by normalized shape, offer to add frequent `allow` patterns to `permissions.allow`.
- Shape normalizers for common commands (npm/pnpm/cargo/git/ls/cat/rg).
- Opt-in only — no silent `permissions.allow` writes.

**Phase T3 — Multi-host + cross-account broadcast — ~2 days**
- Per-host daemons; document multi-bot vs. one-bot-per-host.
- Add `host:` tag to every outbound message (transport-neutral).
- **Cross-account broadcast**: `otaman broadcast --all-accounts` CLI + `to: all-accounts` bus routing keyword fanned out by each daemon via its own transport.

**Phase T4 — Central relay (only if needed) — ~2-3 days**
- Relay service with same JSON contract over HTTP.
- Tailscale setup guide.
- Deferred until a user requests it.

**Phase T5 — Slack transport — ~2 days**
- `SlackTransport` implementation.
- Socket Mode app setup wizard.

---

## 12. Decisions & remaining open questions

### Decided (2026-04-23)

- **Bus message surfacing (was Q5)**: **YES**. Daemon surfaces `spec-change-request`, any `priority: urgent|high`, anything `to: human`, and questions addressed to human. Interactive bus messages become real bus writes (ack files + approved/rejected messages) so audit trail and existing `/otaman:approve` machinery keep working. See §5.6.
- **Auto-AFK on SSH (was Q3)**: **YES**, with opt-out. SessionStart hook flips AFK on when `$SSH_CONNECTION` or `$SSH_TTY` is set, with `source: ssh-auto`. Local WSL and interactive terminals stay off by default. Clears on SessionEnd. Global opt-out via `accounts.<name>.afk.auto_on_ssh: false`; per-connection override in `launch-settings.yaml`. See §5.4.
- **AFK duration syntax**: `otaman afk on [DURATION]` accepts `30s` / `15m` / `8h` / `2d` / `1w` / compound (`1h30m`). No arg = indefinite. Stored in `.otaman/afk` YAML with `expires_at` so it survives restarts. See §5.4.
- **Per-project topics (was Q1)**: **YES**, per-project is the v1 topology — one forum topic per `platform.yaml`, matching the project granularity the user already thinks in. Per-repo topics stay an explicit non-goal; revisit only if a 20-repo project surfaces real unreadability in practice. See §5.1.
- **Messenger abstraction layer is a hard requirement (was Q / §10)**: **YES**. The `Transport` Protocol in §10 is treated as a load-bearing architectural boundary, not a v2 afterthought. v1 ships with `TelegramTransport` as the only implementation, but the daemon, hook protocol, config schema, and bus-surfacing logic **must be transport-agnostic**. Concretely:
  - Hook → daemon IPC payload carries no Telegram-specific fields. Callback-button semantics are expressed as abstract actions (`allow` / `deny` / `ask` / `comment`), not Telegram inline-button markup.
  - `accounts.<name>.transport: telegram` selects the transport; `telegram:` block becomes `transport_config:` (Telegram-specific keys scoped there). Accepting `telegram:` as sugar for `transport: telegram` stays for backwards-compat.
  - Bus surfacing policy (§5.6) is expressed in transport-neutral severities/actions; each transport maps them (Telegram → inline buttons, Slack → block kit, Discord → components, Matrix → reactions + threads).
  - v1 PRs include at least one additional stub transport (`NullTransport` for tests, or a skeletal `SlackTransport`) to prove the abstraction isn't accidentally leaking Telegram assumptions.

  **Why:** the user runs an outsource company; different clients will mandate different chat tools (Slack for most corp, Matrix for compliance-sensitive, Discord for some gaming/indie). Rewriting the bridge per client is a non-starter. **How to apply:** during implementation, reject any PR that hardcodes `telegram` outside the transport module, even if "it's just v1." Cheap to preserve now, painful to retrofit later.

- **IPC transport — loopback HTTP on every platform (was Q about Windows named pipes)**: **YES**. Daemon binds `127.0.0.1:<ephemeral>`, writes `{port, token}` to `~/.otaman/bridge-<account>.endpoint` (mode `0600`). Hooks authenticate with `Authorization: Bearer <token>`. Unix sockets and named pipes both dropped. **Why:** one implementation across all platforms, no unix-socket/named-pipe branching, trivially debuggable with `curl`, **and** the same endpoint is reusable substrate for a future local UI (desktop app, VS Code panel, browser extension) — no protocol rework needed when we want that. See §5.3 and §9.

- **Auto-approve learned patterns (was Q1 of Still Open)**: **YES**, in v1.5 (T2+). The audit log `.agents/approvals.jsonl` already captures every decision with request payload, so the learning data exists for free. Implementation:
  - `otaman approvals learn` — scan the ledger, group by `(tool_name, normalized-input-shape)`, surface any group with ≥10 consecutive `allow` decisions and no `deny` in the last 30 days. Present each as an offer: "add to `permissions.allow`? y/n/edit".
  - Normalization rules matter: `Bash {"command": "npm install X@Y"}` should collapse to the `npm install <pkg>@<ver>` shape regardless of package/version (or the human decides what to parametrize when accepting). Start with a small list of shape normalizers (npm install, pnpm, cargo add, git fetch/pull, ls/cat/rg) rather than trying to auto-derive them.
  - Opt-in: the bridge never auto-writes to `permissions.allow`. The CLI command is the only path. Silent promotion would break the compliance story.
  - A Telegram quick-action later: after 10 `allow` on the same shape, the approval message adds a `[Always allow this shape]` button that runs the same codepath. Post-v1.
  **Why:** same-command re-approval is the top complaint after remote approval itself works. **How to apply:** build the shape-grouper + CLI in T2, defer the Telegram quick-action to v1.5.

- **Cross-account broadcast (was Q2 of Still Open)**: **YES**, in v1.5. Rare but useful — security advisory, dependency CVE, company-wide maintenance window. Shape:
  - `otaman broadcast --all-accounts --severity urgent "CVE-2026-XXXX affects @foo/bar, pin <2.3.0"` — CLI iterates configured accounts and calls each daemon's endpoint in turn.
  - Also reachable from the bridge itself: a `from: human, to: all-accounts` bus message (new routing keyword) gets fanned out by each daemon to its own transport.
  - Transport-agnostic — each account's daemon surfaces the message via whatever transport it's configured with (one account's Telegram group, another's Slack channel).
  - Dedup: recipients see one message per account, not N copies. Cross-account ack rollup (did both accounts acknowledge?) is out of scope for v1.5; reporting lives in the audit log.
  **Why:** compliance-driven work sometimes spans the whole stable of clients and manually DMing each group is error-prone. **How to apply:** implement in T3 alongside multi-host support — same fan-out machinery.

- **Per-project surface overrides (was Q3 of Still Open)**: **YES**, in v1. Cheap and high-value. Schema:
  - `platform.yaml` gains an optional top-level `surface:` (or `transport.surface:` for clarity) block. Keys match `accounts.<name>.transport_config.surface`.
  - Merge semantics: project overrides account — project-level `review_request: false` wins even if the account has `review_request: true`. Only keys present in the project block override; unspecified keys inherit.
  - Mute/amplify both directions supported (project can make noisier *or* quieter than account default).
  - Also supports per-agent overrides inside: `surface.by_agent.cto-reviewer.review_request: false` mutes just that agent's reviews for this project.
  **Why:** one chatty observer-heavy project shouldn't force the whole account into a quieter baseline. **How to apply:** implement alongside T2's surfacing logic — merge happens once at message-receipt time, no perf concern.

### Still open

_(empty)_ — all v0 questions resolved 2026-04-23. New questions will land here as implementation surfaces them.

---

## 13. Suggested next step

Prototype Phase T1 first (account isolation without Telegram). That's independently valuable — it replaces the manual PowerShell functions with a maintained, cross-platform, declarative setup that every dev on the team can adopt in minutes. Once T1 is in place, T2 slots on top with no rework because the config layer already knows about accounts.
