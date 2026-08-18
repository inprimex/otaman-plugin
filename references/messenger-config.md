# Messenger Configuration — Setup Guide

How to wire a otaman account to a messenger transport. Covers the
full bot-creation => token-storage => config-wiring => smoke-test path
for each supported transport.

**Currently supported:**
- **Telegram** (T2b) — long-polling, forum topics, inline keyboard. This file.
- Slack (T5, planned) — Socket Mode, block-kit actions, channels.
- Discord, Matrix, generic WebhookTransport (post-v1).

---

## 1. Where secrets go — one-line summary

Every messenger setup stores its bot token / API key in a single place:

```
<otaman-folder>/.otaman/secrets.env
```

Note: **two different things in the otaman layout both use the name `.otaman`**:
- `.otaman` (a single FILE) in each *managed repo*'s root — points back to the otaman folder.
- `.otaman/` (a DIRECTORY) inside the *otaman folder* itself — holds runtime state like `secrets.env`, `afk`, `bridge-*.endpoint`.

For a project like watchtower where the otaman folder is `C:/work/watchtower/watchtower-otaman/`, the secrets file is:

```
C:/work/watchtower/watchtower-otaman/.otaman/secrets.env
```

Format is plain `KEY=VALUE`, one per line. `#` comments supported. The file is gitignored by `/otaman:init` and `/otaman:scan`, mode `0600` on POSIX. A `.example` stub is committed so teammates know which keys are expected.

---

## 2. Telegram

### 2.1 Bot creation (BotFather)

In Telegram, open `@BotFather` and:

```
/newbot
<bot display name — whatever>
<username ending in bot>
```

BotFather replies with a token of the form `7123456789:AAE...` — save it, you'll paste it in step 2.3.

Recommended BotFather settings:
```
/setprivacy => <your bot> => Disable     (lets the bot read group messages —
                                         needed for T2d bus surfacing later)
/setjoingroups => <your bot> => Enable   (default; lets admin add it to groups)
```

### 2.2 Group creation + forum topics

1. Create a supergroup in Telegram (New Group => add your bot).
2. **Manage group => Topics => toggle ON.** This is what lets the bridge post per-project threads. Without this, `createForumTopic` API calls fail.
3. Promote the bot to admin. Required rights: **Manage topics** (+ **Delete messages** is handy for cleanup).

**Find the group ID.** Easiest: add `@getidsbot` to the group briefly, it DMs you the ID. The ID for supergroups with forum topics is negative and starts with `-100`. Example: `-1001234567890`.

**Find your user ID.** In a DM with `@getidsbot` or `@userinfobot`, it replies with your numeric ID. This goes in `allowed_user_ids` — taps from anyone else are rejected at the callback handler.

### 2.3 Store the bot token

From inside the otaman folder (where `platform.yaml` lives):

```bash
# bash / zsh / fish
cat >> .otaman/secrets.env <<'EOF'
OTAMAN_TG_BOT_<ACCOUNT>=<paste-BotFather-token>
EOF
chmod 600 .otaman/secrets.env
```

```powershell
# PowerShell
Add-Content -Path .otaman\secrets.env `
  -Value "OTAMAN_TG_BOT_<ACCOUNT>=<paste-BotFather-token>"
# Windows ACL's the file to your SID by default; no chmod needed
```

The `<ACCOUNT>` part is the uppercase account name — e.g. for the `personal` account, the env var name is `OTAMAN_TG_BOT_PERSONAL`.

Sanity checks:

```bash
otaman doctor                          # fails if secrets.env is in git history
cat .otaman/secrets.env | head -1      # should show your KEY=... line
```

### 2.4 Wire the account — programmatically

```bash
otaman accounts configure-telegram personal \
    --group-id -1001234567890 \
    --allowed-user-ids 123456789 \
    [--bot-token-env OTAMAN_TG_BOT_PERSONAL]     # default from account name
    [--default-topic-id 42]                       # optional fallback topic
    [--no-auto-create-topics]                     # opt out of auto-create
```

This edits `launch-settings.yaml` in place, preserving everything outside the account's block. Running it again overwrites the transport block cleanly — no stale config accumulates.

Multiple approvers:

```bash
otaman accounts configure-telegram personal \
    --group-id -1001234567890 \
    --allowed-user-ids 123456789,987654321,555555555
```

### 2.5 Wire the account — manually

If you prefer editing `launch-settings.yaml` directly, the block looks like this under an existing account:

```yaml
accounts:
  personal:
    config_dir: "~/.claude-personal"
    transport: telegram
    transport_config:
      group_id: -1001234567890
      allowed_user_ids: [123456789]
      auto_create_topics: true
      bot_token:
        sources:
          - { type: env,     name: OTAMAN_TG_BOT_PERSONAL }
          - { type: dotenv,  name: OTAMAN_TG_BOT_PERSONAL }
          - { type: keyring, service: otaman, account: tg-otaman_tg_bot_personal }
```

Short-form sugar (legacy) is also accepted — leave out `transport:` + `transport_config:` and use a `telegram:` block at the same indent as `config_dir`. `bridge/config.py` expands it to the long form on read.

### 2.6 Install dependencies + start the daemon

```bash
# Core deps (PyYAML, fastmcp, keyring) — one-time per machine
pip install -r requirements.txt

# Transport deps (python-telegram-bot) — needed when bridge runs
pip install -r requirements-bridge.txt
```

On Linux with PEP 668 (externally-managed Python environment), add
`--user` to each `pip install` or use a venv.

### 2.7 Running the daemon

Two choices. Installing as a service is strongly recommended for any
real use — the foreground mode ties you to a terminal.

**Foreground (testing / debugging):**

```bash
otaman bridge run --account personal           # ctrl-C to stop
```

**As a system service (Linux systemd / macOS launchd):**

```bash
otaman bridge install --account personal
# Linux: also survive SSH logout on an unattended box:
otaman bridge install --account personal --linger
# Enable idle-based auto-AFK (flips on after 30 min of inactivity):
otaman bridge install --account personal --idle-auto-afk-minutes 30
# Multi-account setups:
otaman bridge install --all

# One-time preview without touching anything:
otaman bridge install --account personal --dry-run

# Stop and disable:
otaman bridge uninstall --account personal
```

Installed-service side effects:
- Includes `--watch-bus` by default — the daemon drains `.agents/bus/active/`
  and surfaces `spec-change-request` / `to: human` messages to Telegram with
  interactive buttons. Opt out with `--no-watch-bus` (approvals-only).
- Starts now AND on every boot (`--no-enable` to skip the latter,
  `--no-start` to skip the former).
- Auto-restarts on crash (5s backoff).
- Locks the Python interpreter used at install time via
  ``OTAMAN_PYTHON`` so conda / venv / nvm drift won't break it.
- Logs via `journalctl --user -u otaman-bridge@<account>` on Linux,
  `~/Library/Logs/otaman-bridge/` on macOS.
- Windows: not yet supported; use the foreground mode or wrap
  manually with NSSM. See design §5.7.

In another terminal:

```bash
otaman bridge status
# ACCOUNT   STATE    DETAIL
# personal  running  pid=12345 transport=telegram port=53427 pending=0 uptime=3s
```

### 2.7 First approval

```bash
otaman afk on 30m
```

Now trigger a Claude tool call — the phone should buzz with an approval card. Tap Approve. Claude proceeds.

Full walkthrough + 10 troubleshooting rows: `references/t2-live-test.md`.

---

## 3. Adding a new project (greenfield)

1. `otaman scan <project-dir>` — discovers repos, drafts `platform.yaml` + `launch-settings.yaml`.
2. `otaman init` — scaffolds `.agents/`, writes `.otaman/secrets.env.example`, stamps per-repo `.otaman` markers.
3. `otaman accounts add <account> --config-dir ~/.claude-<account>` — declare the account.
4. `otaman accounts configure-telegram <account> --group-id ... --allowed-user-ids ...` — wire messenger.
5. Follow 2.3 to paste the token into `.otaman/secrets.env`.
6. Follow 2.6 to start the daemon + test.

## 4. Adopting on an existing project (brownfield)

You already have `platform.yaml` + `launch-settings.yaml` but no `accounts:` block or no messenger config.

1. `otaman accounts add personal --config-dir "~/.claude-personal"` — creates the accounts block if missing.
2. Edit `launch-settings.yaml`: add `account: personal` under each connection that should use this identity.
3. `otaman accounts configure-telegram personal --group-id ... --allowed-user-ids ...`.
4. Same token-in-secrets.env + daemon-start flow as above.

Nothing else changes — your existing `platform.yaml` / connections / hooks are left alone. Removing messenger = `otaman accounts add-back-the-telegram-block` removed manually, or re-run `configure-telegram` with different settings to replace.

---

## 5. Multiple accounts on one machine

Running both `personal` and `client` (e.g. B2B outsource work)? Each needs its own bot, its own group, its own token, its own daemon:

```bash
# Account setup
otaman accounts add personal  --config-dir "~/.claude-personal"
otaman accounts add client   --config-dir "~/.claude-client"

otaman accounts configure-telegram personal  --group-id ... --allowed-user-ids ...
otaman accounts configure-telegram client   --group-id ... --allowed-user-ids ...

# Secrets (one line per account)
cat >> .otaman/secrets.env <<'EOF'
OTAMAN_TG_BOT_PERSONAL=...
OTAMAN_TG_BOT_CLIENT=...
EOF

# Run both daemons (separate terminals, or background)
otaman bridge run --account personal  &
otaman bridge run --account client   &

otaman bridge status
# ACCOUNT   STATE    DETAIL
# personal  running  pid=... transport=telegram ...
# client    running  pid=... transport=telegram ...
```

Each daemon has its own endpoint file at `~/.otaman/bridge-<account>.endpoint`, so they don't collide. The PreToolUse hook resolves which daemon to call by looking at `OTAMAN_ACTIVE_ACCOUNT` (set by the launcher) or the `CLAUDE_CONFIG_DIR` basename.

---

## 6. Troubleshooting quick reference

| Problem | First place to look |
|---|---|
| Phone doesn't buzz at all | `otaman afk status` (probably off) + `otaman bridge status` (daemon not running?) |
| Daemon crashes on startup with `bot_token is required` | `.otaman/secrets.env` missing or key name wrong |
| `python-telegram-bot not installed` | `pip install -r requirements-bridge.txt` |
| `createForumTopic` errors in daemon log | Group isn't a forum; Manage group => Topics => ON. Delete `~/.otaman/bridge-<account>-topics.json` to clear cached failures. |
| Taps do nothing, daemon logs "rejected tap from uid=..." | Your user ID isn't in `allowed_user_ids`. Run `configure-telegram` again with the right IDs. |
| "message thread not found" | Topic was deleted from the group. Delete `~/.otaman/bridge-<account>-topics.json`; next message recreates it. |
| `endpoint file already exists` on `bridge run` | Stale after a crash. Run `otaman bridge stop --account <name>` or delete `~/.otaman/bridge-<name>.endpoint` and retry. |

Full live-test walkthrough: `references/t2-live-test.md`.
