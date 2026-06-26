#!/usr/bin/env python3
"""Generate .agents/ infrastructure from platform.yaml.

Usage:
    python generate-agent-config.py <path-to-platform.yaml>

Creates:
    .agents/
    ├── bus/
    ├── proposals/
    ├── reviews/pending/
    ├── reviews/done/
    ├── decisions/
    ├── ownership.json
    └── agents.yaml

Also generates per-repo CLAUDE.md with ownership rules (appends if exists).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def _backup_existing(path: Path) -> Path | None:
    """Snapshot an existing file to <path>.bak before overwrite. Returns the
    .bak path if a backup was made, else None.

    Pattern: only one .bak per file (latest pre-overwrite snapshot wins).
    Cheap insurance for .mcp.json / settings.local.json merge logic + the
    malformed-JSON silent-recovery path in the readers above this.
    """
    if not path.exists() or not path.is_file():
        return None
    import shutil
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    return bak


def _phase(label: str, count: int | None = None) -> None:
    """Print a phase header. 2B.2-C: temporal feedback during long inits."""
    if count is not None:
        print(f"\n[*] {label} ({count} repos)...")
    else:
        print(f"\n[*] {label}...")


def load_config(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_directories(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Create .agents/ directory structure. Returns list of created dirs."""
    bus_path = config.get("communication", {}).get("bus_path", ".agents/bus")
    dirs = [
        project_root / ".agents",
        project_root / bus_path,
        project_root / bus_path / "active",
        project_root / bus_path / "active" / "acks",
        project_root / bus_path / "archive",
        project_root / ".agents" / "proposals",
        project_root / ".agents" / "reviews" / "pending",
        project_root / ".agents" / "reviews" / "done",
        project_root / ".agents" / "decisions",
        project_root / ".agents" / "blocked",
        project_root / ".agents" / "queue",
    ]
    created = []
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(str(d.relative_to(project_root)))
    return created


def generate_ownership_json(project_root: Path, config: dict[str, Any]) -> Path:
    """Generate .agents/ownership.json from config."""
    ownership = {
        "project": config["project"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repos": [],
    }
    for repo in config["repos"]:
        entry = {
            "name": repo["name"],
            "path": repo["path"],
            "owner": repo["owner"],
        }
        if repo.get("disabled", False):
            entry["disabled"] = True
        ownership["repos"].append(entry)

    out_path = project_root / ".agents" / "ownership.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ownership, f, indent=2)
    return out_path


def generate_agents_yaml(project_root: Path, config: dict[str, Any]) -> Path:
    """Generate .agents/agents.yaml — registry of all agents."""
    # Collect unique agents from repos
    agents_map: dict[str, dict[str, Any]] = {}
    for repo in config["repos"]:
        owner = repo["owner"]
        if owner not in agents_map:
            agents_map[owner] = {
                "name": owner,
                "role": "developer",
                "owns": [],
            }
        agents_map[owner]["owns"].append(repo["name"])

    # Add observer agents
    for obs in config.get("observers", []):
        role = obs["role"]
        if role not in agents_map:
            agents_map[role] = {
                "name": role,
                "role": "observer",
                "owns": [],
                "triggers": obs.get("triggers", []),
            }

    agents_data = {
        "project": config["project"],
        "agents": list(agents_map.values()),
    }

    out_path = project_root / ".agents" / "agents.yaml"
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(agents_data, f, default_flow_style=False, sort_keys=False)
    return out_path


def generate_queue_files(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Generate starter queue files for each agent. Idempotent — won't overwrite existing."""
    created: list[str] = []
    queue_dir = project_root / ".agents" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)

    agents = set()
    for repo in config.get("repos", []):
        agents.add(repo["owner"])

    for agent in sorted(agents):
        queue_file = queue_dir / f"{agent}.md"
        if queue_file.exists():
            continue  # Don't overwrite existing queue
        queue_file.write_text(
            f"# Task Queue — {agent}\n\n"
            f"## Active\n\n"
            f"_(no active task)_\n\n"
            f"## Queued\n\n"
            f"_(empty)_\n\n"
            f"## Blocked\n\n"
            f"_(none)_\n\n"
            f"## Completed (recent)\n\n"
            f"_(none)_\n",
            encoding="utf-8",
        )
        created.append(f".agents/queue/{agent}.md")

    return created


def generate_repo_claude_md(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Generate or append CLAUDE.md in each repo with ownership rules."""
    warnings: list[str] = []
    all_repos = config["repos"]

    # Build lookup: agent -> list of repo names
    agent_repos: dict[str, list[str]] = defaultdict(list)
    for repo in all_repos:
        agent_repos[repo["owner"]].append(repo["name"])

    bus_path = config.get("communication", {}).get("bus_path", ".agents/bus")

    for repo in all_repos:
        repo_dir = project_root / repo["path"]
        if not repo_dir.exists():
            warnings.append(f"Repo directory does not exist: {repo['path']}")
            continue

        claude_md_path = repo_dir / "CLAUDE.md"
        maestro_block = _build_maestro_block(repo, all_repos, bus_path, config, project_root)

        if claude_md_path.exists():
            existing = claude_md_path.read_text(encoding="utf-8")
            # Recognize both new (otaman:) and legacy (maestro:) markers so  # legacy: pre-rebrand reference
            # existing in-the-wild CLAUDE.md files migrate cleanly on next init.
            if "<!-- otaman:begin -->" in existing or "<!-- maestro:begin -->" in existing:  # legacy: pre-rebrand reference
                import re
                pattern = r"<!-- (?:otaman|maestro):begin -->.*?<!-- (?:otaman|maestro):end -->"  # legacy: pre-rebrand reference
                updated = re.sub(pattern, maestro_block, existing, flags=re.DOTALL)
                claude_md_path.write_text(updated, encoding="utf-8")
            else:
                with open(claude_md_path, "a", encoding="utf-8") as f:
                    f.write("\n\n" + maestro_block + "\n")
        else:
            claude_md_path.write_text(maestro_block + "\n", encoding="utf-8")

    return warnings


def _build_maestro_block(
    repo: dict[str, Any],
    all_repos: list[dict[str, Any]],
    bus_path: str,
    config: dict[str, Any],
    project_root: Path | None = None,
) -> str:
    other_repos = [r for r in all_repos if r["name"] != repo["name"]]
    other_repos_list = "\n".join(
        f"  - {r['name']} ({r['path']}) — owned by **{r['owner']}** (READ-ONLY)"
        for r in other_repos
    )

    # monorepo-path-ownership task 3.1: render an "Owned paths" subsection
    # when this repo declares `owner-paths` and the current agent appears
    # as the owner of at least one glob. Agents who don't claim any path
    # (full-repo owners under the catch-all `owner:`) get no section per
    # design layer 6.
    #
    # Read both the YAML key (`owner-paths`) and the Python-normalized key
    # (`owner_paths`) so this works before AND after otaman-core task 1.1
    # adds the parser-side normalization. Whichever lands first is fine.
    owner_paths_raw = repo.get("owner_paths") or repo.get("owner-paths") or {}
    owned_paths_section = ""
    if isinstance(owner_paths_raw, dict) and owner_paths_raw:
        my_globs = [g for g, agent in owner_paths_raw.items() if agent == repo["owner"]]
        if my_globs:
            glob_list = "\n".join(f"- `{g}`" for g in my_globs)
            owned_paths_section = (
                f"\n\n### Owned paths in {repo['name']}\n\n"
                f"You own the following paths inside `{repo['name']}`:\n"
                f"{glob_list}\n\n"
                "Changes outside these paths require coordination with the owning agent. "
                "Cross-path edits surface at PR review time."
            )

    # Compute relative path from repo to maestro folder for .agents/ references.  # legacy: pre-rebrand reference
    # M = relative path from repo to maestro folder (e.g., "../lmachine-maestro")  # legacy: pre-rebrand reference
    m = ".."  # fallback: assume parent dir
    if project_root:
        repo_dir = (project_root / repo["path"]).resolve()
        try:
            m = Path(os.path.relpath(project_root.resolve(), repo_dir)).as_posix()
        except ValueError:
            m = project_root.resolve().as_posix()

    specs_section = ""
    if "specs" in config:
        specs_path = config["specs"].get("path", "./specs")
        specs_format = config["specs"].get("format", "fallback")
        specs_dirs = repo.get("specs_dir", [])
        if isinstance(specs_dirs, str):
            specs_dirs = [specs_dirs]

        if specs_format == "openspec":
            # Build specific spec paths for this agent
            if specs_dirs:
                my_specs_lines = "\n".join(
                    f"  - `{specs_path}/openspec/specs/{d}/spec.md`"
                    for d in specs_dirs
                )
                my_specs = f"- **Your specs** (read these before implementing):\n{my_specs_lines}"
            else:
                my_specs = f"- Your spec area is not yet mapped — check `{specs_path}/openspec/specs/` for relevant folders"

            specs_section = f"""
### Specs (OpenSpec)
- Specs repo: `{specs_path}` (READ-ONLY)
{my_specs}
- **Shared contracts**: `{specs_path}/openspec/specs/shared-contracts/spec.md` — message schemas, signal classes, security contracts
- **Active changes for you**: scan `{specs_path}/openspec/changes/` for folders whose `tasks.md` references your repo or domain. Read `proposal.md` → `design.md` → `tasks.md` in each.
- **All accumulated specs**: `{specs_path}/openspec/specs/`
- To propose a spec change, use `/otaman:propose` — do NOT modify specs directly

### Spec Change Rules (CRITICAL)
- If you discover a missing endpoint, contract gap, or any spec change needed: run `/otaman:propose`, then **STOP** working on that feature
- **Never implement against a spec that doesn't exist yet** — wait for human approval + spec commit
- After proposing, switch to other tasks. Run `/otaman:check` periodically to see if your proposal was approved
- Resume the blocked task only after you see BOTH `spec-change-approved` AND `spec-change` messages
- Check `{m}/.agents/blocked/{repo['owner']}.md` for your currently blocked tasks"""
        else:
            specs_section = f"""
### Specs
- Specs location: `{specs_path}` (READ-ONLY)
- To change a spec, use `/otaman:propose` — do NOT modify specs directly
- Always read relevant specs before implementing API endpoints or clients

### Spec Change Rules (CRITICAL)
- If you discover a missing endpoint, contract gap, or any spec change needed: run `/otaman:propose`, then **STOP** working on that feature
- **Never implement against a spec that doesn't exist yet** — wait for human approval + spec commit
- After proposing, switch to other tasks. Run `/otaman:check` periodically to see if your proposal was approved
- Resume the blocked task only after you see BOTH `spec-change-approved` AND `spec-change` messages
- Check `{m}/.agents/blocked/{repo['owner']}.md` for your currently blocked tasks"""

    # Build standards section for this repo
    standards_section = ""
    standards_cfg = config.get("standards", {})
    repo_stds = standards_cfg.get("repo_standards", {}).get(repo["name"], {})
    if repo_stds:
        lines = ["\n### Tech Stack & Coding Standards"]
        if repo_stds.get("language"):
            lines.append(f"- **Language**: {repo_stds['language']}")
        if repo_stds.get("framework"):
            lines.append(f"- **Framework**: {repo_stds['framework']}")
        if repo_stds.get("package_manager"):
            lines.append(f"- **Package manager**: {repo_stds['package_manager']} (use this exclusively)")
        if repo_stds.get("styling"):
            lines.append(f"- **Styling**: {repo_stds['styling']}")
        if repo_stds.get("iac"):
            lines.append(f"- **IaC**: {repo_stds['iac']}")
        if repo_stds.get("testing"):
            t = repo_stds["testing"]
            parts = []
            if t.get("unit"):
                parts.append(f"{t['unit']} for unit tests")
            if t.get("e2e"):
                parts.append(f"{t['e2e']} for E2E tests")
            if t.get("coverage_min"):
                parts.append(f"minimum coverage: {t['coverage_min']}%")
            if parts:
                lines.append(f"- **Testing**: {', '.join(parts)}")
        if repo_stds.get("patterns"):
            lines.append(f"- **Patterns**: {', '.join(repo_stds['patterns'])}")
        if repo_stds.get("linting"):
            lines.append(f"- **Linting**: {', '.join(repo_stds['linting'])}")
        if repo_stds.get("rules"):
            lines.append("\n**Project Rules**:")
            for rule in repo_stds["rules"]:
                lines.append(f"- {rule}")
        standards_section = "\n".join(lines)

    # Domain path rules
    domain_rules_section = ""
    domain = config.get("domain", "")
    if domain:
        # Try to load domain-specific path rules
        plugin_root = Path(__file__).resolve().parent.parent.parent  # src/otaman_plugin/X.py → otaman-plugin/
        for rule_domain in (domain, "general"):
            rules_file = plugin_root / "references" / "path-rules" / f"{rule_domain}.yaml"
            if rules_file.exists():
                try:
                    rules_data = yaml.safe_load(rules_file.read_text(encoding="utf-8"))
                    if rules_data and rules_data.get("rules"):
                        lines = [f"\n### Domain Rules ({rule_domain})"]
                        for rule_group in rules_data["rules"]:
                            lines.append(f"\n**Files matching `{rule_group['path']}`**:")
                            for r in rule_group["rules"]:
                                lines.append(f"- {r}")
                        if rule_domain == domain:
                            domain_rules_section = "\n".join(lines)
                except Exception:
                    pass

    # Knowledge gaps (soft blocks)
    knowledge_section = ""
    knowledge_items = config.get("knowledge", [])
    blocked_items = [k for k in knowledge_items if k.get("status") in ("needs_docs", "needs_full_docs")]
    if blocked_items:
        lines = ["\n### Knowledge Gaps (CRITICAL)",
                 "The following technologies have LOW or NO knowledge confidence.",
                 "**DO NOT write implementation code for these without reading the docs first.**\n"]
        for item in blocked_items:
            pack = item.get("pack", "unknown")
            path = item.get("path", f".agents/knowledge/{pack}/")
            lines.append(f"- **{pack}**: Read `{path}` before any related code")
        lines.append("\nIf docs are not available, STOP and inform the human.")
        knowledge_section = "\n".join(lines)

    # Project-wide methodology
    methodology_section = ""
    methodology = standards_cfg.get("methodology", [])
    git_cfg = standards_cfg.get("git", {})
    if methodology or git_cfg:
        lines = []
        if methodology:
            lines.append(f"- **Methodology**: {', '.join(methodology)}")
        if git_cfg.get("branching"):
            lines.append(f"- **Branching**: {git_cfg['branching']}")
        if git_cfg.get("commits"):
            lines.append(f"- **Commits**: {git_cfg['commits']} format")
        if lines:
            methodology_section = "\n".join(lines)

    return f"""<!-- otaman:begin -->
## Otaman Orchestration Rules

**You are `{repo['owner']}`**. You own this repository: **{repo['name']}**.

Otaman folder: `{m}/` (contains `.agents/`, `platform.yaml`, bus messages)

### First Session Checklist
1. Run `otaman check` (Bash) — see pending bus messages. The CLI auto-detects project root, your agent identity, and ack status. No MCP tool-loading needed for this hot path; pre-allowed in `.claude/settings.local.json`.
2. Read `{m}/.agents/queue/{repo['owner']}.md` — see your active/queued/blocked tasks
3. Read specs relevant to your repo (specs_dir paths below)
4. Run `git log --oneline -10` — understand recent changes
5. If `{m}/.agents/knowledge/` exists, check for tech docs relevant to your work
6. Then: resume active task, or pick highest-priority queued task, or act on bus messages

### Ownership
- This repo (`{repo['path']}`) is YOURS — you may read and write freely here
- Other repos (READ-ONLY, do not write to them):
{other_repos_list}
- You may read other repos' source code, configs, and CLAUDE.md to understand their APIs
- If you need a change in another repo, send a `task-assignment` or `question` message to its owner
{owned_paths_section}

### Communication — Bash CLI for hot path, MCP for richer ops

Hot-path commands (frequent, read-mostly) — use the `otaman` Bash CLI, pre-allowed in this repo's settings:
- `otaman check` — list pending messages for you (auto-detects identity)
- `otaman ack <msg-stem>` — acknowledge a message (default: resolved; `--read` keeps it visible)
- `otaman status` — project-wide summary
- `otaman complete <change-name> --all` — mark OpenSpec tasks complete + broadcast task-complete
- `otaman propose <title>` — propose a spec change (pending human approval)
- Read `.agents/queue/<your-agent>.md` directly for your task queue (no CLI subcommand needed)
- Read `.agents/blocked/<your-agent>.md` directly for blocked-task tracking

Richer / less-frequent ops — use MCP tools (load schemas with ToolSearch first when calling directly):
- `otaman_send(cwd, to, subject, body)` — send a message to another agent
- `otaman_read_message(cwd, message_stem)` — read full message content programmatically
- `otaman_propose(cwd, title, what_needs_to_change, why_needed)` — propose a spec change
- `otaman_complete(cwd, change_name, tasks)` — report task completion
- `otaman_read_spec(cwd, spec_path)` — read spec files
- `otaman_list_agents(cwd)`, `otaman_set_agent(cwd, name)`, `otaman_cleanup(cwd)` — agent registry / housekeeping

Why the split: bus checks happen dozens of times per session, and the MCP-via-instruction path proved unreliable across model variants (2026-04-29 incident — see plugin CLAUDE.md). The Bash CLI is deterministic. Heavier write operations stay on MCP because their structured payload is worth the schema-load overhead.

### Bus Awareness (CRITICAL)
- **Check the bus proactively** — do NOT wait for the human to tell you:
  - After completing each task (feature done, test passing)
  - Before starting a new task from your queue
  - When idle or waiting for anything
  - After every 3-5 tool calls during active work
- **Never let pending messages exceed 3 without acting**
- When you change an API or shared type: send `contract-change` via `otaman_send` BEFORE committing
- Message handling while busy: ack as `read`, add to queue, finish current task first
- Urgent messages: pause current work, inform the human immediately

### Outcome Proposals (business-impact ideas)

When you spot a business-impact idea — a pricing change, a process change, a
new outcome the program should pursue — send it as an **outcome-proposal**,
not as `info`:

```
otaman send --type outcome-proposal --to human --subject "<short hook>"
```

Strategic agents (cofounder-agent, cpo-agent, and any others named in the
project's `bus.routing_rules`) are auto-notified via CC — you do not list
them manually. The primary delivery stays addressed to `human` for sign-off.

- Use this type whenever your subject mentions business impact, a proposed
  outcome, a market move, or a structural change to how the program is run.
- Do **not** use `--type info` for outcome statements; they get lost in the
  general bus noise and skip the strategic CC fan-out.
- Implementation tasks, status updates, and routine FYIs stay on `info` /
  `question` / `task-complete` as before.

### Agent Status (REQUIRED)

Before writing any code for a specific task, call:
```
otaman set-status working --task "<N.M task description>" --change <change-name>
```

When waiting on another agent or a dependency:
```
otaman set-status waiting --task "<N.M ...>" --change <change-name>
```

When done with all current tasks:
```
otaman set-status idle
```

This is a single CLI call — no file editing, no token overhead. It lets the human see live fleet state in `otaman status` and in `otaman check`. Per `agent-status-presence` design Q3.

### Task Queue
- Your queue file: `{m}/.agents/queue/{repo['owner']}.md`
- Max 1 active task at a time — finish or pause before switching
- When a `task-assignment` arrives while you're busy: ack as `read`, add to Queued section
- When you finish a task: check bus, then pick highest-priority queued item
- Urgent messages override: pause active task, handle urgent item

### Task Completion Reporting (CRITICAL)
- When you finish tasks from a `task-assignment`, you MUST report completion:
  - `otaman complete <change-name> --tasks "2.1, 2.3"` (specific tasks)
  - `otaman complete <change-name> --all` (all tasks for that change)
- This sends a `task-complete` bus message; spec-agent applies the
  `tasks.md` tick asynchronously on next session start. You do NOT need
  to commit to `otaman-specs` yourself — that repo is read-only for every
  agent except spec-agent, so any local working-tree edit would be
  silently reverted on the next `git pull`. Output line
  `spec-agent will tick tasks.md on next session start` is the success
  signal, not an error. (Per `fix-otaman-complete-task-drift`.)
- **Lifecycle**: task-assignment received -> ack "read" -> implement -> `otaman complete` -> ack "resolved"
- NEVER ack a task-assignment as "resolved" without first running `otaman complete`
{specs_section}
{standards_section}
{methodology_section}
{domain_rules_section}
{knowledge_section}

### Git Workflow
- Work in branches: `agent/{repo['owner']}/{{feature-name}}`
- All changes go through PRs
- Write clear commit messages for the audit trail
<!-- otaman:end -->"""


def install_spec_change_hook(project_root: Path, config: dict[str, Any]) -> str | None:
    """Install post-commit hook in the specs repo to notify agents of spec changes.

    Returns a status message, or None if not applicable.
    """
    specs = config.get("specs", {})
    specs_path_str = specs.get("path")
    if not specs_path_str:
        return None

    specs_dir = project_root / specs_path_str
    if not specs_dir.is_dir():
        return f"WARNING: Specs repo not found at {specs_path_str}, skipping hook install"

    git_dir = specs_dir / ".git"
    if not git_dir.is_dir():
        return f"WARNING: {specs_path_str} has no .git/, skipping spec-change hook"

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_target = hooks_dir / "post-commit"
    hook_source = Path(__file__).resolve().parent.parent.parent / "scripts" / "spec-change-hook.sh"

    if not hook_source.exists():
        return f"WARNING: spec-change-hook.sh not found at {hook_source}"

    # If there's an existing post-commit hook, chain ours after it
    if hook_target.exists():
        existing = hook_target.read_text(encoding="utf-8")
        marker = "# maestro:spec-change-hook"  # legacy: pre-rebrand reference
        if marker in existing:
            # Already installed, update in place
            import re
            pattern = rf"{re.escape(marker)}:begin.*?{re.escape(marker)}:end"
            hook_call = _spec_hook_call_block(hook_source, marker)
            if re.search(pattern, existing, re.DOTALL):
                updated = re.sub(pattern, hook_call, existing, flags=re.DOTALL)
            else:
                updated = existing  # marker present but not in begin/end format, skip
            hook_target.write_text(updated, encoding="utf-8")
            return f"Updated spec-change hook in {specs_path_str}/.git/hooks/post-commit"
        else:
            # Append our hook call
            hook_call = _spec_hook_call_block(hook_source, marker)
            with open(hook_target, "a", encoding="utf-8") as f:
                f.write("\n" + hook_call + "\n")
            return f"Appended spec-change hook to existing {specs_path_str}/.git/hooks/post-commit"
    else:
        # Create new post-commit hook
        marker = "# maestro:spec-change-hook"  # legacy: pre-rebrand reference
        hook_call = _spec_hook_call_block(hook_source, marker)
        content = f"#!/usr/bin/env bash\nset -euo pipefail\n\n{hook_call}\n"
        hook_target.write_text(content, encoding="utf-8")
        # Make executable on Unix
        try:
            hook_target.chmod(0o755)
        except OSError:
            pass
        return f"Installed spec-change hook in {specs_path_str}/.git/hooks/post-commit"


def _spec_hook_call_block(hook_source: Path, marker: str) -> str:
    """Build the bash block that calls our spec-change hook."""
    # Use portable path: resolve relative to the hook location at runtime
    source_posix = hook_source.as_posix()
    return f"""{marker}:begin
# Maestro: notify agents when specs change  # legacy: pre-rebrand reference
if [ -f "{source_posix}" ]; then
    bash "{source_posix}" || true
fi
{marker}:end"""


def install_repo_post_commit_hooks(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Install post-commit hook in all non-specs repos to notify bus on commits.

    Returns list of status messages.
    """
    results: list[str] = []
    specs_path = config.get("specs", {}).get("path", "")
    hook_source = Path(__file__).resolve().parent.parent.parent / "scripts" / "post-commit-hook.sh"

    if not hook_source.exists():
        results.append(f"WARNING: post-commit-hook.sh not found at {hook_source}")
        return results

    for repo in config["repos"]:
        repo_path_str = repo["path"]
        # Skip the specs repo — it has its own spec-change-hook
        if specs_path and repo_path_str.rstrip("/") == specs_path.rstrip("/"):
            continue

        repo_dir = project_root / repo_path_str
        if not repo_dir.is_dir():
            continue

        git_dir = repo_dir / ".git"
        if not git_dir.is_dir():
            continue

        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        hook_target = hooks_dir / "post-commit"
        marker = "# maestro:post-commit-hook"  # legacy: pre-rebrand reference
        hook_call = _repo_hook_call_block(hook_source, marker)

        if hook_target.exists():
            existing = hook_target.read_text(encoding="utf-8")
            if marker in existing:
                # Already installed, update in place
                import re
                pattern = rf"{re.escape(marker)}:begin.*?{re.escape(marker)}:end"
                if re.search(pattern, existing, re.DOTALL):
                    updated = re.sub(pattern, hook_call, existing, flags=re.DOTALL)
                    hook_target.write_text(updated, encoding="utf-8")
                    results.append(f"Updated post-commit hook in {repo['name']}")
                # else: marker present but not in begin/end format, skip
            else:
                # Append our hook call
                with open(hook_target, "a", encoding="utf-8") as f:
                    f.write("\n" + hook_call + "\n")
                results.append(f"Appended post-commit hook to existing {repo['name']}/.git/hooks/post-commit")
        else:
            content = f"#!/usr/bin/env bash\nset -euo pipefail\n\n{hook_call}\n"
            hook_target.write_text(content, encoding="utf-8")
            try:
                hook_target.chmod(0o755)
            except OSError:
                pass
            results.append(f"Installed post-commit hook in {repo['name']}")

    return results


def _repo_hook_call_block(hook_source: Path, marker: str) -> str:
    """Build the bash block that calls the repo post-commit hook."""
    source_posix = hook_source.as_posix()
    return f"""{marker}:begin
# Maestro: notify bus on commits (triggers observer reviews)  # legacy: pre-rebrand reference
if [ -f "{source_posix}" ]; then
    bash "{source_posix}" || true
fi
{marker}:end"""


def install_pre_commit_hooks(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Install pre-commit hooks in all repos for branch protection.

    Blocks commits to protected branches (main/master/develop) and
    warns about non-standard branch naming.
    """
    results: list[str] = []
    hook_source = Path(__file__).resolve().parent.parent.parent / "scripts" / "check-branch.sh"

    if not hook_source.exists():
        results.append(f"WARNING: check-branch.sh not found at {hook_source}")
        return results

    source_posix = hook_source.as_posix()
    marker = "# maestro:pre-commit-hook"  # legacy: pre-rebrand reference
    # Critical: exit $? propagates failure (blocks commit), unlike post-commit which uses || true
    hook_call = f"""{marker}:begin
# Maestro: enforce branch naming and protected branches  # legacy: pre-rebrand reference
if [ -f "{source_posix}" ]; then
    bash "{source_posix}"
    _maestro_rc=$?
    if [ "$_maestro_rc" -ne 0 ]; then exit $_maestro_rc; fi
fi
{marker}:end"""

    for repo in config["repos"]:
        repo_dir = project_root / repo["path"]
        if not repo_dir.is_dir():
            continue

        git_dir = repo_dir / ".git"
        if not git_dir.is_dir():
            continue

        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        hook_target = hooks_dir / "pre-commit"

        if hook_target.exists():
            existing = hook_target.read_text(encoding="utf-8")
            if marker in existing:
                import re
                pattern = rf"{re.escape(marker)}:begin.*?{re.escape(marker)}:end"
                if re.search(pattern, existing, re.DOTALL):
                    updated = re.sub(pattern, hook_call, existing, flags=re.DOTALL)
                    hook_target.write_text(updated, encoding="utf-8")
                    results.append(f"Updated pre-commit hook in {repo['name']}")
            else:
                with open(hook_target, "a", encoding="utf-8") as f:
                    f.write("\n" + hook_call + "\n")
                results.append(f"Appended pre-commit hook in {repo['name']}")
        else:
            content = f"#!/usr/bin/env bash\nset -euo pipefail\n\n{hook_call}\n"
            hook_target.write_text(content, encoding="utf-8")
            try:
                hook_target.chmod(0o755)
            except OSError:
                pass
            results.append(f"Installed pre-commit hook in {repo['name']}")

    return results


def install_mcp_config(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Write .mcp.json in each repo so MCP tools are available.

    When the plugin is installed from the catalog, Claude Code auto-discovers
    MCP servers via ${CLAUDE_PLUGIN_ROOT} in the plugin's .mcp.json — no
    per-repo config needed. This function is only needed for local development
    (--plugin-dir) where the plugin path isn't managed by Claude Code.

    Uses relative paths from each repo to the plugin's server scripts,
    making configs portable across machines and developers.
    """
    results: list[str] = []
    plugin_root = Path(__file__).resolve().parent.parent.parent  # src/otaman_plugin/X.py → otaman-plugin/
    run_server = plugin_root / "servers" / "run-server.sh"

    # Skip if plugin is catalog-installed (CLAUDE_PLUGIN_ROOT is set by Claude Code)
    # In that case, the plugin's own .mcp.json with ${CLAUDE_PLUGIN_ROOT} works natively.
    if os.environ.get("CLAUDE_PLUGIN_ROOT") and not os.environ.get("OTAMAN_FORCE_MCP_INSTALL"):
        results.append("Skipping .mcp.json install (plugin loaded from catalog)")
        return results

    if not run_server.exists():
        results.append(f"WARNING: run-server.sh not found at {run_server}")
        return results

    for repo in config["repos"]:
        repo_dir = (project_root / repo["path"]).resolve()
        if not repo_dir.is_dir():
            continue

        # Skip the plugin's own repo: it ships its own canonical .mcp.json with
        # ${CLAUDE_PLUGIN_ROOT} paths (loaded when Claude Code reads it as a
        # plugin config via --plugin-dir / catalog). Overwriting it with bare
        # relative paths breaks the plugin-context load — "2 MCP servers failed"
        # in every tab. (Backlog M-2.)
        if repo_dir == plugin_root.resolve():
            results.append(f"{repo['name']}: skipped (plugin repo ships its own .mcp.json)")
            continue

        # Compute relative path from repo to run-server.sh
        try:
            rel = Path(os.path.relpath(run_server.resolve(), repo_dir)).as_posix()
        except ValueError:
            # Different drives on Windows — fall back to absolute
            rel = run_server.resolve().as_posix()

        mcp_config = {
            "mcpServers": {
                "otaman-bus": {
                    "command": "bash",
                    "args": [rel, "bus_server.py"],
                    "env": {"PYTHONUNBUFFERED": "1"},
                },
                "otaman-estimation": {
                    "command": "bash",
                    "args": [rel, "estimation_server.py"],
                    "env": {"PYTHONUNBUFFERED": "1"},
                },
            }
        }

        mcp_path = repo_dir / ".mcp.json"

        # Check if .mcp.json exists with non-otaman servers — preserve them
        existing_servers: dict[str, Any] = {}
        if mcp_path.exists():
            try:
                with open(mcp_path, encoding="utf-8") as f:
                    existing = json.load(f)
                existing_servers = existing.get("mcpServers", {})
            except (json.JSONDecodeError, OSError):
                pass

        # Merge: keep existing non-otaman servers, add/update both otaman
        # servers. Drop legacy maestro-* keys from prior pre-rebrand inits.  # legacy: pre-rebrand reference
        LEGACY = {"maestro-bus", "maestro-estimation"}  # legacy: pre-rebrand reference
        merged = {k: v for k, v in existing_servers.items() if k not in LEGACY}
        merged["otaman-bus"] = mcp_config["mcpServers"]["otaman-bus"]
        merged["otaman-estimation"] = mcp_config["mcpServers"]["otaman-estimation"]

        _backup_existing(mcp_path)
        with open(mcp_path, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": merged}, f, indent=2)
            f.write("\n")

        if existing_servers:
            results.append(f"{repo['name']}: updated .mcp.json (merged with existing)")
        else:
            results.append(f"{repo['name']}: created .mcp.json")

    return results


def generate_repo_settings(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Create or update .claude/settings.local.json with maestro permissions.  # legacy: pre-rebrand reference

    Adds safe read-only permissions so agents aren't prompted for common bus ops.
    Preserves any existing permissions the user has already configured.
    """
    results: list[str] = []
    bus_path_rel = config.get("communication", {}).get("bus_path", ".agents/bus")

    # Common safe permission patterns (read-only bus ops + git + maestro CLI).  # legacy: pre-rebrand reference
    # The maestro CLI entries are what /otaman:check and friends rely on after  # legacy: pre-rebrand reference
    # the 2026-04-29 shift to bash-driven hot-path commands (see CLAUDE.md).
    maestro_permissions = [
        "Bash(git log:*)",
        "Bash(git status:*)",
        "Bash(git diff:*)",
        "Bash(git branch:*)",
        "Bash(git checkout:*)",
        "Bash(git add:*)",
        # otaman + maestro (legacy alias) — wildcards cover all subcommands  # legacy: pre-rebrand reference
        # without enumerating each. Both bare-name + full-path forms because
        # Claude Code matches against literal command-prefix.
        "Bash(otaman:*)",
        "Bash(maestro:*)",  # legacy: pre-rebrand reference
        "Bash(/home/*/.local/bin/otaman:*)",
        "Bash(/home/*/.local/bin/maestro:*)",  # legacy: pre-rebrand reference
        "Bash(/usr/local/bin/otaman:*)",
        "Bash(/usr/local/bin/maestro:*)",  # legacy: pre-rebrand reference
    ]

    for repo in config["repos"]:
        repo_dir = project_root / repo["path"]
        if not repo_dir.is_dir():
            continue

        claude_dir = repo_dir / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)

        settings_path = claude_dir / "settings.local.json"
        existing: dict[str, Any] = {}

        if settings_path.exists():
            try:
                with open(settings_path, encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = {}

        perms = existing.setdefault("permissions", {})
        allow_list: list[str] = perms.get("allow", [])

        added = 0
        for perm in maestro_permissions:
            if perm not in allow_list:
                allow_list.append(perm)
                added += 1

        if added > 0:
            perms["allow"] = allow_list
            existing["permissions"] = perms
            _backup_existing(settings_path)
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
                f.write("\n")
            results.append(f"{repo['name']}: added {added} permission(s) to .claude/settings.local.json")

    return results


def install_maestro_markers(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Write .maestro marker files in each managed repo pointing back to the maestro folder.  # legacy: pre-rebrand reference

    Also appends .otaman to each repo's .gitignore if not already present.
    Returns list of status messages.
    """
    results: list[str] = []
    expected_account = (config.get("account") or "").strip() or None
    for repo in config["repos"]:
        repo_dir = (project_root / repo["path"]).resolve()
        if not repo_dir.is_dir():
            results.append(f"WARNING: Repo not found: {repo['path']}, skipping .maestro marker")  # legacy: pre-rebrand reference
            continue

        # Compute relative path from repo to maestro folder  # legacy: pre-rebrand reference
        try:
            rel = os.path.relpath(project_root.resolve(), repo_dir)
            rel_posix = Path(rel).as_posix()
        except ValueError:
            rel_posix = project_root.resolve().as_posix()

        # Write .maestro marker  # legacy: pre-rebrand reference
        marker = repo_dir / ".otaman"
        lines = [
            "# Path to maestro folder (relative to this repo root)",  # legacy: pre-rebrand reference
            "# Written by maestro init — do not edit manually",  # legacy: pre-rebrand reference
            rel_posix,
        ]
        if expected_account:
            lines.append(f"expected_account: {expected_account}")
        marker.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if expected_account:
            results.append(
                f"Marker: {repo['name']}/.otaman -> {rel_posix} "
                f"(expected_account={expected_account})"
            )
        else:
            results.append(f"Marker: {repo['name']}/.otaman -> {rel_posix}")

        # Append .otaman to repo's .gitignore if not already there
        gitignore = repo_dir / ".gitignore"
        marker_entry = ".otaman"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            if marker_entry not in content.splitlines():
                with open(gitignore, "a", encoding="utf-8") as f:
                    if not content.endswith("\n"):
                        f.write("\n")
                    f.write(f"\n# Maestro marker file (local pointer to maestro folder)\n")  # legacy: pre-rebrand reference
                    f.write(f"{marker_entry}\n")
                results.append(f"Updated: {repo['name']}/.gitignore (added .otaman)")
        else:
            gitignore.write_text(
                f"# Maestro marker file (local pointer to maestro folder)\n"  # legacy: pre-rebrand reference
                f"{marker_entry}\n",
                encoding="utf-8",
            )
            results.append(f"Created: {repo['name']}/.gitignore (with .otaman)")

    return results


def install_secrets_infra(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Ensure .otaman/ runtime dir, secrets.env.example stub, and gitignore entry.

    The maestro folder houses ``.otaman/secrets.env`` for local secret storage  # legacy: pre-rebrand reference
    (gitignored, mode 0600). The ``.example`` stub is committed and documents
    the expected keys.
    """
    results: list[str] = []
    runtime_dir = project_root / ".otaman"
    runtime_dir.mkdir(exist_ok=True)

    # Emit .otaman/secrets.env.example if absent. Don't clobber existing stubs
    # — the user may have added project-specific keys.
    example_path = runtime_dir / "secrets.env.example"
    if not example_path.exists():
        example_path.write_text(
            "# .otaman/secrets.env.example — template for maestro secrets\n"  # legacy: pre-rebrand reference
            "#\n"
            "# Copy to .otaman/secrets.env and fill in real values.\n"
            "# The real file is gitignored — NEVER commit populated secrets.\n"
            "#\n"
            "# Secrets are also resolvable via process env or OS keychain; see\n"
            "# scripts/_secrets.py for the full source chain.\n"
            "#\n"
            "# --- Telegram bridge (Phase T2+) ---\n"
            "# OTAMAN_TG_BOT_PERSONAL=\n"
            "# OTAMAN_TG_BOT_RISEAPPS=\n"
            "#\n"
            "# --- Git host / PM tool PATs (backlog) ---\n"
            "# OTAMAN_GITHUB_PAT=\n"
            "# OTAMAN_LINEAR_PAT=\n",
            encoding="utf-8",
        )
        results.append("Created: .otaman/secrets.env.example")

    # If a real secrets.env exists, enforce 0600 on POSIX. Windows best-effort.
    secrets_path = runtime_dir / "secrets.env"
    if secrets_path.is_file() and os.name == "posix":
        try:
            secrets_path.chmod(0o600)
        except OSError:
            pass

    # Ensure maestro folder's .gitignore covers .otaman/secrets.env.  # legacy: pre-rebrand reference
    # Also include .otaman/bridge-*.endpoint and .otaman/afk which show up
    # in later phases — cheap to preempt now.
    entries_needed = [
        ".otaman/secrets.env",
        ".otaman/bridge-*.endpoint",
        ".otaman/afk",
    ]
    gitignore = project_root / ".gitignore"
    if gitignore.exists():
        existing_lines = {
            ln.strip() for ln in gitignore.read_text(encoding="utf-8").splitlines()
        }
        missing = [e for e in entries_needed if e not in existing_lines]
        if missing:
            with open(gitignore, "a", encoding="utf-8") as f:
                existing = gitignore.read_text(encoding="utf-8")
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write("\n# Maestro runtime state (secrets, bridge sockets, AFK flag)\n")  # legacy: pre-rebrand reference
                for e in missing:
                    f.write(f"{e}\n")
            results.append(
                f"Updated: .gitignore (+{len(missing)} entries for .otaman/ runtime)"
            )
    else:
        gitignore.write_text(
            "# Maestro runtime state (secrets, bridge sockets, AFK flag)\n"  # legacy: pre-rebrand reference
            + "\n".join(entries_needed) + "\n",
            encoding="utf-8",
        )
        results.append("Created: .gitignore (maestro runtime entries)")  # legacy: pre-rebrand reference

    return results


def main() -> int:
    # 2B.2-A: dry-run early return. Full per-write gating in 2B.2-B.
    import sys as _sys
    if "--dry-run" in _sys.argv:
        print("  [dry-run] generate-agent-config: skipping all writes")
        print("  [dry-run] would generate: .agents/, ownership.json, queue files,")
        print("  [dry-run]                 per-repo CLAUDE.md, .mcp.json, .claude/,")
        print("  [dry-run]                 .otaman marker, hooks, .gitignore")
        print("  [dry-run] re-run without --dry-run to apply")
        return 0
    if len(sys.argv) < 2:
        print("Usage: generate-agent-config.py <path-to-platform.yaml>", file=sys.stderr)
        return 2

    config_path = Path(sys.argv[1]).resolve()
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}", file=sys.stderr)
        return 2

    config = load_config(config_path)
    project_root = config_path.parent

    # Python version check
    import platform as plat
    py_ver = tuple(int(x) for x in plat.python_version().split(".")[:2])
    if py_ver < (3, 10):
        print(f"WARNING: Python 3.10+ recommended (you have {plat.python_version()})", file=sys.stderr)

    # Create directories
    created_dirs = create_directories(project_root, config)
    if created_dirs:
        print(f"Created directories: {', '.join(created_dirs)}")

    _phase("Initializing .agents state")
    # Generate ownership.json
    ownership_path = generate_ownership_json(project_root, config)
    print(f"Generated: {ownership_path.relative_to(project_root)}")

    # Generate agents.yaml
    agents_path = generate_agents_yaml(project_root, config)
    print(f"Generated: {agents_path.relative_to(project_root)}")

    # Generate agent task queue files
    queue_created = generate_queue_files(project_root, config)
    for q in queue_created:
        print(f"Created: {q}")

    _phase("Writing per-repo CLAUDE.md", count=len(config["repos"]))
    # Generate per-repo CLAUDE.md
    warnings = generate_repo_claude_md(project_root, config)
    for w in warnings:
        print(f"WARNING: {w}")

    _phase("Writing per-repo .otaman markers", count=len(config["repos"]))
    # Write .maestro marker files in each repo (pointing back to maestro folder)  # legacy: pre-rebrand reference
    marker_results = install_maestro_markers(project_root, config)
    for r in marker_results:
        print(r)

    # Ensure .otaman/ runtime dir, secrets.env.example, gitignore entries
    secrets_results = install_secrets_infra(project_root, config)
    for r in secrets_results:
        print(r)

    _phase("Installing per-repo .mcp.json (MCP server config)", count=len(config["repos"]))
    # Install .mcp.json in each repo (enables MCP tools without bash)
    mcp_results = install_mcp_config(project_root, config)
    for r in mcp_results:
        print(r)

    _phase("Updating per-repo .claude/settings.local.json (permissions)", count=len(config["repos"]))
    settings_results = generate_repo_settings(project_root, config)
    for r in settings_results:
        print(r)

    # Install spec-change hook in specs repo
    hook_result = install_spec_change_hook(project_root, config)
    if hook_result:
        print(hook_result)

    _phase("Installing per-repo post-commit hooks", count=len(config["repos"]))
    # Install post-commit hooks in all non-specs repos
    repo_hook_results = install_repo_post_commit_hooks(project_root, config)
    for r in repo_hook_results:
        print(r)

    # Install pre-commit hooks (branch protection)
    pre_commit_results = install_pre_commit_hooks(project_root, config)
    for r in pre_commit_results:
        print(r)

    # Migrate flat bus messages to active/ and run cleanup
    bus_path = config.get("communication", {}).get("bus_path", ".agents/bus")
    bus_dir = project_root / bus_path
    if bus_dir.is_dir():
        # cleanup-bus.py was carved into otaman-cli during Stage 4E.
        from otaman_cli.cleanup_bus import migrate_flat_to_active, cleanup as _cleanup_run
        migrated = migrate_flat_to_active(bus_dir)
        if migrated:
            print(f"Migrated {migrated} bus message(s) to {bus_path}/active/")
        report = _cleanup_run(project_root)
        if report.get("archived"):
            print(f"Archived {len(report['archived'])} old bus message(s)")

    # Summary
    agents = set(r["owner"] for r in config["repos"])
    observers = [o["role"] for o in config.get("observers", [])]
    print(f"\nProject: {config['project']}")
    print(f"Repos: {len(config['repos'])}")
    print(f"Agents: {', '.join(sorted(agents))}")
    if observers:
        print(f"Observers: {', '.join(observers)}")
    print("\nDone. Run /otaman:check to see if any messages are waiting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
