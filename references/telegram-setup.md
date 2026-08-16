# Telegram bot setup walkthrough

This walkthrough takes you from zero to a working Telegram approval flow
for your otaman project in about 10 minutes. By the end, you will be
able to approve agent tool-use prompts from your phone while away from
your machine (AFK mode).

**Audience:** solo developers and small teams setting up the
`otaman-bridge` daemon for the first time.

**Prerequisites:**
- An otaman project initialised (`otaman init` has run successfully)
- A Telegram account on your phone
- 10 minutes

---

## Step 1: Create the bot via @BotFather

@BotFather is the official Telegram bot for creating other bots. You
talk to it from your Telegram client (mobile or desktop).

1. Open Telegram and search for `@BotFather`
2. Start a chat and send `/newbot`
3. BotFather asks for a **display name** — e.g. `Otaman Bridge (Personal)`
4. BotFather asks for a **username** — must end in `bot`, e.g. `my_otaman_bot`
5. BotFather replies with a token that looks like:
   ```
   123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-0123456789
   ```
   **Copy this token immediately and store it somewhere safe** — you
   won't see it again unless you regenerate.

**One bot per maestro account** is the recommended pattern. If you run
multiple projects, create one bot per project (e.g.
`my_otaman_proja_bot`, `my_otaman_projb_bot`) so messages route to the
right place automatically.

---

## Step 2: Store the bot token securely

The token must NOT live in `platform.yaml` or `launch-settings.yaml`.
Otaman reads it via the `_secrets` chain — three sources, checked in
order:

| Order | Source | When to use |
|---|---|---|
| 1 | OS environment variable | local dev, CI |
| 2 | `.otaman/secrets.env` dotenv file | per-project, gitignored |
| 3 | OS keyring (macOS Keychain / Windows Credential Manager / Linux Secret Service) | recommended for long-term local use |

The **keyring is the safest** for everyday use because the token is
encrypted at rest by the OS. The **dotenv file** is fine if you can
guarantee `.otaman/` stays out of git (otaman's `.gitignore` template
already covers this).

### Option A — Keyring (recommended)

Pick a unique secret name per project, e.g. `tg-bot-proja`:

```bash
python3 -c "
import keyring
keyring.set_password('otaman', 'tg-bot-proja', 'PASTE-TOKEN-HERE')
"
```

Then reference it in `launch-settings.yaml`:

```yaml
accounts:
  proja:
    config_dir: "~/.claude-acme"
    label: "ProjA"
    transport: telegram
    transport_config:
      group_id: -1001234567890        # filled in Step 3
      allowed_user_ids: [123456789]   # filled in Step 4
      bot_token:
        sources:
          - { type: keyring, service: otaman, account: tg-bot-proja }
```

### Option B — Dotenv file

In your maestro folder, create or edit `.otaman/secrets.env`:

```bash
mkdir -p .otaman
echo 'OTAMAN_TG_BOT_PROJA=PASTE-TOKEN-HERE' >> .otaman/secrets.env
chmod 600 .otaman/secrets.env
```

Then reference in `launch-settings.yaml`:

```yaml
      bot_token:
        sources:
          - { type: dotenv, name: OTAMAN_TG_BOT_PROJA }
          - { type: env,    name: OTAMAN_TG_BOT_PROJA }   # also works if exported in shell
```

### Verify

```bash
otaman doctor
```

The "Secrets Hygiene" check confirms `.otaman/secrets.env` is gitignored
and has mode 600. If it warns, follow the suggested fix.

---

## Step 3: Create a Telegram group + get its group_id

Per-project Telegram routing is the whole point of the multi-account
setup. Each project gets its own group, where bus approvals appear as
forum topics.

1. In Telegram, create a new **group** (not a channel). Call it whatever
   you want — `Otaman ProjA`, `Otaman ProjB`, etc.
2. Add your bot to the group as an administrator. Required permissions:
   - Pin messages
   - Manage topics (this enables auto-created forum topics per project)
3. Enable **Topics** in the group settings (group info → edit → enable Topics).
4. Find the group_id (looks like `-1001234567890`):
   - **Easiest method:** add the bot @username_to_id_bot or @get_id_bot
     to the group temporarily. It posts the group's chat ID; copy it.
   - **Via the Telegram API:** send any message in the group, then visit
     `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser. The
     `chat.id` in the response is your group_id.

Paste the group_id into `launch-settings.yaml`:

```yaml
      group_id: -1001234567890
```

The minus sign prefix matters — that's how Telegram distinguishes group
IDs from user IDs.

---

## Step 4: Add yourself to the allowlist

For security, the bridge only honors approvals from explicitly-listed
Telegram user IDs. Anyone else's reply to the bot is ignored.

1. Find your own Telegram user ID:
   - Add @userinfobot or @getidsbot to the group, or DM @userinfobot
   - It replies with your user ID (a positive integer, e.g. `123456789`)
2. Add to the allowlist in `launch-settings.yaml`:

```yaml
      allowed_user_ids: [123456789]
```

You can add multiple IDs (each teammate gets their own entry).
**Do not skip this step** — without an allowlist, the daemon refuses
to start.

---

## Step 5: Start the bridge daemon

```bash
otaman bridge install     # installs as systemd (Linux) or launchd (macOS) service
otaman bridge start
otaman bridge status      # should show "running, transport=telegram, account=<name>"
```

On Windows, the bridge runs as a foreground process — open a terminal,
`otaman bridge run --account proja` and leave it open.

---

## Step 6: Test the round trip

In one terminal:
```bash
otaman afk on
```

Then in your project, run something that would normally need approval
(a `Bash` tool use from an agent session). The bridge intercepts and
posts to your Telegram group:

> [Tool use approval] backend-agent wants to run:
> `git push origin main`
> Approve / Reject

Tap Approve from your phone. The agent's tool call completes. ✅

When you're back at your desk:
```bash
otaman afk off
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `bridge: failed to authenticate token` | wrong token in keyring/dotenv | regenerate via @BotFather or fix the secret value |
| `bridge: chat_id not found` | bot not in the group, or wrong group_id | re-add bot to group + verify group_id has `-` prefix |
| Telegram messages don't arrive | bot lacks "Pin messages" or "Manage topics" permission | promote bot to admin with both permissions |
| `daemon already running` | previous instance still up | `otaman bridge stop` then `otaman bridge start` |
| Token leaked to git | committed `.otaman/secrets.env` by mistake | regenerate token immediately via @BotFather, rotate the secret, force-push history rewrite |

**Logs:** `otaman bridge logs` or directly at `~/.otaman/bridge-<account>.log`

---

## Where next

- `references/launcher-walkthrough.md` — configure tabs to auto-start
  agents into AFK-friendly tmux sessions
- `references/git-host-setup.md` — wire up PR/MR posting per provider
- `references/communication-protocol.md` — understand the bus message
  schema agents use
