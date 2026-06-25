#Requires -Version 5.1
<#
.SYNOPSIS
    Launch Claude Code agents for repos defined in platform.yaml
.DESCRIPTION
    Reads platform.yaml from the otaman folder, shows profile menu (or accepts
    -Profile param), opens Windows Terminal tabs (or PuTTY windows) for each repo.

    Supports multiple named connections (local / LAN / mesh) via launch-settings.yaml
    `connections:` block. Each connection has a type (local|ssh) and its own fields.
    `extends:` allows one connection to inherit fields from another.

.EXAMPLE
    .\launch-agents.ps1                              # interactive connection + profile menu
    .\launch-agents.ps1 -Connection lan              # use the "lan" connection
    .\launch-agents.ps1 -Connection mesh -Profile payments
    .\launch-agents.ps1 -Shell ssh -SshHost dev@srv  # override all to SSH (ad-hoc)
    .\launch-agents.ps1 -DryRun                      # preview without launching
    .\launch-agents.ps1 -Setup                       # manage connections
    .\launch-agents.ps1 -Pull                        # fetch remote platform.yaml back to local (SSH connections only)
#>

param(
    [string]$WorkDir = "",        # Project-specific working dir (keeps settings/config per project)
    [string]$ConfigFile = "platform.yaml",
    [string]$WslDistro = "",      # Override WSL distro (otherwise from connection or default Ubuntu)
    [string]$Profile = "",
    [string[]]$Filter = @(),
    [string]$Connection = "",     # Named connection from launch-settings.yaml (local/lan/mesh/...)
    [string]$Shell = "",
    [string]$SshHost = "",
    [string]$SshClient = "",      # Override: ssh | putty | plink | kitty | custom
    [switch]$DryRun,
    [switch]$Setup,               # Manage connections interactively
    [switch]$IncludeDisabled,     # Include repos with disabled:true in platform.yaml
    [switch]$Pull,                # Pull remote platform.yaml back to local (overwrites local copy; SSH connection required)
    [switch]$Close,               # Kill tmux sessions for selected repos (don't open tabs)
    [switch]$Restart,             # Kill then re-launch (combination of -Close + normal launch)
    [switch]$Yes,                 # Skip confirmation prompts (for -Close / -Restart automation)
    [switch]$ViaRunner,           # Deprecated no-op (runner is now the default in tmux mode per auto-session-spawn-implementation task 4.3). Kept for back-compat.
    [switch]$NoRunner             # Skip otaman-runner; spawn wt.exe tabs directly. Use when the runner daemon isn't installed or for offline dev.
)

# ============================================================
# Helpers
# ============================================================

function Write-Step { param($m) Write-Host "`n[$([char]0x25B6)] $m" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "  [OK] $m" -ForegroundColor Green }
function Write-Warn { param($m) Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Write-Err  { param($m) Write-Host "  [X]  $m" -ForegroundColor Red }

# ============================================================
# Otaman-runner client (companion to bash launcher's runner path per ADR-009)
# ============================================================
# Parses ~/.otaman/runner.endpoint and POSTs /spawn for each repo, mirroring
# scripts/launch-agents.sh:read_runner_endpoint / runner_spawn_one.
#
# Runner-first is the default in wt.exe tmux mode (auto-session-spawn-
# implementation task 4.3). Endpoint-missing or any /spawn failure falls back
# to the legacy wt.exe spawn path (laptop dev parity per spec-agent
# 20260522T205846). Pass -NoRunner to skip the runner entirely. Fallback is
# logged as `[degraded mode: runner unavailable; using local fallback]` so the
# user knows which spawn path actually ran.

function Read-RunnerEndpoint {
    $path = Join-Path $HOME ".otaman/runner.endpoint"
    if (-not (Test-Path $path)) { return $null }
    $host_ = $null; $port = $null; $token = $null
    foreach ($line in (Get-Content $path -Encoding UTF8)) {
        $kv = $line -split '=', 2
        if ($kv.Length -ne 2) { continue }
        switch ($kv[0].Trim()) {
            'host'  { $host_ = $kv[1].Trim() }
            'port'  { $port  = $kv[1].Trim() }
            'token' { $token = $kv[1].Trim() }
        }
    }
    if (-not $host_ -or -not $port -or -not $token) { return $null }
    return @{ Host = $host_; Port = $port; Token = $token }
}

function Invoke-RunnerSpawn {
    # POST /spawn against the runner daemon. Returns the attach_command on
    # success; throws on HTTP / payload error so the caller can catch and
    # trigger the local-fallback path.
    #
    # Body shape per auto-session-spawn-implementation proposal §4: agent +
    # repo + project_root + mode are required; account + human are forwarded
    # when set. `human` is the bridge-facing alias for `user` (drives the
    # session-registry dedup key per Q1 of auto-session-spawn-on-bus-events).
    param(
        [Parameter(Mandatory)] $Endpoint,
        [Parameter(Mandatory)][string] $Agent,
        [Parameter(Mandatory)][string] $Repo,
        [Parameter(Mandatory)][string] $ProjectRoot,
        [string] $Account = "",
        [string] $Human = ""
    )
    $body = @{
        agent        = $Agent
        repo         = $Repo
        project_root = $ProjectRoot
        mode         = "interactive"
        account      = if ($Account) { $Account } else { $null }
        human        = if ($Human)   { $Human }   else { $null }
    } | ConvertTo-Json -Compress
    $uri = "http://$($Endpoint.Host):$($Endpoint.Port)/spawn"
    $headers = @{ Authorization = "Bearer $($Endpoint.Token)"; "Content-Type" = "application/json" }
    $resp = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body -TimeoutSec 30
    if (-not $resp.attach -or -not $resp.attach.attach_command) {
        throw "no attach info in response: $($resp | ConvertTo-Json -Compress)"
    }
    return [string]$resp.attach.attach_command
}

# Size-based log rotation. Called before append-only writes so launcher.log
# (and any other trace logs we add later) stays bounded. No-op if the file
# doesn't exist or is under the threshold. Defaults: 1 MiB max, 3 backups.
# All ops are best-effort — rotation failures never break a launch.
function Rotate-Log {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [int]$MaxBytes = 1048576,
        [int]$Keep = 3
    )
    if (-not (Test-Path $Path)) { return }
    try {
        $size = (Get-Item $Path).Length
        if ($size -lt $MaxBytes) { return }
        # Drop the oldest, then shift each .N to .N+1, then base -> .1.
        $oldest = "$Path.$Keep"
        if (Test-Path $oldest) { Remove-Item -Force $oldest -ErrorAction SilentlyContinue }
        for ($i = $Keep - 1; $i -ge 1; $i--) {
            $src = "$Path.$i"
            $dst = "$Path.$($i + 1)"
            if (Test-Path $src) { Move-Item -Force $src $dst -ErrorAction SilentlyContinue }
        }
        Move-Item -Force $Path "$Path.1" -ErrorAction SilentlyContinue
    } catch {
        # Best-effort.
    }
}

# WorkDir isolates settings per project (each project gets its own folder)
if ($WorkDir) {
    if (-not (Test-Path $WorkDir)) { New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null }
    $ConfigFile = Join-Path $WorkDir $ConfigFile
}
$cfgParent = Split-Path $ConfigFile -Parent
if (-not $cfgParent) { $cfgParent = if ($WorkDir) { $WorkDir } else { Get-Location } }
$SettingsFile = Join-Path $cfgParent "launch-settings.yaml"

# ============================================================
# launch-settings.yaml parsing (named connections)
# ============================================================
#
# New format:
#   active_connection: lan
#   default_type: ssh                # optional — filters interactive picker
#   connections:
#     local:
#       type: local
#       local_root: C:/work/myproj/myproj-otaman
#       local_shell: wsl            # wsl | powershell
#     lan:
#       type: ssh
#       ssh_client: ssh
#       ssh_default_host: user@1.2.3.4
#       ssh_key: C:/path/to/key
#       ssh_remote_root: /home/user/proj/proj-otaman
#       ssh_plugin_path: /home/user/otaman/otaman-plugin
#     mesh:
#       type: ssh
#       extends: lan
#       ssh_default_host: user@100.64.0.1
#
# Legacy format (auto-wrapped into connections.default):
#   ssh_client: ssh
#   ssh_default_host: ...
#   ssh_key: ...

function Read-SettingsFile {
    if (-not (Test-Path $SettingsFile)) { return $null }
    $raw = Get-Content $SettingsFile -Raw -ErrorAction SilentlyContinue
    if (-not $raw) { return $null }

    $top = @{}            # top-level k/v (active_connection, legacy ssh_*)
    $connections = [ordered]@{}
    $accounts = [ordered]@{}
    $section = ""         # "" | "connections" | "accounts"
    $currentConn = $null
    $currentAcct = $null

    foreach ($line in ($raw -split "`r?`n")) {
        if ($line -match '^\s*#') { continue }
        if ($line -match '^\s*$') { continue }

        # Top-level key (no indent). Matches `key: value` or `key:` (section header)
        if ($line -match '^([a-zA-Z_][\w-]*):\s*(.*)$') {
            $key = $Matches[1]
            $val = $Matches[2].Trim()
            if ($key -eq 'connections') {
                $section = 'connections'
                $currentConn = $null
                $currentAcct = $null
                continue
            }
            if ($key -eq 'accounts') {
                $section = 'accounts'
                $currentConn = $null
                $currentAcct = $null
                continue
            }
            $section = ''
            $currentConn = $null
            $currentAcct = $null
            if ($val) { $top[$key] = $val.Trim('"').Trim("'") }
            continue
        }

        # 2-space indent under `connections:` — connection name
        if ($section -eq 'connections' -and $line -match '^\s{2}([a-zA-Z_][\w-]*):\s*$') {
            $currentConn = $Matches[1]
            $connections[$currentConn] = [ordered]@{}
            continue
        }

        # 4-space indent under a connection — field
        if ($section -eq 'connections' -and $currentConn -and $line -match '^\s{4}([a-zA-Z_][\w-]*):\s*(.*)$') {
            $k = $Matches[1]
            $v = $Matches[2].Trim().Trim('"').Trim("'")
            $connections[$currentConn][$k] = $v
            continue
        }

        # 2-space indent under `accounts:` — account name
        if ($section -eq 'accounts' -and $line -match '^\s{2}([a-zA-Z_][\w-]*):\s*$') {
            $currentAcct = $Matches[1]
            $accounts[$currentAcct] = [ordered]@{}
            continue
        }

        # 4-space indent under an account — field
        if ($section -eq 'accounts' -and $currentAcct -and $line -match '^\s{4}([a-zA-Z_][\w-]*):\s*(.*)$') {
            $k = $Matches[1]
            $v = $Matches[2].Trim().Trim('"').Trim("'")
            $accounts[$currentAcct][$k] = $v
            continue
        }
    }

    # Legacy format migration: no `connections:` block, top-level has ssh_*
    if ($connections.Count -eq 0) {
        $legacyKeys = @($top.Keys | Where-Object { $_ -like 'ssh_*' -or $_ -eq 'ssh_client' })
        if ($legacyKeys.Count -gt 0) {
            $default = [ordered]@{ type = 'ssh' }
            foreach ($k in $legacyKeys) { $default[$k] = $top[$k] }
            $connections['default'] = $default
            if (-not $top.ContainsKey('active_connection')) { $top['active_connection'] = 'default' }
        }
    }

    return @{
        Top = $top
        Connections = $connections
        Accounts = $accounts
    }
}

function Save-SettingsFile {
    param($Top, $Connections)
    $lines = @()
    $lines += "# Otaman launch settings (auto-generated, edit freely)"
    $lines += "# Re-run setup: .\launch-agents.ps1 -Setup"
    $lines += ""
    if ($Top['active_connection']) {
        $lines += "active_connection: `"$($Top['active_connection'])`""
        $lines += ""
    }
    $lines += "connections:"
    foreach ($name in $Connections.Keys) {
        $lines += "  ${name}:"
        $conn = $Connections[$name]
        foreach ($k in $conn.Keys) {
            $v = $conn[$k]
            # Preserve empty values as empty string so user sees the key exists
            $lines += "    ${k}: `"$v`""
        }
        $lines += ""
    }
    $lines | Set-Content $SettingsFile -Encoding UTF8
}

# Expand an accounts.config_dir value for a target shell.
# Mirrors scripts/_resolve.py :: expand_config_dir.
#   - powershell/pwsh/cmd: expand ~ to $HOME, convert slashes to backslashes
#   - wsl/ssh:             pass through (target shell resolves)
#   - bash/zsh/fish:       expand ~ to $HOME, POSIX slashes
function Expand-ConfigDir {
    param(
        [Parameter(Mandatory)][string]$ConfigDir,
        [Parameter(Mandatory)][string]$Shell,
        [string]$HomeOverride = ""
    )
    if (-not $ConfigDir) { return "" }

    $s = $ConfigDir -replace '\\', '/'

    if ($Shell -in @('wsl','ssh')) {
        # POSIX shells: convert leading "~/" to "$HOME/" so the *remote*
        # shell expands it at runtime.
        #
        # Quoting is layered: the env-prefix string ultimately rides
        # through PowerShell's Invoke-Expression on the wt.exe call
        # (line ~1346), which re-evaluates every $variable in the
        # whole command string. A bare `$HOME` would get expanded to
        # the Windows USERPROFILE there (e.g. `C:\Users\Roman`) — the
        # exact bug Roman saw: CLAUDE_CONFIG_DIR ended up as
        # `C:UsersRoman/.claude` (backslashes munged by the SSH
        # round-trip) and every tab landed on a different broken path.
        #
        # The single-quoted ` ``$HOME ` literal in PS source is the
        # 6-char string [`,$,H,O,M,E]. When that value is interpolated
        # into a PS string and later parsed by Invoke-Expression, the
        # backtick is consumed as an escape so the literal text `$HOME`
        # reaches wt.exe → ssh → bash. Bash then expands it normally.
        # Build-EnvPrefix's `match '\$'` still picks this up and emits
        # the export unquoted, which is what bash needs.
        if ($s -eq '~') { return '`$HOME' }
        if ($s.StartsWith('~/')) { return '`$HOME/' + $s.Substring(2) }
        return $s
    }

    $resolvedHome = if ($HomeOverride) { $HomeOverride }
                    elseif ($env:USERPROFILE) { $env:USERPROFILE }
                    elseif ($env:HOME) { $env:HOME }
                    else { $HOME }
    $resolvedHome = $resolvedHome -replace '\\', '/'

    foreach ($token in @('${HOME}','$HOME','${USERPROFILE}','$USERPROFILE')) {
        $s = $s.Replace($token, $resolvedHome)
    }
    if ($s -eq '~') {
        $s = $resolvedHome
    } elseif ($s.StartsWith('~/')) {
        $s = "$resolvedHome/$($s.Substring(2))"
    }

    if ($Shell -in @('powershell','pwsh','cmd')) {
        return ($s -replace '/', '\')
    }
    return ($s -replace '\\', '/')
}

# Given a connection and the accounts map, return the account hashtable
# referenced by connection.account (empty hashtable if no account).
function Get-AccountForConnection {
    param($Accounts, $Connection)
    if (-not $Connection) { return @{} }
    $acctName = $Connection['account']
    if (-not $acctName) { return @{} }
    if (-not $Accounts -or -not $Accounts.Contains($acctName)) {
        Write-Warn "connection references unknown account '$acctName'"
        return @{}
    }
    $acct = $Accounts[$acctName]
    # Stamp the name onto the returned hash so callers can log it.
    $result = [ordered]@{ name = $acctName }
    foreach ($k in $acct.Keys) { $result[$k] = $acct[$k] }
    return $result
}

# Read secrets.env from the otaman folder. Returns an ordered hashtable
# of KEY=VALUE pairs (empty if absent). Comments / blank lines ignored;
# matching surrounding quotes stripped.
#
# Path resolution (M-1 migration): prefer .otaman/secrets.env; fall back
# to .maestro/secrets.env if the new path doesn't exist. This lets  # legacy: .maestro/secrets.env fallback
# already-migrated projects use the modern layout without breaking older
# deployments that still write to .maestro/.  # legacy: .maestro/ directory
# Resolve the session model/effort tier for a given repo by shelling out
# to scripts/launch-resolve.py. Walks platform.yaml's `models:` chain
# (by_repo → by_agent → default). Returns @{Model=<alias>; Effort=<level>}
# with empty strings when nothing matched.
function Get-ResolvedTierForRepo {
    param(
        [Parameter(Mandatory)][string]$MaestroRoot,
        [string]$Repo = ""
    )
    $result = @{ Model = ""; Effort = "" }
    $pluginDir = Split-Path $PSScriptRoot -Parent
    $resolverPy = Join-Path $PSScriptRoot "launch-resolve.py"
    if (-not (Test-Path $resolverPy)) { return $result }

    # Find a Python interpreter; give up silently if none.
    $py = $null
    foreach ($cand in @("py", "python3", "python")) {
        if (Get-Command $cand -ErrorAction SilentlyContinue) { $py = $cand; break }
    }
    if (-not $py) { return $result }

    $pyArgs = @($resolverPy, "--otaman-root", $MaestroRoot, "--shell", "bash")
    if ($Repo) { $pyArgs += @("--repo", $Repo) }

    try {
        $out = & $py @pyArgs 2>$null
        if ($LASTEXITCODE -ne 0) { return $result }
    } catch {
        return $result
    }

    foreach ($line in ($out -split "`r?`n")) {
        if ($line -match "^export ANTHROPIC_MODEL='([^']+)'") {
            $result.Model = $Matches[1]
        } elseif ($line -match "^export CLAUDE_CODE_EFFORT_LEVEL='([^']+)'") {
            $result.Effort = $Matches[1]
        }
    }
    return $result
}

function Get-MaestroSecretsEnv {
    param([string]$MaestroRoot)
    $result = [ordered]@{}
    if (-not $MaestroRoot) { return $result }
    # M-1: prefer .otaman/secrets.env, fall back to .maestro/secrets.env.  # legacy: .maestro/secrets.env path
    $path = Join-Path $MaestroRoot ".otaman/secrets.env"
    if (-not (Test-Path $path)) {
        $legacy = Join-Path $MaestroRoot ".maestro/secrets.env"  # legacy: .maestro/secrets.env path
        if (Test-Path $legacy) { $path = $legacy } else { return $result }
    }
    foreach ($line in (Get-Content $path -Encoding UTF8 -ErrorAction SilentlyContinue)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $eq = $trimmed.IndexOf('=')
        if ($eq -lt 1) { continue }
        $k = $trimmed.Substring(0, $eq).Trim()
        $v = $trimmed.Substring($eq + 1).Trim()
        if ($v.Length -ge 2) {
            $first = $v[0]; $last = $v[$v.Length - 1]
            if ( ($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'") ) {
                $v = $v.Substring(1, $v.Length - 2)
            }
        }
        if ($k) { $result[$k] = $v }
    }
    return $result
}

# Build a shell-appropriate env-prefix that sets CLAUDE_CONFIG_DIR and any
# secrets.env vars (from .otaman/ or .maestro/) BEFORE the claude  # legacy: .maestro/ directory
# command runs.
#
# Returns a string that can be prepended (with the shell's chain operator)
# to the session's command list. Empty string if no env to inject.
#
# $Shell: wsl | powershell | ssh | bash | zsh | fish
function Build-EnvPrefix {
    param(
        [Parameter(Mandatory)][string]$Shell,
        [string]$ConfigDirExpanded,
        $SecretsEnv,  # ordered hashtable or $null
        [string]$Model = "",    # ANTHROPIC_MODEL (session default tier)
        [string]$Effort = "",   # CLAUDE_CODE_EFFORT_LEVEL
        [bool]$Unattended = $false, # connection flagged `unattended: true`
        [string]$Account = ""       # account name (e.g. "personal" / "greenbin")  # legacy: maestro account name
    )
    $pairs = [ordered]@{}
    if ($ConfigDirExpanded) { $pairs['CLAUDE_CONFIG_DIR'] = $ConfigDirExpanded }
    # Routing identity: exported so PreToolUse hook + check-routing.sh pick
    # the right daemon/group even when multiple accounts share a single
    # CLAUDE_CONFIG_DIR (the "one login per subscription, many Telegram
    # groups" shape). otaman_core/_resolve checks OTAMAN_ACTIVE_ROUTING
    # first, falling back through OTAMAN_ACTIVE_ACCOUNT and
    # MAESTRO_ACTIVE_ACCOUNT. We export all three so any consumer
    # (current or legacy, on this server or a colleague's) finds what it
    # expects. MAESTRO_ACTIVE_ACCOUNT will be removed once nothing reads it.
    if ($Account) {
        $pairs['OTAMAN_ACTIVE_ROUTING'] = $Account   # preferred
        $pairs['OTAMAN_ACTIVE_ACCOUNT'] = $Account   # otaman-era legacy
        $pairs['MAESTRO_ACTIVE_ACCOUNT'] = $Account  # pre-rebrand legacy
    }
    if ($Model)             { $pairs['ANTHROPIC_MODEL'] = $Model }
    if ($Effort)            { $pairs['CLAUDE_CODE_EFFORT_LEVEL'] = $Effort }
    # Launcher-side SSH signal: the SessionStart hook (hooks/ssh-auto-afk.sh)
    # no longer triggers on SSH presence alone (that misfired when the human
    # was actively launching tabs), but we still export OTAMAN_LAUNCHER_SSH=1
    # for diagnostics — it shows up in ssh-auto-afk.log so "why didn't my
    # hook fire?" is easy to debug. MAESTRO_LAUNCHER_SSH kept as legacy alias.
    if ($Shell -eq 'ssh') {
        $pairs['OTAMAN_LAUNCHER_SSH'] = '1'
        $pairs['MAESTRO_LAUNCHER_SSH'] = '1'   # legacy
    }
    # Explicit "this session is unattended" signal — only set when the user
    # opts in via ``unattended: true`` on the connection in launch-settings.yaml.
    # This is the ONLY thing the SessionStart hook listens to for auto-AFK now.
    if ($Unattended) {
        $pairs['OTAMAN_UNATTENDED'] = '1'
        $pairs['MAESTRO_UNATTENDED'] = '1'   # legacy
    }
    if ($SecretsEnv) {
        foreach ($k in $SecretsEnv.Keys) {
            # Don't override pairs already set (CLAUDE_CONFIG_DIR / model / effort win).
            if (-not $pairs.Contains($k)) { $pairs[$k] = $SecretsEnv[$k] }
        }
    }
    if ($pairs.Count -eq 0) { return "" }

    switch ($Shell) {
        'powershell' {
            $parts = @()
            foreach ($k in $pairs.Keys) {
                $val = $pairs[$k] -replace "'", "''"
                $parts += "Set-Item Env:$k -Value '$val'"
            }
            return ($parts -join '; ')
        }
        'pwsh' {
            $parts = @()
            foreach ($k in $pairs.Keys) {
                $val = $pairs[$k] -replace "'", "''"
                $parts += "Set-Item Env:$k -Value '$val'"
            }
            return ($parts -join '; ')
        }
        default {
            # bash / zsh / fish / wsl / ssh — POSIX exports.
            # Values containing `$` are emitted unquoted so the remote
            # shell expands variables ($HOME in CLAUDE_CONFIG_DIR is the
            # main case — see Expand-ConfigDir's ~/ handling). Other
            # values stay single-quoted so embedded apostrophes / spaces
            # are safe. Values are launcher-generated and never contain
            # shell metacharacters that need escaping in the unquoted
            # form, so this is safe today; revisit if user-supplied
            # secrets ever land in this list.
            $parts = @()
            foreach ($k in $pairs.Keys) {
                $rawVal = $pairs[$k]
                if ($rawVal -match '\$') {
                    $parts += "export $k=$rawVal"
                } else {
                    $val = $rawVal -replace "'", "'\''"
                    $parts += "export $k='$val'"
                }
            }
            return ($parts -join ' && ')
        }
    }
}

# Resolve `extends:` chain and return a flat hashtable of fields for a connection.
function Resolve-Connection {
    param($Connections, [string]$Name, [int]$Depth = 0)
    if ($Depth -gt 10) { throw "extends: cycle detected at '$Name'" }
    if (-not $Connections.Contains($Name)) { return $null }
    $conn = $Connections[$Name]

    $parent = $conn['extends']
    $resolved = @{}
    if ($parent) {
        $parentResolved = Resolve-Connection -Connections $Connections -Name $parent -Depth ($Depth + 1)
        if ($parentResolved) { foreach ($k in $parentResolved.Keys) { $resolved[$k] = $parentResolved[$k] } }
    }
    foreach ($k in $conn.Keys) {
        if ($k -eq 'extends') { continue }
        $resolved[$k] = $conn[$k]
    }
    return $resolved
}

function Show-ConnectionMenu {
    param($Connections, [string]$Default)
    Write-Host "`n  Available connections:" -ForegroundColor White; Write-Host ""
    $names = @($Connections.Keys)
    for ($i = 0; $i -lt $names.Count; $i++) {
        $c = $Connections[$names[$i]]
        $type = if ($c['type']) { $c['type'] } else { 'ssh' }
        $suffix = ""
        if ($type -eq 'ssh' -or $type -eq 'mesh') {
            $h = $c['ssh_default_host']
            if (-not $h -and $c['extends']) {
                $resolved = Resolve-Connection -Connections $Connections -Name $names[$i]
                $h = $resolved['ssh_default_host']
            }
            if ($h) { $suffix = " [$h]" }
            $rel = $c['reliability']
            if (-not $rel -and $c['extends']) {
                $resolved = Resolve-Connection -Connections $Connections -Name $names[$i]
                $rel = $resolved['reliability']
            }
            if ($rel -and $rel -ne 'none') { $suffix += " ($rel)" }
        } elseif ($type -eq 'local') {
            $r = $c['local_root']
            if ($r) { $suffix = " [$r]" }
        }
        $mark = if ($names[$i] -eq $Default) { '*' } else { ' ' }
        Write-Host "    $mark $($i + 1). " -NoNewline -ForegroundColor Yellow
        Write-Host "$($names[$i])" -NoNewline -ForegroundColor Green
        Write-Host " ($type)" -NoNewline -ForegroundColor DarkGray
        Write-Host "$suffix" -ForegroundColor DarkGray
    }
    Write-Host ""
    $prompt = if ($Default) { "  Select connection (1-$($names.Count)) or name [default: $Default]" } `
                        else  { "  Select connection (1-$($names.Count)) or name" }
    $choice = Read-Host $prompt
    if (-not $choice -and $Default) { return $Default }
    if ($choice -match '^\d+$') {
        $idx = [int]$choice - 1
        if ($idx -ge 0 -and $idx -lt $names.Count) { return $names[$idx] }
    }
    if ($Connections.Contains($choice)) { return $choice }
    Write-Err "Invalid selection"
    return $null
}

# ============================================================
# -Setup wizard (multi-connection)
# ============================================================

function Prompt-ConnectionFields {
    param([string]$Type, $Existing)
    $fields = [ordered]@{ type = $Type }
    if ($Type -eq 'local') {
        $defRoot  = if ($Existing -and $Existing['local_root'])  { $Existing['local_root'] }  else { '' }
        $defShell = if ($Existing -and $Existing['local_shell']) { $Existing['local_shell'] } else { 'wsl' }
        $defDistro = if ($Existing -and $Existing['wsl_distro']) { $Existing['wsl_distro'] } else { 'Ubuntu' }

        $root = Read-Host "  Local otaman folder (absolute path, e.g., C:/work/myproj/myproj-otaman)$(if ($defRoot) { " [$defRoot]" })"
        if (-not $root -and $defRoot) { $root = $defRoot }
        $fields['local_root'] = $root

        $shell = Read-Host "  Local shell [wsl|powershell] [$defShell]"
        if (-not $shell) { $shell = $defShell }
        $fields['local_shell'] = $shell

        if ($shell -eq 'wsl') {
            $distro = Read-Host "  WSL distro [$defDistro]"
            if (-not $distro) { $distro = $defDistro }
            $fields['wsl_distro'] = $distro
        }
    } elseif ($Type -eq 'ssh' -or $Type -eq 'mesh') {
        # `ssh` and `mesh` use identical wire (SSH); `mesh` is just a label
        # that signals "this connection rides over a mesh VPN
        # (Tailscale/WireGuard/NetBird)" — useful documentation for the
        # operator and a hint that mosh works without firewall changes.
        $defHost   = if ($Existing -and $Existing['ssh_default_host'])  { $Existing['ssh_default_host'] }  else { '' }
        $defClient = if ($Existing -and $Existing['ssh_client'])        { $Existing['ssh_client'] }        else { 'ssh' }
        $defKey    = if ($Existing -and $Existing['ssh_key'])           { $Existing['ssh_key'] }           else { '' }
        $defRoot   = if ($Existing -and $Existing['ssh_remote_root'])   { $Existing['ssh_remote_root'] }   else { '' }
        $defPlugin = if ($Existing -and $Existing['ssh_plugin_path'])   { $Existing['ssh_plugin_path'] }   else { '' }
        $defReliab = if ($Existing -and $Existing['reliability'])       { $Existing['reliability'] }       else { 'none' }

        $client = Read-Host "  SSH client [ssh|plink|putty|kitty|custom] [$defClient]"
        if (-not $client) { $client = $defClient }
        $fields['ssh_client'] = $client

        $hst = Read-Host "  SSH host (e.g., user@1.2.3.4)$(if ($defHost) { " [$defHost]" })"
        if (-not $hst -and $defHost) { $hst = $defHost }
        $fields['ssh_default_host'] = $hst

        $key = Read-Host "  SSH private key (absolute path, blank for default)$(if ($defKey) { " [$defKey]" })"
        if (-not $key -and $defKey) { $key = $defKey }
        if ($key) { $fields['ssh_key'] = $key }

        $rroot = Read-Host "  Remote otaman folder (e.g., /home/user/proj/proj-otaman)$(if ($defRoot) { " [$defRoot]" })"
        if (-not $rroot -and $defRoot) { $rroot = $defRoot }
        if ($rroot) { $fields['ssh_remote_root'] = $rroot }

        $plugin = Read-Host "  Remote otaman-plugin path (e.g., /home/user/otaman/otaman-plugin)$(if ($defPlugin) { " [$defPlugin]" })"
        if (-not $plugin -and $defPlugin) { $plugin = $defPlugin }
        if ($plugin) { $fields['ssh_plugin_path'] = $plugin }

        if ($client -in @('putty','plink','kitty')) {
            $defSession = if ($Existing -and $Existing['ssh_session']) { $Existing['ssh_session'] } else { '' }
            $session = Read-Host "  PuTTY saved session name (blank for host-based)$(if ($defSession) { " [$defSession]" })"
            if (-not $session -and $defSession) { $session = $defSession }
            if ($session) { $fields['ssh_session'] = $session }
        }
        if ($client -eq 'custom') {
            $defT = if ($Existing -and $Existing['ssh_command_template']) { $Existing['ssh_command_template'] } else { '' }
            $tmpl = Read-Host "  Custom command template (placeholders: {host} {path} {commands})$(if ($defT) { " [$defT]" })"
            if (-not $tmpl -and $defT) { $tmpl = $defT }
            $fields['ssh_command_template'] = $tmpl
        }

        # Reliability mode — wraps each tab's inner command for resilience
        # against SSH drops. See references/connection-resilience.md.
        # User-visible strings stay ASCII so Windows PowerShell 5.1 (which
        # reads .ps1 files as Windows-1252 unless they have a UTF-8 BOM)
        # parses them cleanly.
        Write-Host "" -NoNewline
        Write-Host "  Connection resilience options:" -ForegroundColor DarkGray
        Write-Host "    none         -- bare SSH; lose in-flight session on drop" -ForegroundColor DarkGray
        Write-Host "    tmux         -- wrap in tmux session; reattach on drop (RECOMMENDED for remote work)" -ForegroundColor DarkGray
        Write-Host "    tmux+mosh    -- tmux + mosh client for auto-reconnect (needs mosh-server on remote, UDP 60000-61000)" -ForegroundColor DarkGray
        $reliab = Read-Host "  Reliability [none|tmux|tmux+mosh] [$defReliab]"
        if (-not $reliab) { $reliab = $defReliab }
        if ($reliab -notin @('none','tmux','tmux+mosh')) {
            Write-Warn "  Unknown reliability '$reliab' -- defaulting to 'none'"
            $reliab = 'none'
        }
        if ($reliab -ne 'none') { $fields['reliability'] = $reliab }
    }
    return $fields
}

function Run-Setup {
    $existing = Read-SettingsFile
    $top = if ($existing) { $existing.Top } else { @{} }
    $connections = if ($existing) { $existing.Connections } else { [ordered]@{} }

    while ($true) {
        Write-Host "`n  === Otaman launch-settings wizard ===" -ForegroundColor White
        Write-Host "  Settings file: $SettingsFile" -ForegroundColor DarkGray
        if ($connections.Count -eq 0) {
            Write-Host "  No connections configured yet." -ForegroundColor Yellow
        } else {
            Write-Host "  Configured connections:" -ForegroundColor White
            $names = @($connections.Keys)
            for ($i = 0; $i -lt $names.Count; $i++) {
                $n = $names[$i]
                $mark = if ($n -eq $top['active_connection']) { '*' } else { ' ' }
                $t = if ($connections[$n]['type']) { $connections[$n]['type'] } else { 'ssh' }
                $r = if ($connections[$n]['reliability']) { $connections[$n]['reliability'] } else { 'none' }
                $reliabSuffix = if ($t -in @('ssh','mesh') -and $r -ne 'none') { ", $r" } else { "" }
                Write-Host "    $mark $n ($t$reliabSuffix)" -ForegroundColor Gray
            }
        }
        Write-Host ""
        Write-Host "    1. Add connection" -ForegroundColor Yellow
        Write-Host "    2. Edit connection" -ForegroundColor Yellow
        Write-Host "    3. Remove connection" -ForegroundColor Yellow
        Write-Host "    4. Set active connection" -ForegroundColor Yellow
        Write-Host "    5. Save and exit" -ForegroundColor Green
        Write-Host "    6. Cancel (discard changes)" -ForegroundColor DarkGray
        Write-Host ""
        $choice = Read-Host "  Action (1-6)"

        switch ($choice) {
            '1' {
                $name = Read-Host "  Connection name (e.g., local, lan, mesh)"
                if (-not $name) { continue }
                if ($connections.Contains($name)) {
                    Write-Warn "Connection '$name' exists. Use option 2 to edit."
                    continue
                }
                $type = Read-Host "  Type [local|ssh|mesh] (default: ssh)"
                if (-not $type) { $type = 'ssh' }
                if ($type -notin @('local','ssh','mesh')) { Write-Err "Type must be local, ssh, or mesh"; continue }
                $fields = Prompt-ConnectionFields -Type $type -Existing $null
                $connections[$name] = [ordered]@{}
                foreach ($k in $fields.Keys) { $connections[$name][$k] = $fields[$k] }
                if (-not $top['active_connection']) { $top['active_connection'] = $name }
                Write-Ok "Added '$name'"
            }
            '2' {
                if ($connections.Count -eq 0) { Write-Warn "Nothing to edit"; continue }
                $name = Read-Host "  Connection name to edit"
                if (-not $connections.Contains($name)) { Write-Err "Not found"; continue }
                $type = if ($connections[$name]['type']) { $connections[$name]['type'] } else { 'ssh' }
                $fields = Prompt-ConnectionFields -Type $type -Existing $connections[$name]
                $existing_extends = $connections[$name]['extends']
                $connections[$name] = [ordered]@{}
                if ($existing_extends) { $connections[$name]['extends'] = $existing_extends }
                foreach ($k in $fields.Keys) { $connections[$name][$k] = $fields[$k] }
                Write-Ok "Updated '$name'"
            }
            '3' {
                $name = Read-Host "  Connection name to remove"
                if (-not $connections.Contains($name)) { Write-Err "Not found"; continue }
                $connections.Remove($name)
                if ($top['active_connection'] -eq $name) {
                    $top.Remove('active_connection')
                    $remaining = @($connections.Keys)
                    if ($remaining.Count -gt 0) { $top['active_connection'] = $remaining[0] }
                }
                Write-Ok "Removed '$name'"
            }
            '4' {
                if ($connections.Count -eq 0) { Write-Warn "No connections to choose from"; continue }
                $sel = Show-ConnectionMenu -Connections $connections -Default $top['active_connection']
                if ($sel) { $top['active_connection'] = $sel; Write-Ok "Active: $sel" }
            }
            '5' {
                Save-SettingsFile -Top $top -Connections $connections
                Write-Ok "Saved $SettingsFile"
                return @{ Top = $top; Connections = $connections }
            }
            '6' {
                Write-Warn "Changes discarded"
                return $existing
            }
            default { Write-Warn "Invalid choice" }
        }
    }
}

# ============================================================
# Load settings, pick active connection
# ============================================================

$settings = Read-SettingsFile
if ($Setup) {
    $settings = Run-Setup
    if (-not $settings) { exit 0 }
}

$activeConn = @{}       # flat hash of resolved connection fields (empty if none)
$activeName = ""

if ($settings) {
    $top = $settings.Top
    $connections = $settings.Connections

    # Pick connection: CLI param > active_connection from file > interactive menu > legacy flat
    $target = $Connection
    if (-not $target) { $target = $top['active_connection'] }

    if ($connections.Count -gt 0) {
        if (-not $target -or -not $connections.Contains($target)) {
            # default_type: when set, restrict the interactive picker to one
            # connection type ('local' / 'ssh' / 'mesh'). Falls back to the
            # full list if no connection matches the filter.
            $defaultType = $top['default_type']
            $menuConns = $connections
            if ($defaultType) {
                $filtered = [ordered]@{}
                foreach ($n in $connections.Keys) {
                    $t = if ($connections[$n]['type']) { $connections[$n]['type'] } else { 'ssh' }
                    if ($t -eq $defaultType) { $filtered[$n] = $connections[$n] }
                }
                if ($filtered.Count -gt 0) {
                    $menuConns = $filtered
                } else {
                    Write-Warn "default_type='$defaultType' matched no connections; showing all."
                }
            }
            if ($menuConns.Count -eq 1) {
                $target = @($menuConns.Keys)[0]
            } elseif (-not $Shell) {
                # Only prompt if user didn't pass -Shell override
                $target = Show-ConnectionMenu -Connections $menuConns -Default $top['active_connection']
                if (-not $target) { exit 1 }
            }
        }
        if ($target -and $connections.Contains($target)) {
            $activeConn = Resolve-Connection -Connections $connections -Name $target
            $activeName = $target
        }
    }
}

# CLI param overrides (apply on top of resolved connection)
if ($SshClient) { $activeConn['ssh_client'] = $SshClient }
if ($SshHost)   { $activeConn['ssh_default_host'] = $SshHost }

$connType = if ($activeConn['type']) { $activeConn['type'] } else { 'ssh' }

# ============================================================
# YAML Parser (platform.yaml)
# ============================================================

function Parse-PlatformYaml {
    param([string]$Path)

    # Force UTF-8 so non-ASCII characters in descriptions (em-dashes, Cyrillic) aren't mangled
    $lines = Get-Content $Path -Encoding UTF8 -ErrorAction Stop
    $repos = @()
    $profiles = @{}
    $inRepos = $false
    $inProfiles = $false
    $inLaunch = $false
    $inCommands = $false
    $inProfileRepos = $false
    $current = $null
    $currentProfile = $null

    foreach ($line in $lines) {
        $raw = $line.TrimEnd()

        if ($raw -eq 'repos:') {
            if ($current) { $repos += $current; $current = $null }
            $inRepos = $true; $inProfiles = $false; $inLaunch = $false; $inCommands = $false
            continue
        }
        if ($raw -eq 'profiles:') {
            if ($current) { $repos += $current; $current = $null }
            $inProfiles = $true; $inRepos = $false; $inLaunch = $false; $inCommands = $false
            continue
        }
        if ($raw.Length -gt 0 -and $raw[0] -match '[a-z]' -and -not $raw.StartsWith(' ') -and -not $raw.StartsWith('-')) {
            if ($inRepos -and $current) { $repos += $current; $current = $null }
            $inRepos = $false; $inProfiles = $false; $inLaunch = $false; $inCommands = $false; $inProfileRepos = $false
            continue
        }

        if ($inProfiles) {
            $t = $raw.Trim()
            if ($raw -match '^\s{2}(\w[\w-]*):\s*$') {
                $currentProfile = $Matches[1]
                $profiles[$currentProfile] = [PSCustomObject]@{ description = ""; repos = @() }
                $inProfileRepos = $false; continue
            }
            if ($null -ne $currentProfile) {
                if ($t -match '^description:\s*"?(.+?)"?\s*$') { $profiles[$currentProfile].description = $Matches[1] }
                if ($t -eq 'repos:') { $inProfileRepos = $true; continue }
                if ($t -match '^repos:\s+all\s*$') {
                    $profiles[$currentProfile].repos = 'all'
                    $inProfileRepos = $false; continue
                }
                if ($t -match '^repos:\s*\[(.+)\]') {
                    $profiles[$currentProfile].repos = $Matches[1] -split ',' | ForEach-Object { $_.Trim() }
                    $inProfileRepos = $false; continue
                }
                if ($inProfileRepos -and $t -match '^-\s+(.+)') { $profiles[$currentProfile].repos += $Matches[1].Trim(); continue }
            }
            continue
        }

        if (-not $inRepos) { continue }

        if ($raw -match '^-\s+name:\s*(.+)' -or $raw -match '^\s+-\s+name:\s*(.+)') {
            if ($current) { $repos += $current }
            $inLaunch = $false; $inCommands = $false
            $current = [PSCustomObject]@{
                name = $Matches[1].Trim(); path = ""; owner = ""; description = ""; disabled = $false
                launch_title = ""; launch_color = ""; launch_shell = ""
                launch_ssh_host = ""; launch_ssh_path = ""; launch_commands = @()
            }
            continue
        }
        if ($null -eq $current) { continue }
        $t = $raw.Trim()

        if ($t -eq 'launch:') { $inLaunch = $true; $inCommands = $false; continue }
        if ($inLaunch -and $raw -match '^\s{2}\w' -and $raw -notmatch '^\s{4}') { $inLaunch = $false; $inCommands = $false }
        if ($inLaunch -and $t -eq 'commands:') { $inCommands = $true; continue }
        if ($inCommands) {
            if ($t -match '^-\s+"(.+)"' -or $t -match "^-\s+'(.+)'" -or $t -match '^-\s+(.+)') {
                $val = $Matches[1].Trim()
                # Only strip matched outer quotes (not inner quotes)
                if ($val.Length -ge 2 -and $val[0] -eq '"' -and $val[-1] -eq '"') { $val = $val.Substring(1, $val.Length - 2) }
                elseif ($val.Length -ge 2 -and $val[0] -eq "'" -and $val[-1] -eq "'") { $val = $val.Substring(1, $val.Length - 2) }
                $current.launch_commands += $val; continue
            }
            if ($t -notmatch '^-') { $inCommands = $false }
        }
        if ($inLaunch) {
            if ($t -match '^title:\s*(.+)')    { $current.launch_title    = $Matches[1].Trim().Trim('"').Trim("'") }
            if ($t -match '^color:\s*(.+)')    { $current.launch_color    = $Matches[1].Trim().Trim('"').Trim("'") }
            if ($t -match '^shell:\s*(.+)')    { $current.launch_shell    = $Matches[1].Trim().Trim('"').Trim("'").ToLower() }
            if ($t -match '^ssh_host:\s*(.+)') { $current.launch_ssh_host = $Matches[1].Trim().Trim('"').Trim("'") }
            if ($t -match '^ssh_path:\s*(.+)') { $current.launch_ssh_path = $Matches[1].Trim().Trim('"').Trim("'") }
            continue
        }
        if ($t -match '^path:\s*(.+)')        { $current.path        = $Matches[1].Trim() }
        if ($t -match '^owner:\s*(.+)')       { $current.owner       = $Matches[1].Trim() }
        if ($t -match '^description:\s*(.+)') { $current.description = $Matches[1].Trim().Trim('"').Trim("'") }
        if ($t -match '^disabled:\s*(true|yes|1)\s*$') { $current.disabled = $true }
    }
    if ($current) { $repos += $current }
    return @{ repos = $repos; profiles = $profiles }
}

function ConvertTo-WslPath {
    param([string]$WinPath)
    $resolved = (Resolve-Path $WinPath -ErrorAction Stop).Path -replace '\\', '/'
    if ($resolved -match '^([A-Za-z]):(.*)') { return "/mnt/$($Matches[1].ToLower())$($Matches[2])" }
    return $resolved
}

function Is-AllRepos {
    param($ReposList)
    if ($ReposList -is [string] -and $ReposList -eq 'all') { return $true }
    if ($ReposList -is [array] -and $ReposList -contains 'all') { return $true }
    return $false
}

function Resolve-ProfileRepos {
    # Expands a profile's repos list into (activeNames, disabledNames) based on $AllRepos.
    # For `repos: all` → all repos in platform.yaml, split by disabled state.
    # For explicit list → preserves order, splits by disabled state.
    param($Profile, $AllRepos)
    $active = @()
    $disabled = @()
    $byName = @{}
    foreach ($r in $AllRepos) { $byName[$r.name] = $r }

    if (Is-AllRepos $Profile.repos) {
        foreach ($r in $AllRepos) {
            if ($r.disabled) { $disabled += $r.name } else { $active += $r.name }
        }
    } else {
        foreach ($n in $Profile.repos) {
            $r = $byName[$n]
            if ($null -eq $r) { $active += "$n(?)"; continue }   # unknown repo
            if ($r.disabled) { $disabled += $n } else { $active += $n }
        }
    }
    return @{ Active = $active; Disabled = $disabled }
}

function Show-ProfileMenu {
    param($Profiles, $AllRepos, [string]$ConnectionLabel = "")
    if ($ConnectionLabel) {
        Write-Host "`n  Connection: " -NoNewline -ForegroundColor DarkGray
        Write-Host $ConnectionLabel -NoNewline -ForegroundColor Cyan
        Write-Host "  (press 'c' to change)" -ForegroundColor DarkGray
    }
    Write-Host "`n  Available profiles:" -ForegroundColor White; Write-Host ""
    $names = @($Profiles.Keys | Sort-Object)
    for ($i = 0; $i -lt $names.Count; $i++) {
        $p = $Profiles[$names[$i]]
        $resolved = Resolve-ProfileRepos -Profile $p -AllRepos $AllRepos

        $countParts = @("$($resolved.Active.Count) active")
        if ($resolved.Disabled.Count -gt 0) { $countParts += "$($resolved.Disabled.Count) disabled" }
        $countLabel = $countParts -join ", "
        if (Is-AllRepos $p.repos) { $countLabel = "all - $countLabel" }

        Write-Host "    $($i + 1). " -NoNewline -ForegroundColor Yellow
        Write-Host "$($names[$i])" -NoNewline -ForegroundColor Green
        Write-Host " ($countLabel)" -NoNewline -ForegroundColor DarkGray
        if ($p.description) { Write-Host " - $($p.description)" -ForegroundColor DarkGray } else { Write-Host "" }

        # Repo list line(s). Truncate long lists to keep menu readable.
        $activeShown = if ($resolved.Active.Count -gt 8) {
            ($resolved.Active[0..6] -join ", ") + ", +" + ($resolved.Active.Count - 7) + " more"
        } else { $resolved.Active -join ", " }
        if ($activeShown) {
            Write-Host "         " -NoNewline
            Write-Host "$activeShown" -ForegroundColor Gray
        }
        if ($resolved.Disabled.Count -gt 0) {
            Write-Host "         skipped: " -NoNewline -ForegroundColor DarkGray
            Write-Host ($resolved.Disabled -join ", ") -ForegroundColor DarkGray
        }
    }
    # Add "pick" option for custom selection
    $pickIdx = $names.Count + 1
    Write-Host ""
    Write-Host "    $pickIdx. " -NoNewline -ForegroundColor Yellow
    Write-Host "pick" -NoNewline -ForegroundColor Cyan
    Write-Host " (choose individual repos)" -ForegroundColor DarkGray

    $promptSuffix = if ($ConnectionLabel) { " (or 'c' to change connection)" } else { "" }
    Write-Host ""; $choice = Read-Host "  Select profile (1-$pickIdx) or name$promptSuffix"
    if ($ConnectionLabel -and $choice -in @('c','C')) { $script:ChangeConnection = $true; return $null }
    if ($choice -match '^\d+$') {
        $idx = [int]$choice - 1
        if ($idx -eq $names.Count) { return "__pick__" }  # custom pick
        if ($idx -ge 0 -and $idx -lt $names.Count) { return $names[$idx] }
    }
    if ($choice -eq 'pick') { return "__pick__" }
    if ($Profiles.ContainsKey($choice)) { return $choice }
    Write-Err "Invalid selection"; return $null
}

function Show-RepoPicker {
    param($Repos, [string]$ConnectionLabel = "")
    if ($ConnectionLabel) {
        Write-Host "`n  Connection: " -NoNewline -ForegroundColor DarkGray
        Write-Host $ConnectionLabel -NoNewline -ForegroundColor Cyan
        Write-Host "  (press 'c' to change)" -ForegroundColor DarkGray
    }
    Write-Host "`n  Select repos to launch (comma-separated numbers):" -ForegroundColor White; Write-Host ""
    for ($i = 0; $i -lt $Repos.Count; $i++) {
        $r = $Repos[$i]
        $title = if ($r.launch_title) { $r.launch_title } else { $r.name }
        Write-Host "    $($i + 1). " -NoNewline -ForegroundColor Yellow
        Write-Host "$($r.name)" -NoNewline -ForegroundColor Green
        Write-Host " ($title)" -ForegroundColor DarkGray
    }
    Write-Host ""
    $promptSuffix = if ($ConnectionLabel) { " (or 'c' to change connection)" } else { "" }
    $input_ = Read-Host "  Enter numbers (e.g., 1,3,5 or 1-5 or all)$promptSuffix"
    if ($ConnectionLabel -and $input_ -in @('c','C')) { $script:ChangeConnection = $true; return @() }
    if ($input_ -eq 'all') { return $Repos }

    $selected = @()
    foreach ($part in ($input_ -split ',')) {
        $part = $part.Trim()
        if ($part -match '^(\d+)-(\d+)$') {
            $from = [int]$Matches[1] - 1
            $to = [int]$Matches[2] - 1
            for ($j = $from; $j -le $to -and $j -lt $Repos.Count; $j++) {
                if ($j -ge 0) { $selected += $Repos[$j] }
            }
        } elseif ($part -match '^\d+$') {
            $idx = [int]$part - 1
            if ($idx -ge 0 -and $idx -lt $Repos.Count) { $selected += $Repos[$idx] }
        }
    }
    return $selected
}

# ============================================================
# Path resolution for local connection
# ============================================================
# Resolves repo.path (relative, e.g., ../detectmod) against local_root.
# local_root is the absolute path to the otaman folder on local disk.  # legacy: maestro folder name

function Resolve-LocalPath {
    param([string]$LocalRoot, [string]$RepoPath)
    if (-not $LocalRoot) { return $RepoPath }
    if ([System.IO.Path]::IsPathRooted($RepoPath)) { return $RepoPath }
    # Combine local_root + repo.path (e.g., ../foo), then normalize
    $combined = Join-Path $LocalRoot $RepoPath
    try {
        # [IO.Path]::GetFullPath resolves .. segments without requiring the target to exist
        return [System.IO.Path]::GetFullPath($combined)
    } catch {
        return $combined
    }
}

# ============================================================
# SSH Command Builder (client-agnostic)
# ============================================================

# Sanitise a name for use as a tmux session label. tmux session names disallow
# dots and colons; we strip those and any other non-alphanumeric character to
# underscores so the same repo name resolves to the same session every launch.
function ConvertTo-TmuxSessionName {
    # WARNING: do NOT call this on a composite `<program>:<agent-name>` session
    # name — it strips the `:` separator. Per fix-launcher-tmux-session-naming
    # the new session-name format relies on the colon being preserved. Use this
    # function only on legacy single-token names (e.g., individual repo names)
    # or other non-session strings.
    param([string]$Name)
    if (-not $Name) { return "" }
    return ($Name -replace '[^A-Za-z0-9_-]', '_')
}

# Read the top-level ``project:`` field from platform.yaml. Used to namespace
# tmux session names so two projects on one host don't collide.
function Get-ProjectName {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return "" }
    $lines = Get-Content $Path -Encoding UTF8 -ErrorAction SilentlyContinue
    foreach ($line in $lines) {
        if ($line -match '^project:\s*"?([^"\s#]+)"?\s*(#.*)?$') {
            return $Matches[1].Trim()
        }
    }
    return ""
}

# Wrap an inner shell command for execution under tmux on the remote.
# Generates: tmux new -A -s '<session>' bash -c 'echo <BASE64> | base64 -d | bash -l'
# `-A` means "create OR attach" — relaunching the same tab from the launcher
# reattaches to the in-flight session if it already exists, which is exactly
# the recovery path after an SSH drop.
#
# Base64 sidesteps the multi-layer quoting hell. The original command may
# contain single quotes (`source ~/.nvm/nvm.sh && claude '/otaman:check'`),
# and the wrapper has to ride through:
#
#   1. PowerShell string interpolation
#   2. PowerShell Invoke-Expression re-parse
#   3. Windows Terminal (wt.exe) command-line parser
#   4. ssh.exe argv assembly
#   5. SSHd on the remote handing the command to /bin/sh -c
#   6. Tmux's command argument parsing
#   7. bash -c parsing of the inner command
#
# The classic POSIX `'"'"'` escape (close-quote / quoted-quote / reopen)
# breaks at layer 2: Invoke-Expression sees `\"` inside a `"..."` string
# and mangles it. Base64 output is `[A-Za-z0-9+/=]` only — none of those
# characters need escaping in any shell — so the wrapped string flows
# through every layer cleanly.
#
# Requires `base64` on the remote, which is part of GNU coreutils (Linux)
# and macOS base utilities. The remote shell stays bash -l for nvm/profile
# sourcing — same effect as the previous `bash -lc 'CMD'`.
function Wrap-WithTmux {
    param(
        [string]$SessionName,
        [string]$InnerCommand,
        [string]$WindowName = ""    # Per fix-launcher-tmux-session-naming task 2.5: window name = repo
    )
    # Build-EnvPrefix emits ``$HOME`` (backtick + $HOME) so PS
    # Invoke-Expression on the un-tmux'd path leaves a literal `$HOME` for
    # the remote bash to expand (commit 4b53d42). Base64 bypasses PS
    # interpolation entirely, so that backtick would arrive at the remote
    # AS-IS — and bash treats backtick as command substitution start, which
    # breaks the line. Strip the backtick before encoding; the resulting
    # `$HOME` is exactly what remote bash needs to see.
    $cleaned = $InnerCommand -replace '`\$', '$'
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($cleaned)
    $b64 = [Convert]::ToBase64String($bytes)

    # Tmux UX defaults applied at session creation time. These run as
    # separate bash statements chained with `&&` BEFORE `tmux new`, so
    # they take effect on the tmux server before the session starts.
    # `set -g` is server-wide; `-q` quiets warnings on tmux versions that
    # don't recognise an option (defensive, no-op on modern tmux).
    #
    # Why `&&` and not `;` — wt.exe (Windows Terminal) treats `;` as its
    # OWN command/tab separator. A `;` inside the quoted SSH command
    # makes wt.exe split the wrap into pieces and try to launch each
    # fragment as a separate tab, producing 0x80070002 "file not found".
    # `&&` is a bash-only operator that wt.exe passes through verbatim.
    # Each tmux-set succeeds on any modern tmux (option names are stable
    # since 2015), so the chain proceeds reliably to `tmux new`.
    #
    #   mouse on              -- scroll wheel scrolls the scrollback buffer
    #                            (without this, wheel events drop through to
    #                            Claude Code which ignores them); also makes
    #                            click-and-drag select text in copy mode.
    #   history-limit 50000   -- default 2000 is exhausted in seconds of busy
    #                            Claude output; 50k is generous, ~few MB RAM.
    #   default-terminal      -- "tmux-256color" so Claude's TUI renders the
    #                            full palette (default "screen" clamps to 8).
    # Ensure server + session exist before setting server-wide options.
    # `tmux start-server` alone doesn't work because exit-empty=on (default)
    # means the server exits immediately when it has no sessions, so the
    # next `tmux set` then fails with "no server running on /tmp/...".
    #
    # Correct pattern (mirrors scripts/launch-agents.sh): has-session check
    # (exits non-zero if no server) OR new-session -d to create a detached
    # session running the inner cmd. The session keeps the server alive,
    # so `tmux set` succeeds. Then explicit `exec tmux attach` to attach
    # interactively. Replaces the original `tmux new -A -s … bash -c …`
    # auto-attach form with detached-create + explicit-attach so server
    # options can be set in between.
    # No single quotes needed: tmux-256color has no spaces or special chars.
    $tmuxOptions = "tmux set -gq mouse on && tmux set -gq history-limit 50000 && tmux set -gq default-terminal tmux-256color"

    # Session names now use '-' as separator (not ':'), so the '=' exact-match
    # prefix and per-name single-quoting are no longer required. Names like
    # "sunflowers-spec-agent" contain only [A-Za-z0-9-] — safe without quoting.
    $newSessionArgs = "-d -s $SessionName"
    if ($WindowName) {
        $newSessionArgs += " -n $WindowName"
    }

    # Build the wrapper script. Single quotes inside are fine here because the
    # entire script is base64-encoded below — they never appear in the SSH arg.
    $wrapperScript = "( tmux has-session -t $SessionName 2>/dev/null || tmux new-session $newSessionArgs bash -c 'echo $b64 | base64 -d | bash -l' ) && $tmuxOptions && exec tmux attach -t $SessionName"

    # Double-base64: encode the whole wrapper so the final SSH argument is just
    #   echo OUTERB64 | base64 -d | bash
    # This contains only [A-Za-z0-9+/=|. ] — no shell metacharacters at all.
    # Eliminates the quoting issue that caused "unexpected EOF while looking for
    # matching '" errors when single-quoted strings passed through the
    # PowerShell -> Start-Process -> wt.exe -> ssh.exe -> sshd chain.
    $wrapperBytes = [System.Text.Encoding]::UTF8.GetBytes($wrapperScript)
    $outerB64 = [Convert]::ToBase64String($wrapperBytes)
    return "echo $outerB64 | base64 -d | bash"
}

function Build-SshCommand {
    param(
        [string]$Host_,
        [string]$RemotePath,
        [string[]]$Commands,
        [hashtable]$Settings,
        [string]$RepoName = "",
        [string]$ProjectName = "",
        [string]$AgentName = ""    # owner: field from platform.yaml; drives the tmux session name
    )

    $client = $Settings["ssh_client"]
    if (-not $client) { $client = "ssh" }

    # reliability: none | tmux | tmux+mosh — defaults to none for back-compat.
    # When tmux is selected, the inner command is wrapped in `tmux new -A -s ...`
    # so an SSH drop doesn't kill the in-flight Claude Code session.
    # When tmux+mosh is selected, the SSH client is replaced with `mosh` for
    # automatic UDP-based reconnect in addition to the tmux wrapper.
    $reliability = $Settings["reliability"]
    if (-not $reliability) { $reliability = "none" }
    $useTmux = ($reliability -eq "tmux" -or $reliability -eq "tmux+mosh")
    $useMosh = ($reliability -eq "tmux+mosh")

    $allCmds = @("cd $RemotePath") + $Commands
    $chainedCmd = $allCmds -join ' && '

    if ($useTmux) {
        # Tmux session name: "${ProjectName}-${AgentName}" — dash separator.
        # Colon was previously used but tmux interprets ':' as session:window
        # separator in target notation, making attach fail even with '=' prefix
        # (tmux strips ':agent' and looks for session 'project' alone).
        # Per fix-launcher-tmux-session-naming. Fall back to RepoName if AgentName
        # is absent (with a warning so the misconfiguration surfaces).
        $agentForSession = $AgentName
        if (-not $agentForSession) {
            $agentForSession = $RepoName
            if ($RepoName) {
                Write-Warn "Build-SshCommand: repo '$RepoName' missing owner: field in platform.yaml; using repo name for tmux session"
            }
        }
        $session = "${ProjectName}-${agentForSession}"
        $chainedCmd = Wrap-WithTmux -SessionName $session -InnerCommand $chainedCmd -WindowName $RepoName
    }

    # Resolve host: per-repo > CLI param > settings default
    $target = $Host_
    if (-not $target) { $target = $Settings["ssh_default_host"] }
    if (-not $target) { return $null }

    # Mosh path (only valid with OpenSSH-style targets — putty/plink users
    # stay on their existing client).
    if ($useMosh) {
        $sshPassthrough = ""
        if ($Settings["ssh_key"]) {
            $sshPassthrough = " --ssh=`"ssh -i $($Settings['ssh_key'])`""
        }
        # mosh runs the command directly; tmux's -A handles attach-or-create.
        # No outer quoting needed because tmux's command is its own argv.
        return @{
            type = "wt-tab"
            args = "mosh${sshPassthrough} $target -- $chainedCmd"
        }
    }

    switch ($client) {
        "ssh" {
            # OpenSSH: runs in terminal, great for WT tabs
            $keyFlag = ""
            if ($Settings["ssh_key"]) { $keyFlag = "-i $($Settings['ssh_key']) " }
            # Escape double quotes in the command, wrap in double quotes for SSH
            $escaped = $chainedCmd -replace '"', '\"'
            return @{
                type = "wt-tab"
                args = "ssh ${keyFlag}-t $target `"$escaped`""
            }
        }
        "plink" {
            # PuTTY CLI: runs in terminal, supports saved sessions
            $session = $Settings["ssh_session"]
            $plinkTarget = if ($session) { "-load `"$session`"" } else { "-ssh $target" }
            return @{
                type = "wt-tab"
                args = "plink $plinkTarget -t `"$chainedCmd`""
            }
        }
        "putty" {
            # PuTTY GUI: opens separate window (cannot embed in WT)
            $session = $Settings["ssh_session"]
            $puttyTarget = if ($session) { "-load `"$session`"" } else { "-ssh $target" }
            return @{
                type = "separate-window"  # launches its own window
                exe  = "putty"
                args = "$puttyTarget -t -m -"  # -m reads commands from stdin
                # PuTTY can't pass commands inline easily.
                # Better approach: use -m with a temp script file
                remoteCmd = $chainedCmd
            }
        }
        "kitty" {
            # KiTTY (PuTTY fork): same as PuTTY but with extras
            $session = $Settings["ssh_session"]
            $kittyTarget = if ($session) { "-load `"$session`"" } else { "-ssh $target" }
            return @{
                type = "separate-window"
                exe  = "kitty"
                args = "$kittyTarget -cmd `"$chainedCmd`""
                remoteCmd = $chainedCmd
            }
        }
        "custom" {
            $template = $Settings["ssh_command_template"]
            if (-not $template) { return $null }
            $cmd = $template -replace '\{host\}', $target
            $cmd = $cmd -replace '\{path\}', $RemotePath
            $cmd = $cmd -replace '\{commands\}', $chainedCmd
            return @{
                type = "wt-tab"
                args = $cmd
            }
        }
        default {
            return @{
                type = "wt-tab"
                args = "ssh -t $target -- bash -ic `"$chainedCmd`""
            }
        }
    }
}

# ============================================================
# Main
# ============================================================

Write-Host ""
Write-Host "=== Otaman Agent Launcher ===" -ForegroundColor White

if ($activeName) {
    Write-Ok "Connection: $activeName ($connType)"
} elseif ($Shell) {
    Write-Ok "Ad-hoc shell: $Shell"
} else {
    Write-Warn "No connection configured. Run .\launch.ps1 -Setup"
}

# -Pull: overwrite local platform.yaml with remote copy, then exit
if ($Pull) {
    if ($connType -notin @('ssh','mesh')) {
        Write-Err "-Pull requires an SSH or mesh connection (got '$connType')."
        exit 1
    }
    $remoteRoot   = $activeConn["ssh_remote_root"]
    $remoteHost   = $activeConn["ssh_default_host"]
    $remoteClient = $activeConn["ssh_client"]
    $sshKey       = $activeConn["ssh_key"]

    if (-not $remoteRoot -or -not $remoteHost) {
        Write-Err "Connection '$activeName' missing ssh_remote_root or ssh_default_host"
        exit 1
    }

    $remoteCfg = "$remoteRoot/platform.yaml"
    Write-Step "Pulling platform.yaml from $remoteHost`:$remoteCfg"

    $output = $null
    try {
        if ($remoteClient -eq 'plink' -or $remoteClient -eq 'putty') {
            $session = $activeConn["ssh_session"]
            $plinkTarget = if ($session) { "-load `"$session`"" } else { "-ssh $remoteHost" }
            $output = & plink $plinkTarget -batch "cat $remoteCfg" 2>$null
        } elseif ($sshKey) {
            $output = & ssh -i $sshKey -o StrictHostKeyChecking=no $remoteHost "cat $remoteCfg" 2>$null
        } else {
            $output = & ssh $remoteHost "cat $remoteCfg" 2>$null
        }
    } catch {
        Write-Err "ssh fetch threw: $_"
        exit 1
    }

    if ($LASTEXITCODE -ne 0 -or -not $output) {
        Write-Err "Could not fetch $remoteCfg from $remoteHost"
        exit 1
    }

    if (Test-Path $ConfigFile) {
        $backup = "$ConfigFile.bak"
        Copy-Item $ConfigFile $backup -Force
        Write-Ok "Existing local copy backed up to $(Split-Path $backup -Leaf)"
    }

    $output | Set-Content $ConfigFile -Encoding UTF8
    Write-Ok "Pulled $($output.Count) lines into $(Split-Path $ConfigFile -Leaf)"
    exit 0
}

# If no local config, try fetching from remote server (only for ssh connection)
if (-not (Test-Path $ConfigFile)) {
    $remoteRoot = $activeConn["ssh_remote_root"]
    $remoteHost = $activeConn["ssh_default_host"]
    $remoteClient = $activeConn["ssh_client"]

    if ($connType -in @('ssh','mesh') -and $remoteRoot -and $remoteHost) {
        $remoteCfg = "$remoteRoot/platform.yaml"
        Write-Step "No local $ConfigFile --fetching from $remoteHost`:$remoteCfg"

        $fetchOk = $false
        $sshKey = $activeConn["ssh_key"]
        try {
            if ($remoteClient -eq 'plink' -or $remoteClient -eq 'putty') {
                $session = $activeConn["ssh_session"]
                $plinkTarget = if ($session) { "-load `"$session`"" } else { "-ssh $remoteHost" }
                $output = & plink $plinkTarget -batch "cat $remoteCfg" 2>$null
            } elseif ($sshKey) {
                $output = & ssh -i $sshKey -o StrictHostKeyChecking=no $remoteHost "cat $remoteCfg" 2>$null
            } else {
                $output = & ssh $remoteHost "cat $remoteCfg" 2>$null
            }
            if ($LASTEXITCODE -eq 0 -and $output) {
                $output | Set-Content $ConfigFile -Encoding UTF8
                Write-Ok "Fetched platform.yaml from remote ($($output.Count) lines)"
                $fetchOk = $true
            }
        } catch {}

        if (-not $fetchOk) {
            Write-Err "Could not fetch $remoteCfg from $remoteHost"
            Write-Warn "Either copy platform.yaml locally or ensure SSH access works."
            exit 1
        }
    } else {
        Write-Err "'$ConfigFile' not found."
        Write-Warn "Run: .\launch.ps1 -Setup   to configure a connection"
        exit 1
    }
}

Write-Step "Reading $ConfigFile"
try {
    $parsed = Parse-PlatformYaml -Path $ConfigFile
    $allRepos = @($parsed.repos)
    $profiles = $parsed.profiles
} catch { Write-Err "Failed to parse: $_"; exit 1 }
# Project name from platform.yaml — used for tmux session namespacing so two
# projects on the same host don't collide on session names.
$projectName = Get-ProjectName -Path $ConfigFile
# Separate active vs disabled repos for a useful summary
$disabledRepos = @($allRepos | Where-Object { $_.disabled })
$activeRepos = @($allRepos | Where-Object { -not $_.disabled })

$summaryLine = "Found $($allRepos.Count) repos ($($activeRepos.Count) active"
if ($disabledRepos.Count -gt 0) { $summaryLine += ", $($disabledRepos.Count) disabled" }
$summaryLine += "), $($profiles.Count) profiles"
Write-Ok $summaryLine

if ($disabledRepos.Count -gt 0) {
    $mode = if ($IncludeDisabled) { "included via -IncludeDisabled" } else { "skipped" }
    Write-Host "  Disabled ($mode): " -NoNewline -ForegroundColor DarkGray
    Write-Host ($disabledRepos | ForEach-Object { $_.name }) -ForegroundColor DarkGray -Separator ", "
}

# Apply disabled filter unless user explicitly opts in
$reposForLaunch = if ($IncludeDisabled) { $allRepos } else { $activeRepos }

# Snapshot original launch_shell + launch_commands so a connection swap
# (via the picker's 'c' hotkey) can restore them before re-applying the
# new connection's rewrite. Done once before the loop; loop iterations
# re-read these to start fresh.
foreach ($r in $allRepos) {
    Add-Member -InputObject $r -NotePropertyName '_origShell' -NotePropertyValue $r.launch_shell -Force
    Add-Member -InputObject $r -NotePropertyName '_origCommands' -NotePropertyValue $r.launch_commands -Force
}

# Loop: connection-effect + account/secrets banner + profile pick.
# 'c' in the profile/repo picker sets $script:ChangeConnection — we then
# show the full connection menu and restart the loop with the new choice.
while ($true) {
    $script:ChangeConnection = $false

    # Restore originals so connection-effect re-applies cleanly each iteration.
    foreach ($r in $reposForLaunch) {
        $r.launch_shell    = $r._origShell
        $r.launch_commands = $r._origCommands
    }
    $launchable = @($reposForLaunch | Where-Object { $_.launch_shell -and $_.launch_commands.Count -gt 0 })

    # Apply active connection: rewrite per-repo shell/commands for this connection's type.
    # `platform.yaml` may be configured with any baseline shell (ssh, wsl, powershell);
    # the active connection overrides it so one platform.yaml serves all scenarios.
    if (-not $Shell) {
        if ($connType -eq 'local') {
            # ssh -> local_shell (wsl|powershell)
            $localShell = $activeConn['local_shell']
            if (-not $localShell) { $localShell = 'wsl' }
            foreach ($r in $launchable) {
                if ($r.launch_shell -eq 'ssh') {
                    $r.launch_shell = $localShell
                    # If the ssh command used `source ~/.nvm/nvm.sh` (bash-only) and local shell is PowerShell, simplify
                    $hasNvm = ($r.launch_commands | Where-Object { $_ -match 'nvm\.sh' }).Count -gt 0
                    if ($hasNvm -and $localShell -eq 'powershell') {
                        $r.launch_commands = @("claude --version 2>`$null | Out-Null; claude -c '/otaman:check'; if (`$LASTEXITCODE -ne 0) { claude '/otaman:check' }")
                    }
                    # For wsl we keep commands as-is (they're bash-compatible inside WSL)
                }
            }
        } elseif ($connType -eq 'ssh' -or $connType -eq 'mesh') {
            # wsl/powershell -> ssh (rebuild commands with remote plugin path).
            # Both `ssh` and `mesh` connection types take this branch — they use
            # the same SSH wire underneath; `mesh` is just a user-facing label
            # for "this connection rides over a VPN tunnel."
            $pluginDir = $activeConn["ssh_plugin_path"]
            foreach ($r in $launchable) {
                if ($r.launch_shell -in @('wsl','powershell')) {
                    $r.launch_shell = 'ssh'
                    if ($pluginDir) {
                        $r.launch_commands = @("source ~/.nvm/nvm.sh && claude --plugin-dir $pluginDir --version >/dev/null 2>&1 || true; while :; do { claude -c --plugin-dir $pluginDir /otaman:check || claude --plugin-dir $pluginDir /otaman:check; }; printf '\n[claude exited -- Enter to respawn, Ctrl-C to drop to shell] '; read -r || break; done")
                    } else {
                        $r.launch_commands = @("source ~/.nvm/nvm.sh && claude --version >/dev/null 2>&1 || true; while :; do { claude -c /otaman:check || claude /otaman:check; }; printf '\n[claude exited -- Enter to respawn, Ctrl-C to drop to shell] '; read -r || break; done")
                    }
                }
            }
        }
    }

    # Shell override (CLI -Shell param): make all repos launchable with that shell
    if ($Shell) {
        $launchable = @($reposForLaunch | Where-Object { $_.path })
        $pluginDir = $activeConn["ssh_plugin_path"]
        foreach ($r in $launchable) {
            $r.launch_shell = $Shell
            if ($Shell -eq 'ssh') {
                # For SSH: always rebuild commands with remote plugin path (no single quotes)
                if ($pluginDir) {
                    $r.launch_commands = @("source ~/.nvm/nvm.sh && claude --plugin-dir $pluginDir --version >/dev/null 2>&1 || true; while :; do { claude -c --plugin-dir $pluginDir /otaman:check || claude --plugin-dir $pluginDir /otaman:check; }; printf '\n[claude exited -- Enter to respawn, Ctrl-C to drop to shell] '; read -r || break; done")
                } else {
                    $r.launch_commands = @("source ~/.nvm/nvm.sh && claude --version >/dev/null 2>&1 || true; while :; do { claude -c /otaman:check || claude /otaman:check; }; printf '\n[claude exited -- Enter to respawn, Ctrl-C to drop to shell] '; read -r || break; done")
                }
            } elseif (-not $r.launch_commands -or $r.launch_commands.Count -eq 0) {
                $r.launch_commands = @("claude --version 2>`$null | Out-Null; claude -c '/otaman:check'; if (`$LASTEXITCODE -ne 0) { claude '/otaman:check' }")
            }
        }

        # Prompt setup if SSH requested but no connection configured
        if ($Shell -eq 'ssh' -and -not $activeConn['ssh_client']) {
            $settings = Run-Setup
            if ($settings) {
                $top = $settings.Top
                $activeName = $top['active_connection']
                if ($activeName -and $settings.Connections.Contains($activeName)) {
                    $activeConn = Resolve-Connection -Connections $settings.Connections -Name $activeName
                }
            }
        }
    }

    Write-Ok "$($launchable.Count) launchable"
    if ($launchable.Count -eq 0) { Write-Warn "No launchable repos."; exit 0 }

    # ============================================================
    # Resolve account for this connection, load secrets.env.
    # These are shared across all sessions launched in this run.
    # ============================================================

    $accounts = if ($settings) { $settings.Accounts } else { [ordered]@{} }
    $activeAccount = Get-AccountForConnection -Accounts $accounts -Connection $activeConn
    $activeAccountName = $activeAccount['name']
    $maestroSecrets = Get-MaestroSecretsEnv -MaestroRoot $cfgParent

    if ($activeAccountName) {
        $cfgDirRaw = $activeAccount['config_dir']
        if ($cfgDirRaw) {
            Write-Ok "Account: $activeAccountName ($cfgDirRaw)"
        } else {
            Write-Warn "Account '$activeAccountName' has no config_dir; CLAUDE_CONFIG_DIR will not be set"
        }
    }
    if ($maestroSecrets.Count -gt 0) {
        Write-Ok "Secrets: $($maestroSecrets.Count) var(s) from secrets.env"
    }

    # SSH client info
    if ($launchable | Where-Object { $_.launch_shell -eq 'ssh' }) {
        $clientName = $activeConn["ssh_client"]
        if ($clientName) { Write-Ok "SSH client: $clientName" }
    }

    # Connection label for the picker — only meaningful when we actually
    # have multiple connections to swap between AND no -Shell override.
    $connLabel = ""
    if ($activeName -and -not $Shell -and $settings -and $settings.Connections.Count -gt 1) {
        $connLabel = "$activeName ($connType)"
    }

    # Profile selection
    if (-not $Profile -and $Filter.Count -eq 0 -and $profiles.Count -gt 0) {
        $Profile = Show-ProfileMenu -Profiles $profiles -AllRepos $launchable -ConnectionLabel $connLabel
        if ($script:ChangeConnection) {
            # Re-pick from the FULL connections list (the user is asking to
            # swap, so don't re-apply default_type filter here).
            $sel = Show-ConnectionMenu -Connections $settings.Connections -Default $activeName
            if (-not $sel) { exit 1 }
            $activeConn = Resolve-Connection -Connections $settings.Connections -Name $sel
            $activeName = $sel
            $connType = if ($activeConn['type']) { $activeConn['type'] } else { 'ssh' }
            $Profile = ""  # reset so the next iteration shows the profile menu again
            continue
        }
        if (-not $Profile) { exit 1 }
    }
    if ($Profile -eq '__pick__') {
        # Custom repo picker
        $launchable = @(Show-RepoPicker -Repos $launchable -ConnectionLabel $connLabel)
        if ($script:ChangeConnection) {
            $sel = Show-ConnectionMenu -Connections $settings.Connections -Default $activeName
            if (-not $sel) { exit 1 }
            $activeConn = Resolve-Connection -Connections $settings.Connections -Name $sel
            $activeName = $sel
            $connType = if ($activeConn['type']) { $activeConn['type'] } else { 'ssh' }
            $Profile = ""
            continue
        }
        if ($launchable.Count -eq 0) { Write-Err "No repos selected"; exit 1 }
        Write-Ok "Custom: $($launchable.Count) agents"
    } elseif ($Profile -and $profiles.ContainsKey($Profile)) {
        $p = $profiles[$Profile]
        # Show which repos this profile will actually launch (post disabled-filter).
        $resolved = Resolve-ProfileRepos -Profile $p -AllRepos $allRepos
        if ($resolved.Active.Count -gt 0) {
            Write-Host "  Launching: " -NoNewline -ForegroundColor DarkGray
            Write-Host ($resolved.Active -join ", ") -ForegroundColor Gray
        }
        if ($resolved.Disabled.Count -gt 0) {
            Write-Host "  Skipped (disabled): " -NoNewline -ForegroundColor DarkGray
            Write-Host ($resolved.Disabled -join ", ") -ForegroundColor DarkGray
        }
        if (-not (Is-AllRepos $p.repos)) {
            $profileRepos = $p.repos
            $launchable = @($launchable | Where-Object { $profileRepos -contains $_.name })
        }
        Write-Ok "Profile '$Profile': $($launchable.Count) agents"
    } elseif ($Profile) { Write-Err "Unknown profile: $Profile"; exit 1 }

    # Name filter
    if ($Filter.Count -gt 0) {
        $launchable = @($launchable | Where-Object { $n = $_.name; ($Filter | Where-Object { $n -like "*$_*" }).Count -gt 0 })
        if ($launchable.Count -eq 0) { Write-Err "No repos matched filter"; exit 1 }
    }

    break
}

# Validate targets
Write-Step "Checking targets"
$valid = @()
foreach ($r in $launchable) {
    if ($r.launch_shell -eq 'ssh') {
        $h = if ($r.launch_ssh_host) { $r.launch_ssh_host } else { $activeConn["ssh_default_host"] }
        # Resolve remote path: use explicit ssh_path, or resolve repo's relative path against remote root
        $p_ = if ($r.launch_ssh_path) { $r.launch_ssh_path }
             elseif ($activeConn["ssh_remote_root"] -and $r.path) {
                 # Repo path is relative to otaman folder (e.g., ../lmachine-common)  # legacy: maestro folder name
                 # Remote root is the otaman folder (e.g., /home/romans/lmachine/lmachine-maestro)  # legacy: maestro folder name
                 # Combine and normalize: /home/romans/lmachine/lmachine-maestro/../lmachine-common  # legacy: lmachine-maestro folder name
                 # -> /home/romans/lmachine/lmachine-common
                 $combined = "$($activeConn['ssh_remote_root'])/$($r.path)" -replace '\\', '/'
                 # Normalize ../  segments
                 while ($combined -match '/[^/]+/\.\./') {
                     $combined = $combined -replace '/[^/]+/\.\./', '/'
                 }
                 $combined
             }
             else { $r.path }
        $r.launch_ssh_path = $p_
        $r.launch_ssh_host = $h
        Write-Ok "$($r.name) -> $h`:$p_"
        $valid += $r
    } else {
        # Local shell (wsl/powershell) — resolve path against local_root if configured
        $localRoot = $activeConn['local_root']
        $effectivePath = if ($localRoot) { Resolve-LocalPath -LocalRoot $localRoot -RepoPath $r.path } else { $r.path }
        $r.path = $effectivePath
        if (Test-Path $effectivePath) { Write-Ok "$($r.name) -> $effectivePath"; $valid += $r }
        else { Write-Warn "$($r.name) -> $effectivePath (NOT FOUND, skipping)" }
    }
}
if ($valid.Count -eq 0) { Write-Err "No valid targets."; exit 1 }

# -Close / -Restart: kill tmux sessions on the remote for selected repos.
# Repos with reliability=none have no tmux session to kill — quietly skipped
# with a one-line note. -Close exits after kill; -Restart continues to the
# normal launch flow which will create fresh sessions because the old ones
# are gone.
if ($Close -and $Restart) {
    Write-Err "-Close and -Restart are mutually exclusive."
    exit 1
}
if ($Close -or $Restart) {
    $killActions = @()
    foreach ($r in $valid) {
        if ($r.launch_shell -ne 'ssh') {
            Write-Warn "$($r.name): not an SSH connection — no tmux session to close, skipping"
            continue
        }
        $reliab = $activeConn['reliability']
        if (-not $reliab) { $reliab = 'none' }
        if ($reliab -eq 'none') {
            Write-Warn "$($r.name): reliability=none — no tmux session, skipping"
            continue
        }
        # Per fix-launcher-tmux-session-naming: session name is
        # "${projectName}-${owner}" (dash, not colon — colon breaks tmux target
        # parsing). Fall back to repo name if owner: missing (with a warning),
        # to match Build-SshCommand's fallback.
        $agentForSession = $r.owner
        if (-not $agentForSession) {
            $agentForSession = $r.name
            Write-Warn "$($r.name): missing owner: field in platform.yaml; using repo name for tmux session"
        }
        $sess = "${projectName}-${agentForSession}"

        $h = if ($r.launch_ssh_host) { $r.launch_ssh_host } else { $activeConn['ssh_default_host'] }
        $keyFlag = ""
        if ($activeConn['ssh_key']) { $keyFlag = "-i $($activeConn['ssh_key']) " }
        # -t not needed for a one-shot remote command. tmux kill-session
        # exits 1 if the session doesn't exist; redirect stderr so the
        # quiet-skip is genuinely quiet, and force exit 0 with `|| true`.
        # `=` prefix forces exact match so the colon doesn't get parsed.
        $remoteCmd = "tmux kill-session -t '=$sess' 2>/dev/null || true"
        $killActions += @{
            repo = $r.name
            session = $sess
            host = $h
            sshArgs = "ssh ${keyFlag}$h `"$remoteCmd`""
        }
    }

    if ($killActions.Count -eq 0) {
        Write-Warn "No tmux sessions to close (no SSH targets with reliability set)."
        if ($Close) { exit 0 }
        # -Restart with nothing to kill: fall through to normal launch
    } else {
        Write-Step "Closing $($killActions.Count) tmux session(s)"
        foreach ($k in $killActions) {
            Write-Host "  $([char]0x25CF) " -NoNewline -ForegroundColor Yellow
            Write-Host "$($k.repo)" -NoNewline -ForegroundColor White
            Write-Host " (session: $($k.session) on $($k.host))" -ForegroundColor DarkGray
        }

        if (-not $Yes -and -not $DryRun) {
            $reply = Read-Host "Continue? [y/N]"
            if ($reply -notmatch '^[Yy]') {
                Write-Warn "Cancelled."
                exit 0
            }
        }

        foreach ($k in $killActions) {
            if ($DryRun) {
                Write-Host "  [dry-run] $($k.sshArgs)" -ForegroundColor DarkGray
            } else {
                try {
                    Invoke-Expression $k.sshArgs | Out-Null
                    Write-Ok "  killed: $($k.repo) ($($k.session))"
                } catch {
                    Write-Warn "  failed: $($k.repo) ($_)"
                }
            }
        }

        if ($Close) {
            Write-Ok "Done. ($($killActions.Count) session(s) closed.)"
            exit 0
        }
        # -Restart: fall through to the normal launch flow below
        Write-Step "Re-launching after close"
    }
}

# Auto-register this launcher folder so `otaman upgrade` knows about it.
# Best-effort and silent — never block a launch on registration failure.
# Skipped in dry-run because dry-run shouldn't mutate user state.
if (-not $DryRun) {
    try {
        # Polyrepo split moved the launcher-register subcommand to otaman-cli;
        # the legacy `cli/maestro.py` path inside this repo is dead. Call the  # legacy: cli/maestro.py path
        # `otaman` binary on PATH instead. If absent, the redirect keeps the
        # launch silent.
        $otamanCli = Get-Command otaman -ErrorAction SilentlyContinue
        if ($otamanCli) {
            & $otamanCli.Source launcher register $cfgParent 2>&1 | Out-Null
        }
    } catch {
        # Silent on any failure — registration is a side-channel, not load-bearing.
    }
}

# Build launch specs
$consoleColors = @("Blue","Green","Cyan","Magenta","Yellow","DarkCyan","DarkGreen","DarkMagenta","DarkYellow","Red")
Write-Step "Building $($valid.Count) sessions"
if ($DryRun) { Write-Warn "DRY RUN -- preview only" }

$wtTabs = @()          # Windows Terminal tabs
$separateWindows = @() # PuTTY/KiTTY separate windows

# Resolve WSL distro: CLI arg > connection > default Ubuntu
$effectiveWslDistro = if ($WslDistro) { $WslDistro } elseif ($activeConn['wsl_distro']) { $activeConn['wsl_distro'] } else { 'Ubuntu' }

# Runner-first dispatch (default in wt.exe tmux mode per auto-session-spawn-
# implementation task 4.3). Each repo's spawn goes through otaman-runner's
# HTTP /spawn endpoint; the runner returns an attach_command which we render
# as a wt.exe tab body (run inside WSL so the bash one-liner executes
# natively). If the endpoint file is missing or any /spawn fails we fall
# through to the existing per-shell tab build below with a
# `[degraded mode: ...]` notice so the user knows which spawn path actually
# ran. Pass -NoRunner to skip the runner entirely (offline / dev mode).
$useRunnerTabs = $false
if (-not $NoRunner) {
    $endpoint = Read-RunnerEndpoint
    if ($endpoint) {
        $human = $env:USERNAME
        Write-Host "runner: spawning via http://$($endpoint.Host):$($endpoint.Port) (human=$(if ($human) { $human } else { '<unset>' }))" -ForegroundColor DarkGray
        $runnerWtTabs = @()
        $runnerOk = $true
        foreach ($repo in $valid) {
            $rTitle = if ($repo.launch_title) { $repo.launch_title } else { $repo.name }
            $rColor = if ($repo.launch_color) { $repo.launch_color } else { "#4169E1" }
            if (-not $rColor.StartsWith('#')) { $rColor = "#$rColor" }
            $rAgent = if ($repo.owner) { $repo.owner } else { $repo.name }
            try {
                $attachCmd = Invoke-RunnerSpawn -Endpoint $endpoint -Agent $rAgent -Repo $repo.name -ProjectRoot $cfgParent -Account $activeAccountName -Human $human
            } catch {
                Write-Warn "runner: spawn failed for $($repo.name): $_"
                $runnerOk = $false
                break
            }
            # Wrap the opaque attach_command in WSL bash -ic so it runs in a
            # real shell (typical attach_command is `ssh user@host tmux a ...`
            # or `tmux a -t ...`). Mirrors the existing wsl-shell tab build.
            $escaped = $attachCmd -replace '"', '\"'
            $runnerWtTabs += "--title `"$rTitle`" --suppressApplicationTitle --tabColor `"$rColor`" wsl.exe -d $effectiveWslDistro -- bash -ic `"$escaped`""
            Write-Host "  spawned $rAgent@$($repo.name) -> $attachCmd" -ForegroundColor DarkGray
        }
        if ($runnerOk -and $runnerWtTabs.Count -gt 0) {
            $wtTabs = $runnerWtTabs
            $useRunnerTabs = $true
        } else {
            Write-Warn "[degraded mode: runner unavailable; using local fallback]"
        }
    } else {
        Write-Warn "[degraded mode: runner unavailable; using local fallback]"
        Write-Host "  (no endpoint file at ~/.otaman/runner.endpoint; start the runner daemon or pass -NoRunner to silence)" -ForegroundColor DarkGray
    }
}

if (-not $useRunnerTabs) {
for ($i = 0; $i -lt $valid.Count; $i++) {
    $repo = $valid[$i]
    $title = if ($repo.launch_title) { $repo.launch_title } else { $repo.name }
    $color = if ($repo.launch_color) { $repo.launch_color } else { "#4169E1" }
    if (-not $color.StartsWith('#')) { $color = "#$color" }
    $shell = $repo.launch_shell

    $cc = $consoleColors[$i % $consoleColors.Count]

    # Per-repo model/effort tier (walks platform.yaml models: chain).
    # Resolved here so each tab gets its own ANTHROPIC_MODEL /
    # CLAUDE_CODE_EFFORT_LEVEL based on which repo it's launching.
    $repoTier = Get-ResolvedTierForRepo -MaestroRoot $cfgParent -Repo $repo.name

    # Per-connection unattended flag — when true the launcher exports
    # MAESTRO_UNATTENDED=1 so the SessionStart hook auto-enables AFK.
    # Interactive launcher tabs leave this false (the common case).
    $connUnattended = [bool]$activeConn['unattended']

    if ($shell -eq 'wsl') {
        $fullPath = (Resolve-Path $repo.path -ErrorAction SilentlyContinue)
        if (-not $fullPath) { continue }
        $wslPath = ConvertTo-WslPath $fullPath.Path
        $cfgDirWsl = if ($activeAccount['config_dir']) { Expand-ConfigDir -ConfigDir $activeAccount['config_dir'] -Shell 'wsl' } else { "" }
        $envPrefix = Build-EnvPrefix -Shell 'wsl' -ConfigDirExpanded $cfgDirWsl -SecretsEnv $maestroSecrets -Model $repoTier.Model -Effort $repoTier.Effort -Unattended $connUnattended -Account $activeAccountName
        $allCmds = @("cd '$wslPath'") + $repo.launch_commands
        if ($envPrefix) { $allCmds = @($envPrefix) + $allCmds }
        $chainedCmd = $allCmds -join ' && '
        $wtTabs += "--title `"$title`" --suppressApplicationTitle --tabColor `"$color`" wsl.exe -d $effectiveWslDistro -- bash -ic `"$chainedCmd`""
    }
    elseif ($shell -eq 'powershell') {
        $fullPath = (Resolve-Path $repo.path -ErrorAction SilentlyContinue)
        if (-not $fullPath) { continue }
        $cfgDirPs = if ($activeAccount['config_dir']) { Expand-ConfigDir -ConfigDir $activeAccount['config_dir'] -Shell 'powershell' } else { "" }
        $envPrefix = Build-EnvPrefix -Shell 'powershell' -ConfigDirExpanded $cfgDirPs -SecretsEnv $maestroSecrets -Model $repoTier.Model -Effort $repoTier.Effort -Unattended $connUnattended -Account $activeAccountName
        $allCmds = @("Set-Location '$($fullPath.Path)'") + $repo.launch_commands
        if ($envPrefix) { $allCmds = @($envPrefix) + $allCmds }
        $chainedCmd = $allCmds -join '; '
        # Encode the chain as base64 UTF-16LE (PowerShell -EncodedCommand format)
        # so that `;` and other special characters survive wt.exe's command-line
        # parser. wt.exe treats unescaped `;` as a tab separator regardless of
        # inner shell quoting; base64 produces an opaque token containing only
        # [A-Za-z0-9+/=], so wt.exe sees one token and passes it through.
        $cmdBytes = [System.Text.Encoding]::Unicode.GetBytes($chainedCmd)
        $cmdEncoded = [Convert]::ToBase64String($cmdBytes)
        $wtTabs += "--title `"$title`" --suppressApplicationTitle --tabColor `"$color`" powershell.exe -NoExit -EncodedCommand $cmdEncoded"
    }
    elseif ($shell -eq 'ssh') {
        $cfgDirSsh = if ($activeAccount['config_dir']) { Expand-ConfigDir -ConfigDir $activeAccount['config_dir'] -Shell 'ssh' } else { "" }
        $envPrefix = Build-EnvPrefix -Shell 'ssh' -ConfigDirExpanded $cfgDirSsh -SecretsEnv $maestroSecrets -Model $repoTier.Model -Effort $repoTier.Effort -Unattended $connUnattended -Account $activeAccountName
        $sshCmds = if ($envPrefix) { @($envPrefix) + $repo.launch_commands } else { $repo.launch_commands }
        $sshResult = Build-SshCommand -Host_ $repo.launch_ssh_host -RemotePath $repo.launch_ssh_path -Commands $sshCmds -Settings $activeConn -RepoName $repo.name -ProjectName $projectName -AgentName $repo.owner
        if (-not $sshResult) { Write-Warn "$($repo.name): SSH not configured, skipping"; continue }

        if ($sshResult.type -eq 'wt-tab') {
            $wtTabs += "--title `"$title`" --suppressApplicationTitle --tabColor `"$color`" $($sshResult.args)"
        } else {
            # PuTTY/KiTTY: separate window
            $separateWindows += @{
                title = $title; exe = $sshResult.exe; args = $sshResult.args
                remoteCmd = $sshResult.remoteCmd; color = $color
            }
        }

        # Trace file: append the SSH args (and decoded base64 payload when
        # reliability=tmux/mosh) to <otaman-root>/.otaman/launcher.log so a
        # silent-drop failure leaves something to grep. Append-only, with
        # size-based rotation (1 MiB threshold, keeps 3 backups).
        #
        # M-1 migration: new installs write to .otaman/. If a legacy
        # .maestro/ directory exists and .otaman/ does not, we keep writing  # legacy: .maestro/ directory
        # to .maestro/ — avoids splitting one project's log history across  # legacy: .maestro/ directory
        # two directories until someone migrates explicitly (mv .maestro  # legacy: .maestro directory
        # .otaman, or `otaman migrate`).
        try {
            $logDir = Join-Path $cfgParent ".otaman"
            $legacyDir = Join-Path $cfgParent ".maestro"  # legacy: .maestro directory
            if ((Test-Path $legacyDir) -and -not (Test-Path $logDir)) {
                $logDir = $legacyDir
            }
            if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
            $logFile = Join-Path $logDir "launcher.log"
            Rotate-Log -Path $logFile
            $stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz"
            $logLines = @(
                "[$stamp] $($repo.name) ($shell) -> $($repo.launch_ssh_host)"
                "  args: $($sshResult.args)"
            )
            $b64Match = [regex]::Match($sshResult.args, "echo (?<b64>[A-Za-z0-9+/=]+) \| base64 -d")
            if ($b64Match.Success) {
                $b64 = $b64Match.Groups['b64'].Value
                $decoded = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
                $logLines += "  decoded: $decoded"
            }
            $logLines += ""
            Add-Content -Path $logFile -Value $logLines -Encoding UTF8
        } catch {
            # Never let logging failure break a launch.
        }
    }
    else { Write-Warn "$($repo.name): unknown shell '$shell'"; continue }

    Write-Host "  $([char]0x25CF) " -NoNewline -ForegroundColor $cc
    Write-Host "$title" -NoNewline -ForegroundColor $cc
    Write-Host (" ({0})" -f $shell) -ForegroundColor DarkGray
}
}  # end if (-not $useRunnerTabs) — B-41

# Launch Windows Terminal tabs
if ($wtTabs.Count -gt 0) {
    $wtCmd = "wt.exe new-tab $($wtTabs[0])"
    for ($j = 1; $j -lt $wtTabs.Count; $j++) { $wtCmd += " ``; new-tab $($wtTabs[$j])" }

    if ($DryRun) {
        Write-Host "`n--- Windows Terminal command ---" -ForegroundColor DarkGray
        for ($j = 0; $j -lt $wtTabs.Count; $j++) {
            $pfx = if ($j -eq 0) { "  wt.exe new-tab" } else { "       ``; new-tab" }
            Write-Host "$pfx $($wtTabs[$j])" -ForegroundColor DarkGray
        }
    } else {
        # Pass the wt.exe arg string to Start-Process so PowerShell does NOT
        # re-parse it. Invoke-Expression treats `;` as a PS statement separator
        # and splits the command, so only the first new-tab ever ran — every
        # tab after the first was silently dropped. wt.exe's own parser handles
        # `;` correctly as its tab separator when it receives the full arg
        # string verbatim. Strip the leading "wt.exe " literal and forward
        # the rest unchanged.
        $wtArgs = $wtCmd -replace '^wt\.exe\s+', ''
        try {
            Start-Process "wt.exe" -ArgumentList $wtArgs
            Write-Ok "Launched $($wtTabs.Count) WT tab(s)"
        } catch {
            Write-Err "Windows Terminal failed: $_"
        }
    }
}

# Launch PuTTY/KiTTY separate windows
if ($separateWindows.Count -gt 0) {
    foreach ($win in $separateWindows) {
        # For PuTTY: create temp command file, pass via -m
        $tmpFile = [System.IO.Path]::GetTempFileName()
        $win.remoteCmd | Set-Content $tmpFile -Encoding ASCII

        $puttyArgs = $win.args -replace '-m -', "-m `"$tmpFile`""

        if ($DryRun) {
            Write-Host "`n--- $($win.exe) window: $($win.title) ---" -ForegroundColor DarkGray
            Write-Host "  $($win.exe) $puttyArgs" -ForegroundColor DarkGray
            Write-Host "  Remote command: $($win.remoteCmd)" -ForegroundColor DarkGray
        } else {
            try {
                Start-Process $win.exe -ArgumentList $puttyArgs
                Write-Ok "$($win.title) ($($win.exe) window)"
            } catch {
                Write-Err "$($win.title): Failed to launch $($win.exe): $_"
            }
        }
    }
}

if ($wtTabs.Count -eq 0 -and $separateWindows.Count -eq 0) {
    Write-Err "No sessions launched."
    exit 1
}

Write-Host ""
