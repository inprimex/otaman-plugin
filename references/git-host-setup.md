# Git host integration setup

Otaman ships with provider-neutral PR/MR support: agents can read PRs,
post comments, and append observer-review artifacts as PR comments. To
enable, you give otaman a fine-grained PAT scoped only to the repos in
your project.

**Supported providers:** GitHub (SaaS + Enterprise), GitLab (SaaS +
self-hosted), Bitbucket Cloud, Azure DevOps.

This page covers token creation per provider. Steps after token creation
are identical:

1. Add `git_host:` block to `platform.yaml` (template at the bottom)
2. Store the token in the `_secrets` chain (env / dotenv / keyring)
3. Verify with `otaman doctor` — should report "Git Host PAT: ok"

---

## GitHub (SaaS — github.com)

**Recommended: fine-grained PAT** (per-repo scoping, easier to audit
than classic PATs).

1. Go to https://github.com/settings/personal-access-tokens
2. Click **Generate new token** → **Fine-grained tokens**
3. Name: `otaman-<project>` (e.g., `otaman-myapp`)
4. Expiration: pick a defensible duration (90 days is a sensible default)
5. Resource owner: your user or org (org tokens may need owner approval)
6. Repository access: **Only select repositories** → pick the ones in
   your project's `platform.yaml`
7. Permissions → **Repository permissions**:
   - **Contents: Read-only** (required for `otaman git-host pr list`)
   - **Pull requests: Read and write** (required for `otaman git-host
     pr comment` and `otaman git-host post-review`)
   - **Metadata: Read-only** (automatic)
8. Generate. Copy the token (starts with `github_pat_`).

**Classic PAT fallback** (if your org doesn't allow fine-grained tokens):
- https://github.com/settings/tokens
- New token (classic) with scopes: `repo` (full control)
- Classic PATs grant access to ALL your repos — less safe, prefer
  fine-grained.

---

## GitHub Enterprise (self-hosted)

Same steps as GitHub SaaS but at your enterprise URL:
- https://github.example.com/settings/personal-access-tokens

Add `git_host.base_url` to `platform.yaml`:

```yaml
git_host:
  provider: github
  base_url: "https://github.example.com"
  token:
    sources:
      - { type: keyring, service: otaman, account: gh-pat-myapp }
```

---

## GitLab (SaaS — gitlab.com)

1. Go to https://gitlab.com/-/user_settings/personal_access_tokens
2. Token name: `otaman-<project>`
3. Expiration: 90 days
4. **Scopes:**
   - `read_api` (read PRs, comments, project metadata)
   - `read_repository`
   - `api` (only if you need to write comments — preferred:
     `write_repository` for narrower scope, but for MR comments you'll
     need `api`)
5. Create. Copy the token (starts with `glpat-`).

**Self-hosted GitLab:** same steps at your instance URL:
- https://gitlab.example.com/-/user_settings/personal_access_tokens
- Add `base_url` to `git_host:` block.

---

## Bitbucket Cloud

Bitbucket Cloud uses **app passwords**, not PATs. Different mechanism
but conceptually similar.

1. Click your avatar (bottom-left) → **Personal settings**
2. Under "Access management" → **App passwords**
3. Create new app password. Label: `otaman-<project>`
4. **Permissions:**
   - Account → Read
   - Workspace membership → Read
   - Projects → Read (Read and write if you need to update PRs)
   - Pull requests → Read and write
   - Repositories → Read
5. Create. The dialog shows your username + the app password — copy
   both.

In otaman config:

```yaml
git_host:
  provider: bitbucket
  workspace: "your-workspace-slug"
  username: "your-bitbucket-username"
  token:
    sources:
      - { type: keyring, service: otaman, account: bb-app-myapp }
```

Bitbucket auth is `username:app_password` (HTTP Basic) — both fields are
needed. The `username` lives in YAML; the app password goes in the
secrets chain.

---

## Azure DevOps

1. In Azure DevOps, click your profile (top-right) → **Personal access
   tokens**
2. **New Token**. Name: `otaman-<project>`
3. Organization: pick the org containing your project
4. Expiration: 90 days
5. **Scopes** — click **Custom defined**:
   - **Code** → Read & write (write needed for PR comments)
   - **Pull Request Threads** → Read & write
6. Create. Copy the token (long base64-ish string).

In otaman config:

```yaml
git_host:
  provider: azure-devops
  organization: "your-org"
  project: "your-project"
  token:
    sources:
      - { type: keyring, service: otaman, account: ado-pat-myapp }
```

Azure DevOps uses **Basic auth with the PAT as the password** (and any
non-empty string as the username — convention is "" or "user"). Otaman
handles this internally; just provide the token.

---

## Store the token securely

The same three-tier `_secrets` chain applies to all providers:

```yaml
git_host:
  token:
    sources:
      - { type: env,     name: OTAMAN_GH_PAT_MYAPP }       # checked first
      - { type: dotenv,  name: OTAMAN_GH_PAT_MYAPP }       # then .otaman/secrets.env
      - { type: keyring, service: otaman, account: gh-pat-myapp }  # then OS keyring
```

For everyday local dev, **keyring is the safest** (encrypted at rest).
Set with:

```bash
python3 -c "
import keyring
keyring.set_password('otaman', 'gh-pat-myapp', 'PASTE-TOKEN-HERE')
"
```

For CI, use the env var pattern (CI secrets injected as env).

For dotenv, put `OTAMAN_GH_PAT_MYAPP=<token>` in `.otaman/secrets.env`
and ensure that path is in your `.gitignore` (otaman init covers this
automatically — verify with `otaman doctor`).

---

## Verify

```bash
otaman doctor
```

The **Git Host PAT** row should report:

```
[OK] Git Host PAT (github, authenticated as <your-username>, scopes: contents:read, pull_requests:write)
```

If you see `[FAIL] Token validation failed: 401 Unauthorized` — the
token is wrong or revoked. Re-create and re-store.

If you see `[FAIL] Token scopes insufficient` — re-create the token
with the scopes listed above.

If `git_host:` is missing from `platform.yaml`, the check is skipped (no
PR support; still fine for basic otaman usage).

---

## Try it

```bash
# List open PRs on the current repo's git remote
otaman git-host pr list

# Fetch one PR's details
otaman git-host pr get 42

# Find the PR linked to your current branch
otaman git-host pr for-branch

# Post a comment to a PR
otaman git-host pr comment 42 "LGTM after the migration test"

# Post a review artifact to the PR (after /otaman:review writes one)
otaman git-host post-review
```

---

## Where next

- `references/telegram-setup.md` — AFK approvals via Telegram
- `references/launcher-walkthrough.md` — terminal launcher with SSH/tmux
- `references/communication-protocol.md` — bus message schema

---

## Backlog notes

- Bitbucket Server (self-hosted Data Center) is not yet supported.
  Different REST base (`/rest/api/1.0`) from Bitbucket Cloud. Tracked
  in `otaman-meta/backlog.md` for a future commit.
- Inline / line-level review comments are not yet supported by the
  Protocol — only general PR comments. Inline support requires
  per-provider endpoint extensions. Backlog item.
