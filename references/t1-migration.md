# T1 Migration Guide — From Ad-hoc PowerShell Functions to Declarative Accounts

**Audience**: Existing otaman users on Windows who set up multi-account Claude access via hand-rolled PowerShell functions (`claude-personal`, `claude-riseapps`, etc.) before T1 shipped, plus Linux/macOS devs adopting multi-account isolation for the first time.

**Effort**: ~5 minutes per account. Fully reversible.

---

## 1. What T1 ships

Phase T1 of the Remote Approval Bridge replaces manual `CLAUDE_CONFIG_DIR` juggling with a declarative `accounts:` block in `launch-settings.yaml`. Effects:

- One source of truth for account → `CLAUDE_CONFIG_DIR` mapping, shared across PowerShell, bash, zsh, fish.
- Launchers (PowerShell + new bash) resolve the connection's account and set `CLAUDE_CONFIG_DIR` automatically.
- Optional shell alias generator emits `claude-<name>` functions compatible with the pre-T1 PowerShell workflow.
- `.otaman/secrets.env` + tiered secret resolution (env → dotenv → OS keychain) ready for T2's Telegram tokens.
- SessionStart hook warns when `CLAUDE_CONFIG_DIR` disagrees with the managed repo's `expected_account`.
- `otaman doctor` now grep-checks git history for accidentally committed secrets.

Nothing about your existing Claude auth, `~/.claude-*` directories, or otaman folder layout changes. T1 is a *wrapper upgrade*, not a data migration.

---

## 2. Before → after at a glance

**Before (per-user `$PROFILE`):**

```powershell
function claude-personal {
    $env:CLAUDE_CONFIG_DIR = "$HOME\.claude-personal"
    claude @args
}
function claude-riseapps {
    $env:CLAUDE_CONFIG_DIR = "$HOME\.claude-riseapps"
    claude @args
}
```

**After (per-otaman-folder `launch-settings.yaml`):**

```yaml
accounts:
  personal:
    config_dir: "~/.claude-personal"
    label: "Personal (max)"
  riseapps:
    config_dir: "~/.claude-riseapps"
    label: "Riseapps (corp)"

active_connection: local
connections:
  local:
    type: local
    local_shell: wsl
    account: personal       # NEW — which account this connection uses
  lan:
    type: ssh
    ssh_default_host: user@1.2.3.4
    account: riseapps       # NEW
```

Optionally, regenerate shell functions with the same names from the same source:

```bash
otaman accounts install-shell-aliases --shell powershell
```

---

## 3. Step-by-step migration

### 3.1 Register each account

From inside your otaman folder (where `platform.yaml` lives):

```bash
otaman accounts add personal --config-dir "~/.claude-personal" --label "Personal (max)"
otaman accounts add riseapps --config-dir "~/.claude-riseapps" --label "Riseapps (corp)"
otaman accounts list
```

Output:

```
NAME      CONFIG_DIR          LABEL            USED BY
--------  ------------------  ---------------  -------
personal  ~/.claude-personal  Personal (max)   -
riseapps  ~/.claude-riseapps  Riseapps (corp)  -
```

### 3.2 Wire each connection to its account

Edit `launch-settings.yaml` and add `account:` under the relevant connection(s):

```yaml
connections:
  local:
    type: local
    local_shell: wsl
    account: personal
  lan:
    type: ssh
    ssh_default_host: user@host
    account: riseapps
```

The launcher (`launch-agents.ps1` and `launch-agents.sh`) automatically exports `CLAUDE_CONFIG_DIR=<account.config_dir>` when it fires up each terminal tab.

### 3.3 (Optional) Regenerate shell functions

If you relied on `claude-personal` / `claude-riseapps` in bare shell prompts (outside the launcher), regenerate them from the single source:

```bash
otaman accounts install-shell-aliases                   # auto-detects your shell
otaman accounts install-shell-aliases --shell powershell
otaman accounts install-shell-aliases --shell zsh
```

The generated block is bracketed with `# BEGIN MAESTRO ACCOUNTS` / `# END MAESTRO ACCOUNTS` so re-running is idempotent. You can safely delete the old hand-rolled functions from `$PROFILE` / `~/.bashrc` / `~/.zshrc` — everything between the markers is regenerated.

### 3.4 (Optional) Stamp `expected_account` into managed repos

If you want the SessionStart hook to warn when a repo is opened under the wrong account, add to `platform.yaml`:

```yaml
project: my-project
account: riseapps          # NEW — the expected account for this project
```

Then re-run `otaman init` to stamp `expected_account:` into each repo's `.otaman` marker. The hook compares `$CLAUDE_CONFIG_DIR` basename to the expected value and prints a warning (never blocks) on mismatch.

### 3.5 Verify

```bash
otaman doctor
otaman accounts list
otaman launcher --dry-run           # PS launcher: preview first
./launch-agents.sh --dry-run         # bash launcher: preview first
```

Both launchers should now show the resolved account and `CLAUDE_CONFIG_DIR` in their pre-launch banner.

---

## 4. Secrets: use `.otaman/secrets.env` from day one

Even without Telegram (T2), you benefit from the new secrets infra. Any env var you'd otherwise set before `claude` (CI PAT, API key, debug flag) can live in:

```
.otaman/secrets.env       # gitignored, mode 0600 on POSIX
```

Format is standard `KEY=VALUE`. Comments (`#`) and surrounding quotes supported. The launchers source this file into every spawned session, *after* process-env (so process-env always wins).

A `.otaman/secrets.env.example` stub is committed to git by `otaman init` — put expected keys there so team members know what to copy.

Check for leaks any time with:

```bash
otaman doctor
```

It scans your git history for any accidentally-committed `secrets.env` and flags critical severity with remediation (git-filter-repo hint).

---

## 5. Rollback

T1 is additive. Nothing in your pre-T1 setup is deleted unless you delete it.

- The old `$PROFILE` functions keep working alongside the new aliases if you leave them alone.
- To remove the T1 block in your rc file: delete everything between `# BEGIN MAESTRO ACCOUNTS` and `# END MAESTRO ACCOUNTS`.
- To remove accounts from the project: `otaman accounts remove <name>` (refuses if any connection references it; pass `--force` to override).
- To disable the SessionStart account-mismatch warning: remove `account:` from `platform.yaml` and re-run `otaman init`.

No state lives outside these files. `git checkout` rolls the whole thing back.

---

## 6. Cross-platform notes

| Shell | CLAUDE_CONFIG_DIR expansion | Aliases target | Launcher |
|---|---|---|---|
| PowerShell (Windows) | `C:\Users\<you>\.claude-<name>` | `$HOME\Documents\PowerShell\Profile.ps1` | `launch-agents.ps1` |
| bash (Linux, macOS, WSL) | `$HOME/.claude-<name>` | `~/.bashrc` | `launch-agents.sh` |
| zsh (macOS, Linux) | `$HOME/.claude-<name>` | `~/.zshrc` | `launch-agents.sh` |
| fish | `$HOME/.claude-<name>` | `~/.config/fish/config.fish` | `launch-agents.sh` |
| SSH targets | deferred to remote shell | — | both launchers |
| WSL (from PS launcher) | deferred to WSL's `$HOME` | — | `launch-agents.ps1` |

Key subtlety: on a Windows host, PowerShell's `~/.claude-personal` and WSL's `~/.claude-personal` are **two different directories** by design. Each keeps its own Claude auth. If you want one shared auth, opt-in symlink WSL's `~/.claude-personal` → `/mnt/c/Users/<you>/.claude-personal` manually. Default = independent.

---

## 7. What T1 does *not* do (coming in T2+)

- Telegram bridge for remote approval from your phone (T2).
- Daemon + PreToolUse hook that routes permission prompts to chat (T2).
- `otaman afk` toggle (T2).
- Bus-message surfacing to chat (T2).
- Auto-AFK on SSH (T2).
- Cross-account broadcast, learned-pattern grooming (T1.5 / v1.5).

T1's scope is account isolation + secrets infrastructure. Every T2+ feature layers on top without touching the T1 schema — the abstractions were chosen so the Telegram bridge slots in with zero rework of the account config.
