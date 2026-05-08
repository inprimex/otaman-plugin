# T2 Live Smoke Test — End-to-End Approval from Phone

This guide walks through the first real hook → daemon → Telegram → phone → decision roundtrip after T2a/T2b/T2c ships. Expect ~10 minutes end-to-end if BotFather cooperates.

**What you're verifying:** a Claude Code tool call triggers a Telegram message with inline buttons on your phone, tapping Approve unblocks Claude, tapping Reject stops it. Same for bus notifications in later phases.

---

## 0. Prerequisites

- T1 + T2a + T2b + T2c are on the branch and tests pass (`pytest tests/ -q`).
- otaman-cli + otaman-bridge installed on whichever machine runs the daemon:
  ```
  pip install otaman-cli otaman-bridge[telegram]
  # or (faster, when developing in the polyrepo workspace):
  cd /path/to/otaman/ && uv sync --all-packages
  ```
  On Linux with PEP 668 (externally-managed Python), add `--user` or use a venv.
- `otaman accounts` already knows your account (e.g. `personal`) with a `config_dir`. Confirm: `otaman accounts list`.
- Your Telegram account. Nothing else — we create the bot + group in steps 1–3.

---

## 1. Create the bot

1. Open Telegram → search `@BotFather` → start a chat.
2. Send `/newbot`.
3. Name: whatever you want (appears in the group; `Otaman Personal Bridge` is fine).
4. Username: must end in `bot` (e.g. `your_otaman_personal_bot`).
5. **Copy the HTTP API token** BotFather replies with. Looks like `7123456789:AAE...`. Keep this chat open — you'll paste one more bit later.
6. Send `/setprivacy` → pick your bot → **Disable** — lets the bot read all group messages (needed for future bus-surfacing features in T2d; optional for T2c approval-only).

---

## 2. Create the group + enable forum topics

1. In Telegram: **New Group** → add your freshly-created bot as a member (search its `@username`).
2. Give it a name (e.g. `Otaman · Personal`).
3. Open the group → **Manage group** (pencil icon) → **Group type: Public** is NOT required; Private works fine.
4. **Manage group → Topics → toggle "Topics" ON**. This flips the group from "chat" to "forum" and is what lets the bridge post per-project threads. The first topic "General" appears.
5. Promote the bot to admin with the minimum rights: **Manage topics** and **Delete messages** are enough. (Management UI: Manage group → Administrators → Add Administrator → pick the bot.)

**Find the group ID.** Three ways, pick whichever is easiest:
- Send any message in the group, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser. Look for `"chat": {"id": -100123..., "is_forum": true}` in the JSON. Copy the negative ID (starts with `-100`).
- Or: use `@getidsbot` — add it to the group briefly, it DMs you the group ID.
- Or: invite `@RawDataBot` for one message, read the ID it prints, remove it.

**Find your user ID.** Same trick in a DM: message `@getidsbot` or `@userinfobot`, it replies with your numeric Telegram user ID. Note it down — you'll need it for the allowlist.

---

## 3. Store the bot token

Never put the token in `platform.yaml` or `launch-settings.yaml` (lint warns, `otaman doctor` warns, git would leak it). Use `.otaman/secrets.env`:

```bash
# From your otaman folder (where platform.yaml lives)
cat >> .otaman/secrets.env <<'EOF'
OTAMAN_TG_BOT_PERSONAL=7123456789:AAE-your-token-here
EOF
chmod 600 .otaman/secrets.env    # POSIX; Windows ACL's by default
```

Sanity check:

```bash
otaman doctor                 # scans git history for leaked secrets.env; should be green
grep -r OTAMAN_TG_BOT .        # real token should appear only in .otaman/secrets.env
```

---

## 4. Wire the account to the Telegram transport

Edit `launch-settings.yaml` and extend the account block:

```yaml
accounts:
  personal:
    config_dir: "~/.claude-personal"
    label: "Personal (max)"
    transport: telegram
    transport_config:
      group_id: -1001234567890          # from step 2
      allowed_user_ids: [123456789]     # your user ID; add teammates here later
      auto_create_topics: true          # bot will createForumTopic per project
      bot_token:
        sources:
          - { type: env,    name: OTAMAN_TG_BOT_PERSONAL }
          - { type: dotenv, name: OTAMAN_TG_BOT_PERSONAL }
```

`auto_create_topics: true` is the ergonomic default — the bridge will make a `<project-name>` topic inside the group the first time a message for that project needs sending, and cache the resulting thread ID in `~/.otaman/bridge-personal-topics.json`.

Verify the config loads cleanly:

```bash
# Quick python sanity check (stays behind launch-settings.yaml's existing schema)
py -c "
from bridge.config import load_account_config
from pathlib import Path
cfg = load_account_config('personal', Path('launch-settings.yaml'))
print('transport:', cfg.transport)
print('config:', {k: v if k != 'bot_token' else '<resolved>' for k, v in cfg.transport_config.items()})
print('unresolved secrets:', list(cfg.unresolved_secrets))
"
```

If `unresolved secrets` is non-empty, the chain didn't find the token — double-check `.otaman/secrets.env`.

---

## 5. Start the daemon

Two options — pick one:

**Option A — foreground (quick testing, ties you to a terminal):**

```bash
otaman bridge run --account personal
```

Expected output:

```
otaman bridge: account=personal transport=telegram port=53427 endpoint=/home/you/.otaman/bridge-personal.endpoint
Press Ctrl-C to stop.
```

Keep this terminal open.

**Option B — install as a service (recommended for real use):**

```bash
otaman bridge install --account personal --linger \
  --idle-auto-afk-minutes 30        # optional: auto-flip AFK after 30 min of no prompt activity
# On Linux, --linger makes the service survive SSH logout.
# Check it's running:
systemctl --user status otaman-bridge@personal    # Linux
launchctl list | grep com.otaman.bridge.personal  # macOS
# Live logs:
journalctl --user -u otaman-bridge@personal -f    # Linux
tail -f ~/Library/Logs/otaman-bridge/*.log        # macOS
```

The installed unit includes `--watch-bus` by default (drains `.agents/bus/active/` and surfaces interactive messages — see §11). Opt out with `--no-watch-bus` if you only want PreToolUse approvals.

Then skip ahead — you don't need a dedicated terminal. In another terminal, confirm the daemon is healthy:

```bash
otaman bridge status
# ACCOUNT   STATE    DETAIL
# personal  running  pid=12345 transport=telegram port=53427 pending=0 uptime=3s
```

---

## 6. Flip AFK on

The PreToolUse hook only routes to the daemon when AFK is on. Local sessions default to off (native terminal prompt still works). Turn it on for testing:

```bash
otaman afk on 30m       # 30-minute window
otaman afk status       # confirm: "AFK: on (source: manual, 29m 59s remaining)"
```

---

## 7. Trigger your first approval

In a Claude Code session (started with the account env var set — either via the launcher or `claude-personal` shell alias from T1 step 7):

```
claude "run a harmless bash command to test the bridge"
```

Claude will propose e.g. `ls`. The PreToolUse hook sees `AFK: on`, finds the endpoint file, and posts `/approval` to the daemon. Within ~1 second your phone should buzz with:

```
🟡 [<project>] <repo> · <agent>
Tool: Bash
Command: ls
Reason: ...

[✅ Approve]  [❌ Reject]  [📄 Details]  [⏱ Snooze 15m]
```

Tap **Approve**. Back in the terminal, Claude proceeds as if you'd answered the local prompt. The Telegram message edits to `✓ approved by telegram:<your-user-id> · HH:MM`.

Tap **Reject** on the next one and confirm Claude honors it (message shows "Permission denied" with the responder note).

**Which tools buzz your phone?** Only the ones that actually change state:
`Bash`, `Write`, `Edit`, `NotebookEdit`. Read-only tools (`Read`, `Grep`,
`Glob`, and all `mcp__*` tools that fetch state) bypass the bridge so
routine orchestration doesn't spam the phone. To widen or narrow, edit
the `matcher:` in `hooks/hooks.json` for the `bridge-approval.sh` entry
— anything matching the matcher routes through the bridge when AFK is on.

---

## 8. Test the fail-safe paths

These confirm the bridge never makes Claude harder to use than stock:

1. **Daemon down**: `Ctrl-C` the daemon, trigger another tool call. The hook should log `otaman bridge: daemon unreachable …` to stderr and surface the native terminal prompt. Nothing blocks.
2. **AFK off**: `otaman afk off`, trigger a tool call. No Telegram traffic, native prompt shows. Phone stays quiet.
3. **Unauthorized tapper**: have a friend who's NOT in `allowed_user_ids` try to approve. Telegram should show them an "Not authorized to approve this request." alert, and the approval stays pending. (Check the daemon log for `rejected tap from uid=...`.)
4. **Timeout**: set `OTAMAN_BRIDGE_TIMEOUT=5` in your shell, trigger a tool call, don't tap anything. After 5s the Telegram message edits to `⏱️ expired` and the terminal falls back to the native prompt.

---

## 9. Auto-AFK — unattended vs idle

AFK can flip on three ways. Pick whichever matches your workflow:

| Source | Trigger | When to use |
|---|---|---|
| `manual` | `otaman afk on [DURATION]` | You know you're stepping away. Survives session end. |
| `unattended` | Launcher connection with `unattended: true` exports `OTAMAN_UNATTENDED=1`; SessionStart hook sees it and flips AFK on. | Boxes that are deliberately not babysat (overnight runs, long-lived agents). Cleared by SessionEnd. |
| `idle-auto` | Daemon's IdleAFKMonitor sees no `UserPromptSubmit` hook fire for `--idle-auto-afk-minutes N`. | The "I walked away" case. Automatically clears when you type a prompt back in Claude. |

**Important change from earlier versions**: pure SSH presence (`SSH_CONNECTION` / `SSH_TTY`) no longer triggers auto-AFK on its own. That misfired when the human was actively launching tabs from a local laptop into a remote box — they were "at the keyboard" despite the session being SSH. Set `unattended: true` in `launch-settings.yaml` for the genuinely unattended-box case, or use idle-auto for presence tracking.

**Kill switch**: `OTAMAN_AFK_AUTO=0` disables the SessionStart hook entirely for a session.

**Manual always wins**: if you've set `otaman afk on 8h`, neither unattended nor idle-auto will touch it. Likewise the idle-auto monitor only clears entries it wrote itself (`source: idle-auto`).

---

## 10. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Phone gets nothing, daemon log quiet | AFK is off (`otaman afk status`) or CLAUDE_CONFIG_DIR doesn't point at a `.claude-<name>` path the hook can map to an account |
| `daemon unreachable` warnings | Daemon crashed (check the `otaman bridge run` terminal) or endpoint file is stale (`rm ~/.otaman/bridge-personal.endpoint` and restart) |
| `cannot determine account` warnings | No `OTAMAN_ACTIVE_ACCOUNT`, no `.claude-<name>` CLAUDE_CONFIG_DIR, and no `expected_account` in the repo's `.otaman` marker. Set one. |
| Approval goes through but lands in the wrong group | `group_id` is wrong (you might have copied from a different chat — `-100` prefix required for supergroups) |
| "Bad Request: message thread not found" in daemon log | The forum topic the bridge cached (`~/.otaman/bridge-personal-topics.json`) was deleted. Remove that file — next message auto-recreates |
| Button taps do nothing | Bot isn't promoted to admin with "Manage topics" permission, or the allowlist rejects your user ID. Check `allowed_user_ids` and the daemon log. |
| `createForumTopic` errors | Group isn't a forum. Manage group → Topics → toggle ON. Then `rm ~/.otaman/bridge-personal-topics.json` to clear any cached negative results. |

If the daemon crashes on startup, the error is almost always one of:
- `bot_token is required` — secret didn't resolve (check `.otaman/secrets.env`)
- `python-telegram-bot not installed` — `pip install python-telegram-bot>=21`
- `endpoint file already exists and a daemon IS running` — another daemon really is live. `otaman bridge stop --account personal` (auto-cleans if the prior process is dead).

---

## 11. Bus message surfacing (T2d)

With `--watch-bus` (default for installed services), the daemon polls `.agents/bus/active/` every ~2s and surfaces interactive messages to Telegram:

- **`spec-change-request`** (agent proposes a spec change) → Approve / Reject / Details card in the project's topic. Tap Approve and the daemon writes `acks/{stem}.human.ack` + broadcasts `spec-change-approved` to the bus — indistinguishable from running `/otaman:approve` locally.
- **`to: human`** messages (urgent pages, questions) → Acknowledge + free-text reply.
- **Reply by message**: reply to any card in Telegram (tap the card → Reply) and the text lands on the bus as an `info` message from `human` to the original proposer. Works for commentary on still-pending decisions.

Configure via `platform.yaml`:

```yaml
surface:
  review_request: true       # turn a default-off message type ON globally
  task_complete: false       # explicit default
  by_agent:
    cto-reviewer:
      review_request: false  # this agent's reviews stay quiet even globally on
```

Default policy (design §5.6): `spec-change-request` and `to: human` are always interactive; `task-assignment` and info broadcasts are always silent; `review-request` / `task-complete` / `spec-change-{approved,rejected}` are configurable (default off).

Dedup state lives at `<otaman>/.otaman/bus-surfaced.state` (JSON, pruned after 7 days). Clear it if you want a previously-surfaced message to re-appear.

---

## 12. Clarifying questions via the Stop hook

When Claude finishes a turn with an unanswered question (e.g. "Which approach should I take?"), the `Stop` hook can surface it to Telegram via `/otaman:ping`. The Force Reply / comment path (see §11 "Reply by message") lets you answer from your phone and the text lands in the bus as an `info` message.

---

## What to do next

Everything in the T2 series is now live: PreToolUse approvals, Stop-hook questions, bus message surfacing, interactive spec-change flow, idle AFK, unattended-session opt-in. For design context beyond this walkthrough see `references/remote-approval-design.md`.

Follow-up work that is **not** in v1: multi-host with >1 daemon per account (§6.2), central relay (§6.3), Slack transport, auto-approve learned patterns, cross-account broadcast. Ship a user-facing PR when one of these has a concrete driver.
