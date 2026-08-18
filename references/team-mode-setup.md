# Team-mode setup walkthrough

End-to-end onboarding for a developer joining an otaman-coordinated team.
By the end you'll have your Claude Code authenticated against the team's
otaman-bridge, with `list_team_sessions`, `send_message_to_user`,
`request_review`, and the other [team-mode MCP tools](../reference/mcp-tools.md#otaman-bridge-7-tools)
working in any project where you drop a `.mcp.json`.

**Audience:** developers joining an existing otaman team. If you're the
person *setting up* the bridge (Zitadel bootstrap, Cloudflare Tunnel,
machine users, etc.), see [Cloudflare Tunnel deployment](cloudflare-tunnel.md)
first.

**Prerequisites:**
- Claude Code CLI v2.1.x installed (`claude --version`).
- Your team admin has given you: the bridge public URL (typically
  `https://otaman.<your-team-domain>`) and your Zitadel login credentials
  (email + initial password).
- Network access to the bridge URL from your machine. If your team's
  bridge is netbird-mesh-only, install netbird first; if it's
  Cloudflare-fronted (or any public HTTPS), no VPN needed.

---

## What the bridge does for you

The bridge is the team's coordination layer. It runs once for the whole
team and exposes MCP tools that your Claude Code can call to:

- See who else on the team is online and what repo they're working on
- Send another developer a message (or a structured review request)
- Read your own inbox of messages from teammates
- Get a stand-up-style "what's happening in the last 24h" summary

Authentication is per-developer via OIDC (your team's Zitadel). The
bridge identifies you by the `sub` claim in your JWT, so messages
you send carry your real identity — no spoofing, no shared service
accounts.

---

## Step 1: Drop the `.mcp.json` in your project

Add a project-local `.mcp.json` pointing at the bridge URL your admin
gave you. The file is intentionally minimal — **no tokens, no
client_id**. Claude Code does the OAuth dance on first use.

```json
{
  "mcpServers": {
    "otaman-bridge": {
      "type": "http",
      "url": "https://otaman.your-team.example/mcp"
    }
  }
}
```

Drop it at the root of any project where you want team-mode tools
available. Same file works in every project — it's just a pointer.

---

## Step 2: Pre-allow the safe read tools (optional but nice)

By default Claude Code will prompt for permission the first time
each MCP tool is called. To skip the prompt for the read-only ones,
add this to `.claude/settings.local.json` next to the `.mcp.json`:

```json
{
  "enableAllProjectMcpServers": true,
  "enabledMcpjsonServers": ["otaman-bridge"],
  "permissions": {
    "allow": [
      "mcp__otaman-bridge__list_team_sessions",
      "mcp__otaman-bridge__check_messages",
      "mcp__otaman-bridge__get_recent_activity",
      "mcp__otaman-bridge__mark_message_read"
    ]
  }
}
```

The mutating tools (`send_message_to_user`, `request_review`,
`kill_session_for_user`) intentionally still prompt — they have
visible-to-others side effects.

---

## Step 3: Launch Claude Code and authenticate

```bash
cd ~/path/to/your/project
claude
```

In the Claude Code TUI:

1. Type `/mcp`. You should see `otaman-bridge · △ needs authentication`.
2. Arrow down to `otaman-bridge`, press **Enter**, choose **Authenticate**.
3. Your default browser opens to your team's Zitadel login page.
4. Log in with the credentials your admin gave you.
5. If Zitadel prompts you to change the initial password, do so.
6. After redirect, the browser shows "Authentication successful — you
   can close this tab" (or similar). Switch back to Claude Code.
7. `/mcp` now shows `otaman-bridge · ✔ connected`.

**Under the hood**, Claude Code:

- Fetched `https://otaman.your-team.example/.well-known/oauth-protected-resource`
- Followed the issuer to Zitadel
- Dynamically registered itself as an OIDC client via the bridge's
  RFC 7591 endpoint
- Ran the authorization_code + PKCE flow
- Cached the resulting token in `~/.claude/.credentials.json` under
  `mcpOAuth`

You won't need to re-do this dance for that project unless the daemon
rotates its DCR registry (rare) or your refresh token expires.

---

## Step 4: First tool call

Ask Claude something simple to verify the wire:

> Use list_team_sessions to see who's online right now.

Expected: Claude reports zero or more sessions, one entry per active
teammate. Each row shows their `user_id`, `repo`, and `agent` name.
Yours is omitted by default (`include_self: false`).

Now try a write:

> Send a "hello from the new dev" message to user_id <pick one from above>.

Claude Code will prompt for permission the first time (unless you did
Step 2). Click **Allow once** or **Always allow for project**. The
message lands in the recipient's inbox; they'll see it next time
they call `check_messages`.

---

## Step 5: Patterns for daily use

Some prompts that work well once the tools are wired:

- **Morning stand-up**: *"Run get_recent_activity for the last 16
  hours."* — surfaces your unread messages + a per-repo headcount of
  who else is active.

- **Async question**: *"Send a message to <user_id> asking about the
  auth refactor — they were online in auth-service earlier."*

- **Code review**: *"Use request_review to ask <user_id> for review
  on my PR <url>, repo X, branch wip/Y. Include checklist: confirm
  role claims, check clock skew."* — composes a structured review
  request with the right `type` so the recipient sees it as a review,
  not chat.

- **Triaging your inbox**: *"Check my messages. For each review request,
  open the PR link and quickly assess. For each chat, summarize."*

---

## Troubleshooting

### `/mcp` shows `✘ failed`

Run with debug to see what failed:

```bash
claude --debug mcp --debug-file /tmp/cc-otaman-debug.log
```

Common causes:

- **Bridge URL unreachable**: `curl -fsS https://otaman.your-team.example/.well-known/oauth-protected-resource` should return JSON. If 502, the bridge daemon is down; ping your admin. If you can't even resolve DNS, you may not be on the right network.

- **Cached stale OAuth state**: if you saw `Got new credentials, but
  ... rejected them on reconnect`, your cached token doesn't match the
  current bridge state (Zitadel was rebuilt, etc.). Clear it:

  ```bash
  python3 - <<'PY'
  import json, pathlib
  p = pathlib.Path.home() / '.claude' / '.credentials.json'
  d = json.loads(p.read_text())
  d['mcpOAuth'] = {k: v for k, v in d.get('mcpOAuth', {}).items()
                   if not k.startswith('otaman-bridge|')}
  p.write_text(json.dumps(d))
  PY
  ```

  Then `/mcp` => Re-authenticate.

- **Claude Code shows `Auth: ✔ authenticated` but `Status: △ needs
  authentication`**: pick "Re-authenticate" — same recovery as above.

### `kill_session_for_user` returns "requires the 'otaman:admin' role"

Working as designed. You're a developer, not an admin. Ask whoever
provisioned your account to grant `otaman:admin` if you genuinely
need this.

### `list_team_sessions` returns empty

Either no one else is in an active session, OR the runner's session
registry doesn't have entries for your team yet. The runner picks up
session records when each developer's Claude Code starts in an
otaman-managed project (the launcher tells the runner). If you're the
first dev on the team, you'll see one session: yours, only visible to
others (not yourself, since `include_self` defaults to false).

### `check_messages` returns empty even though someone sent me one

Check the recipient `user_id` they sent to. If they used a stale or
wrong `user_id`, the message went somewhere else. Confirm yours with:

```
Use list_team_sessions with include_self=true. My session row tells me my user_id.
```

---

## What's next

- [MCP tools reference](../reference/mcp-tools.md#otaman-bridge-7-tools) — full schema for each tool.
- [Cloudflare Tunnel deployment](cloudflare-tunnel.md) — if you're also setting up the bridge.
- [Team-mode auth architecture](../architecture/team-mode-auth.md) — the DCR shim, two-layer auth, and PAT-vs-JWT design.
