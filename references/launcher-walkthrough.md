# Launcher folder walkthrough

The launcher is the piece that makes "open a terminal tab for each
agent" a single command instead of N manual SSH invocations. This
walkthrough explains the launcher folder concept, configures one for
your project, and runs it end-to-end.

**Audience:** anyone who has more than one repo in their otaman project
(i.e., everyone except minimal pre-sale projects).

**Prerequisites:**
- `otaman init` has run successfully (`.agents/` + per-repo configs exist)
- For SSH connections: SSH key access to your target host configured
- For tmux-backed connections (recommended): `tmux` installed on the host

---

## Concept: what is a launcher folder?

A **launcher folder** is a directory containing two YAML files plus a
thin wrapper script. The launcher reads `platform.yaml` (your project
config) and `launch-settings.yaml` (your local connection + account
preferences), then opens one terminal tab per repo with the right cwd,
env vars, and `claude` invocation.

Launcher folders are **decoupled from the project itself**, which means:

- The project (and its `platform.yaml`) lives wherever your code lives —
  often on a server.
- The launcher folder lives on your laptop, points at the project, and
  encodes per-user preferences (SSH host, tmux on/off, Claude config dir,
  Telegram routing).
- One project can have multiple launcher folders — for different
  machines, different teams, different connection paths.

Typical layout:

```
C:\work\launchers\my-project\        ← launcher folder (Windows laptop)
├── launch.ps1                       ← thin wrapper, calls the orchestrator
├── launch-settings.yaml             ← connections + accounts (this file)
└── platform.yaml                    ← copy of project's platform.yaml
```

Or on Linux/macOS: `~/launchers/my-project/launch.sh` + same yaml pair.

---

## Step 1: Scaffold the folder

From within the project directory (where `platform.yaml` lives):

```bash
otaman launcher ~/launchers/my-project
```

This creates the folder with `launch.ps1` (or `launch.sh`), copies your
`platform.yaml`, and writes a starter `launch-settings.yaml` with three
named connections: `local`, `lan`, `mesh`.

If you don't yet have a project to point at, you can scaffold an empty
launcher and fill it in by hand later:

```bash
otaman launcher ~/launchers/test --plugin-path /path/to/otaman-plugin
```

---

## Step 2: Configure connections

The `connections:` block in `launch-settings.yaml` defines how to reach
your project. Three connection types ship out of the box:

### `local` — project on the same machine
```yaml
connections:
  local:
    type: "local"
    local_root: "C:/work/my-project/my-project-otaman"
    local_shell: "wsl"          # wsl | powershell
    wsl_distro: "Ubuntu"        # WSL distro to use
    account: "personal"
```

Use this for native dev on your laptop. On Windows, `local_shell: wsl`
runs everything inside WSL so the bash hooks work natively.

### `lan` — project on a LAN server
```yaml
  lan:
    type: "ssh"
    reliability: tmux           # wrap each session in tmux for resilience
    ssh_client: "ssh"
    ssh_default_host: "user@192.168.1.100"
    ssh_key: "~/.ssh/id_ed25519"
    ssh_remote_root: "/home/user/my-project/my-project-otaman"
    ssh_plugin_path: "/home/user/otaman/otaman-plugin"
    account: "personal"
```

`reliability: tmux` is **strongly recommended** for SSH connections —
each tab opens a named tmux session inside the SSH connection. If the
SSH drops (laptop sleep, network blip, mesh handoff), the tmux session
keeps running. Reconnecting reattaches you to the live agent.

### `mesh` — project on a remote host via Tailscale / Netbird / ZeroTier
```yaml
  mesh:
    type: "ssh"
    reliability: tmux
    extends: "lan"              # inherits everything from `lan`
    ssh_default_host: "user@100.65.57.73"
```

`extends:` saves duplication. You only override what differs between
LAN and mesh — typically just the host IP/name.

Activate one with `active_connection: "lan"` (or pick at run time with
`./launch.ps1 -Connection mesh`).

---

## Step 3: Configure routing (account)

The `accounts:` block defines the per-host **routing identity** —
what tags AFK state, what Telegram group receives approvals, which
Claude config dir holds the OAuth.

```yaml
accounts:
  personal:
    config_dir: "~/.claude"          # Claude OAuth dir (login scope)
    label: "Personal"
    # Telegram routing — see references/telegram-setup.md for setup
    transport: telegram
    transport_config:
      group_id: -1003928170207
      allowed_user_ids: [799080965]
      bot_token:
        sources:
          - { type: keyring, service: otaman, account: tg-bot-personal }
```

**Naming convention** for corporate vs personal:

| Scope | config_dir | account name |
|---|---|---|
| Personal projects | `~/.claude/` (default) | `personal` |
| Corporate account #1 | `~/.claude-acme/` (per-org) | per project (`acme-naz`, `acme-greenbin`) |
| Corporate account #2 | `~/.claude-bigco/` | `bigco-x`, `bigco-y` |

One login per corporate organisation; per-project routing on top. See
`telegram-setup.md` for details on bot tokens + group IDs.

---

## Step 4: Per-repo launch commands

Each repo in `platform.yaml` needs a `launch:` block telling the launcher
how to start the agent for that repo:

```yaml
# platform.yaml (in the launcher folder)
repos:
  - name: my-service
    path: ./my-service
    owner: backend-agent
    tech: [python]
    launch:
      title: "Backend"                  # tab title
      color: "#3b82f6"                  # tab tint (Windows Terminal)
      shell: ssh                        # ssh | wsl | powershell
      commands:
        - "source ~/.nvm/nvm.sh && claude --plugin-dir ~/otaman/otaman-plugin '/otaman:check'"
```

The `commands:` list runs after the connection is established. Typical
pattern:
1. Source nvm or pyenv (if your shell needs it)
2. Launch `claude --plugin-dir <path-to-otaman-plugin> '/otaman:check'`

The slash command at the end is what the agent should run on first
prompt — `/otaman:check` shows pending bus messages, which is the
natural "what was I doing?" first-glance for any agent session.

---

## Step 5: Run it

```powershell
# Windows
cd C:\work\launchers\my-project
.\launch.ps1
```

```bash
# Linux / macOS
cd ~/launchers/my-project
./launch.sh
```

The launcher shows you a menu:

```
=== Otaman Agent Launcher ===
  [OK] Connection: lan (ssh)

[▶] Reading platform.yaml
  [OK] Found 5 repos (5 active), 0 profiles
  [OK] 5 launchable
  [OK] Account: personal (~/.claude)

Available profiles:
  1. full (all - 5 active)
  6. pick (choose individual repos)

Select profile (1-6) or name:
```

Pick "all" or a specific profile. The launcher opens N Windows Terminal
tabs (or N gnome-terminal windows, or N iTerm tabs), each:
1. Establishing the chosen connection (local/SSH)
2. Wrapping in tmux if `reliability: tmux`
3. `cd`'ing to the repo
4. Exporting env (`CLAUDE_CONFIG_DIR`, `OTAMAN_ACTIVE_ROUTING`, `MAESTRO_ACTIVE_ACCOUNT` legacy alias)
5. Running the configured launch commands

---

## Step 6 (optional): profiles for subsets

If your project has many repos but you usually work on a subset, add
profiles to `platform.yaml`:

```yaml
profiles:
  backend:
    description: "Backend services — API + workers"
    repos: [api, worker, shared-types]
  frontend:
    description: "Web app iteration"
    repos: [web, web-admin, shared-types]
  full:
    description: "Everything (5 agents)"
    repos: all
```

Launcher menu offers each profile + a `pick` option for ad-hoc
combinations.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `0 launchable` despite N repos found | Add `launch:` blocks (shell + commands) to each repo in `platform.yaml` |
| Tab title resets to "default" after agent runs | Windows Terminal: enable `suppressApplicationTitle: true` in your profile (see backlog B-11 for Linux/macOS equivalent) |
| SSH tab closes immediately on launch | Check `ssh_key` path is correct + key isn't passphrase-protected (or use ssh-agent) |
| Tabs spawn but agent identity is wrong | Verify `account:` on the active connection points at an entry in `accounts:` block |
| Can't ack messages from phone | Bridge daemon needs to be running on the remote host — see `telegram-setup.md` |

---

## Where next

- `references/telegram-setup.md` — bot token + group + allowlist for AFK approvals
- `references/git-host-setup.md` — wire up PR/MR posting per provider
- `references/communication-protocol.md` — bus message schema agents use
- `polyrepo-structure.md` — design rationale for the launcher / platform split
