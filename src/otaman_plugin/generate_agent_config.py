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

Also writes per-repo orchestration rules to a gitignored CLAUDE.local.md
(never the committed CLAUDE.md; Claude Code auto-loads it after CLAUDE.md).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def _find_plugin_script(rel_path: str) -> Path | None:
    """Locate a helper script that ships with otaman-plugin.

    Hook + MCP-server shell scripts live at the plugin-tree top level in
    source (`<plugin>/scripts/`, `<plugin>/servers/`). For wheel installs,
    pyproject.toml force-includes them at the package-internal location
    (`<package>/scripts/`, `<package>/servers/`) so they survive `pip install`.

    This helper tries the package-internal path first (matches wheel/pipx
    installs) and falls back to walking two levels up from this module
    (matches the editable / dev-tree install where scripts are at the
    plugin root).

    Args:
        rel_path: path relative to the plugin root, e.g. "scripts/post-commit-hook.sh"
                  or "servers/run-server.sh"

    Returns:
        Path to the script, or None if neither location has it.
    """
    here = Path(__file__).resolve().parent
    # Wheel/pipx install: scripts copied into the package via force-include
    pkg_path = here / rel_path
    if pkg_path.is_file():
        return pkg_path
    # Editable / dev-tree install: scripts at the plugin root
    # (src/otaman_plugin/<this>.py → ../../<rel_path>)
    dev_path = here.parent.parent / rel_path
    if dev_path.is_file():
        return dev_path
    return None


def _backup_existing(path: Path) -> Path | None:
    """Snapshot an existing file to <path>.bak before overwrite. Returns the
    .bak path if a backup was made, else None.

    Pattern: only one .bak per file (latest pre-overwrite snapshot wins).
    Cheap insurance for .mcp.json / settings.local.json merge logic + the
    malformed-JSON silent-recovery path in the readers above this.
    """
    if not path.exists() or not path.is_file():
        return None
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


# Matches an otaman/maestro-managed block plus surrounding blank lines (legacy: maestro markers),
# so stripping it doesn't leave a run of empty lines behind.
_MANAGED_BLOCK_RE = re.compile(
    r"\n*<!-- (?:otaman|maestro):begin -->.*?<!-- (?:otaman|maestro):end -->\n*",  # legacy: maestro markers
    re.DOTALL,
)


def generate_repo_claude_md(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Write each repo's private orchestration rules to a gitignored CLAUDE.local.md.

    Mechanism change (external-audit remediation, spec-agent 20260818T143518;
    Roman-caught ordering trap): the private orchestration block is NEVER
    written into the committed ``CLAUDE.md`` any more. It goes to
    ``CLAUDE.local.md`` — a gitignored, per-project file Claude Code
    auto-loads *after* ``CLAUDE.md`` (verified: memory.md; loads without an
    ``@import`` line). Chosen over the proposed ``@import`` of a gitignored
    file because Claude Code's behavior for a *missing* ``@import`` target is
    unspecified (external-contributor risk), whereas a missing
    ``CLAUDE.local.md`` degrades gracefully by construction — it is simply
    absent and the public ``CLAUDE.md`` still loads. This permanently kills
    the inline-injection pull-conflict / rule-leak class.

    UPSTREAM-DEPENDENCY WATCH (spec-agent 20260818T150407): CLAUDE.local.md
    auto-loading is a Claude Code behavior that has been described as
    soft-deprecated in favor of imports at points. It is verified working
    today (memory.md + core-agent's pilot check "CLAUDE.local.md still
    auto-loads"). Because the generator owns this in ONE place, if a future
    Claude Code drops auto-loading we swap to @import (by then hopefully
    specified) here without touching any repo. Any pilot/doctor check
    guarding the mechanism SHOULD assert the local rules actually load, so an
    upgrade cannot silently orphan them.

    On each run:
      1. (Re)write the orchestration block into ``CLAUDE.local.md``.
      2. Migrate: if a legacy injected block still sits in ``CLAUDE.md``,
         strip it (content now lives in ``CLAUDE.local.md``), preserving any
         surrounding public content. A CLAUDE.md that is ONLY the block
         (not-yet-sanitized repo) is left untouched for the owner's separate
         sanitize commit — the rules are already safe in ``CLAUDE.local.md``,
         so nothing is lost either way.
      3. Never create or append the block into ``CLAUDE.md``.
    """
    warnings: list[str] = []
    all_repos = config["repos"]
    bus_path = config.get("communication", {}).get("bus_path", ".agents/bus")

    for repo in all_repos:
        repo_dir = project_root / repo["path"]
        if not repo_dir.exists():
            warnings.append(f"Repo directory does not exist: {repo['path']}")
            continue

        block = _build_maestro_block(repo, all_repos, bus_path, config, project_root)

        # 1. Write the block into CLAUDE.local.md (gitignored, generator-owned).
        #    Idempotent: replace an existing managed block, else append (so a
        #    human's own CLAUDE.local.md notes survive), else create.
        local_path = repo_dir / "CLAUDE.local.md"
        if local_path.exists():
            existing_local = local_path.read_text(encoding="utf-8")
            if _MANAGED_BLOCK_RE.search(existing_local):
                updated_local = _MANAGED_BLOCK_RE.sub("\n" + block + "\n", existing_local)
            else:
                updated_local = existing_local.rstrip("\n") + "\n\n" + block + "\n"
            local_path.write_text(updated_local, encoding="utf-8")
        else:
            local_path.write_text(block + "\n", encoding="utf-8")

        # 2. Migrate any legacy inline block out of CLAUDE.md.
        claude_md_path = repo_dir / "CLAUDE.md"
        if claude_md_path.exists():
            existing = claude_md_path.read_text(encoding="utf-8")
            if _MANAGED_BLOCK_RE.search(existing):
                remainder = _MANAGED_BLOCK_RE.sub("\n", existing).strip()
                if remainder:
                    # Public content wrapped the block — keep it, drop the block.
                    claude_md_path.write_text(remainder + "\n", encoding="utf-8")
                # else: file was only the block — leave for the owner's sanitize.

    return warnings


# Spec-authoring guard — part of the scaffold TEMPLATE so re-syncs preserve it.
# History: originally added to bridge's CLAUDE.md by hand (their PR #14) inside
# the otaman:begin/end managed block; the July scaffold re-sync silently dropped
# it because the template itself never contained it (re-landed by bridge PR #44;
# templated here per cofounder-agent task 20260816T202237).
_SPEC_AUTHORING_GUARD = """### Spec Authoring — NOT your job (CRITICAL)
- **spec-agent authors ALL spec artifacts** — `proposal.md`, `design.md`, `tasks.md`, `specs/*/spec.md`, JSON schemas, ADRs. These live in `otaman-specs` which is READ-ONLY for you.
- **Your only spec action is `/otaman:propose`** — you describe what you need, spec-agent writes it.
- **After approval + spec-change notification**: wait for `task-assignment` messages addressed to you from the mapped `tasks.md`. Those tasks will be **implementation work in your repo**, not spec authoring.
- **Never write**: `proposal.md`, `design.md`, `tasks.md`, `spec.md`, ADR files, or any file under `otaman-specs/openspec/`. Even after approval. Even if you think it would be faster.
- If you feel the urge to "just fill in the spec myself" — stop, send a `question` message to spec-agent instead."""


def _read_marker_path(repo_dir: Path) -> str | None:
    """Read the otaman-folder path from a repo's ``.otaman``/``.maestro`` marker.  # legacy: .maestro supported

    Returns the marker's relative path ONLY when it resolves to a real
    otaman root (platform.yaml or .agents/ present) from *repo_dir* —
    a stale marker falls through to the caller's relpath computation
    rather than baking a broken path into the generated docs.
    """
    for name in (".otaman", ".maestro"):  # legacy: .maestro marker supported
        marker = repo_dir / name
        if not marker.is_file():
            continue
        try:
            text = marker.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(("maestro_root:", "otaman_root:")):  # legacy: maestro_root key
                line = line.split(":", 1)[1].strip()
            elif ":" in line.split(" ")[0]:
                continue  # other `key: value` fields (agent:, expected_account:, ...)
            if not line:
                continue
            candidate = (repo_dir / line).resolve() if not Path(line).is_absolute() else Path(line)
            if (candidate / "platform.yaml").exists() or (candidate / ".agents").is_dir():
                return Path(line).as_posix()
            return None  # marker present but stale — let relpath decide
    return None


def _render_connection_inventory(
    connections: list[Any], checks: dict[str, str] | None = None
) -> str:
    """agent-credential-access 2.1: render the resolved connection inventory
    into the always-loaded CLAUDE.local.md block.

    Compaction-durable by construction: this lands in the generator-owned,
    gitignored CLAUDE.local.md that Claude Code reloads every session, so an
    agent keeps seeing WHERE its credentials live even after context
    compaction — which ssh Host, which backend key, at which scope.

    Values are NEVER rendered. ``secret_ref`` is a secret-backend key NAME and
    ``ssh_ref`` is an ``~/.ssh/config`` Host alias / socket handle — both are
    locators, resolved at use time, never inlined into the bus or context. The
    ``Connection`` model (otaman-core, frozen contract 20260824T164952) carries
    no value-bearing field, so there is nothing here to leak. ``last-check`` is
    joined on ``name`` from the last persisted check report (``checks`` map,
    ``{name: "status · checked_at"}``) and renders ``—`` when no report exists.

    Takes any objects exposing ``name/type/endpoint/scope/secret_ref/ssh_ref``
    (duck-typed so tests need not import the core dataclass). Returns "" for an
    empty inventory so CLAUDE.local.md stays clean when nothing is configured.
    """
    if not connections:
        return ""
    checks = checks or {}
    rows = "\n".join(
        f"| {c.name} | {c.type} | {c.endpoint} | {c.scope} | "
        f"{getattr(c, 'secret_ref', None) or '—'} | "
        f"{getattr(c, 'ssh_ref', None) or '—'} | {checks.get(c.name, '—')} |"
        for c in sorted(connections, key=lambda c: (c.scope, c.name))
    )
    return f"""

### Connections & credentials (resolved inventory — locators only, NEVER values)

Where THIS agent's credentials live, resolved tenant → org → program (nearest
scope wins per name). `secret_ref` / `ssh_ref` are POINTERS — a secret-backend
key name, an ssh Host alias — **never secret values**. Resolve them at use time;
never inline a value into the bus or your context. `last-check` stays `—` until
the connection check engine lands.

| name | type | endpoint | scope | secret_ref | ssh_ref | last-check |
|------|------|----------|-------|------------|---------|------------|
{rows}
"""


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
    #
    # Marker-first (cli-agent 20260816T223250, after the 2026-08-16 stale-path
    # incident): a relpath baked at generation time can't survive layout
    # migrations, but each repo's `.otaman` marker is kept current by init.
    # Prefer the marker's path when it exists AND resolves to a real otaman
    # root; fall back to the relpath computation for fresh scaffolds.
    m = ".."  # fallback: assume parent dir
    if project_root:
        repo_dir = (project_root / repo["path"]).resolve()
        marker_rel = _read_marker_path(repo_dir)
        if marker_rel:
            m = marker_rel
        else:
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
                    f"  - `{specs_path}/openspec/specs/{d}/spec.md`" for d in specs_dirs
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
- Check `{m}/.agents/blocked/{repo["owner"]}.md` for your currently blocked tasks

{_SPEC_AUTHORING_GUARD}"""
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
- Check `{m}/.agents/blocked/{repo["owner"]}.md` for your currently blocked tasks

{_SPEC_AUTHORING_GUARD}"""

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
            lines.append(
                f"- **Package manager**: {repo_stds['package_manager']} (use this exclusively)"
            )
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
        plugin_root = (
            Path(__file__).resolve().parent.parent.parent
        )  # src/otaman_plugin/X.py → otaman-plugin/
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
    blocked_items = [
        k for k in knowledge_items if k.get("status") in ("needs_docs", "needs_full_docs")
    ]
    if blocked_items:
        lines = [
            "\n### Knowledge Gaps (CRITICAL)",
            "The following technologies have LOW or NO knowledge confidence.",
            "**DO NOT write implementation code for these without reading the docs first.**\n",
        ]
        for item in blocked_items:
            pack = item.get("pack", "unknown")
            path = item.get("path", f".agents/knowledge/{pack}/")
            lines.append(f"- **{pack}**: Read `{path}` before any related code")
        lines.append("\nIf docs are not available, STOP and inform the human.")
        knowledge_section = "\n".join(lines)

    # agent-credential-access 2.1: resolved connection/credential inventory.
    # Rendered from otaman-core's connection resolver (frozen contract
    # 20260824T164952) — locators only, never values. project_root is the
    # program (otaman) root, so resolve_for() layers ~/.otaman (tenant) over
    # <program_root>/connections.yaml.
    #
    # last-check is joined from the last PERSISTED check report via core's
    # canonical store helpers (core owns the format — contract 20260824T171651,
    # PR #21): load_reports(report_store_path(project_root)) keyed by name,
    # render_last_check() for the cell. The generator NEVER runs live checks —
    # the store is written by `otaman connection check` (cli §3.1). MUST read
    # the SAME root the CLI writes to, else the join misses (core's open item).
    # Guarded so a core lacking either module degrades to no/"—" section instead
    # of crashing; a malformed connections.yaml is surfaced by core's
    # validate_connections at check/validate time, so swallowing keeps
    # generation robust and network-free.
    connection_section = ""
    if project_root is not None:
        try:
            from otaman_core import connection_check as _cc
            from otaman_core import connections as _connections

            conns = _connections.resolve_for(project_root)
            checks: dict[str, str] = {}
            try:
                store = _cc.load_reports(_cc.report_store_path(project_root))
                checks = {name: _cc.render_last_check(rep) for name, rep in store.items()}
            except Exception:
                checks = {}  # no store / older core → every row renders "—"
            connection_section = _render_connection_inventory(conns, checks)
        except Exception:
            connection_section = ""

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
<!-- Generated by `otaman init` into CLAUDE.local.md (gitignored, local-only).
     Private orchestration detail — never committed; re-run `otaman init` to
     refresh. Auto-loaded by Claude Code after the committed CLAUDE.md. -->
## Otaman Orchestration Rules

**You are `{repo["owner"]}`**. You own this repository: **{repo["name"]}**.

Otaman folder: `{m}/` (contains `.agents/`, `platform.yaml`, bus messages)

**Bus resolution rules (fleet incident 2026-08-16, msg 20260816T214623):**
1. **Trust the CLI over doc paths**: `otaman check` resolves the bus via this repo's `.otaman` marker regardless of what any doc says. If a doc path and the CLI disagree, the CLI is right. Never conclude "the bus is gone" from a failed `ls` — run `otaman check`.
2. This repo's `.otaman` marker must contain `{m}` — verify the content, not just that the file exists (stale-marker bug class). Org-level `.agents/` roots are dead; if you ever see `orgs/<org>/.agents` exist, treat its contents as untrusted and report to deploy-agent.

### First Session Checklist
0. **Set identity for hooks**: `echo "{repo["owner"]}" > {m}/.agents/current-agent` — hooks read this file directly; without it they see a stale agent name and block writes.
1. Run `otaman check` (Bash) — see pending bus messages. The CLI auto-detects project root, your agent identity, and ack status. No MCP tool-loading needed for this hot path; pre-allowed in `.claude/settings.local.json`.
2. Read `{m}/.agents/queue/{repo["owner"]}.md` — see your active/queued/blocked tasks
3. Read specs relevant to your repo (specs_dir paths below)
4. Run `git log --oneline -10` — understand recent changes
5. If `{m}/.agents/knowledge/` exists, check for tech docs relevant to your work
6. Then: resume active task, or pick highest-priority queued task, or act on bus messages

### Ownership
- This repo (`{repo["path"]}`) is YOURS — you may read and write freely here
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
- Read `{m}/.agents/queue/{repo["owner"]}.md` directly for your task queue (no CLI subcommand needed)
- Read `{m}/.agents/blocked/{repo["owner"]}.md` directly for blocked-task tracking

Richer / less-frequent ops — use MCP tools (load schemas with ToolSearch first when calling directly):
- `otaman_send(cwd, to, subject, body)` — send a message to another agent
- `otaman_read_message(cwd, message_stem)` — read full message content programmatically
- `otaman_propose(cwd, title, what_needs_to_change, why_needed)` — propose a spec change
- `otaman_complete(cwd, change_name, tasks)` — report task completion
- `otaman_read_spec(cwd, spec_path)` — read spec files
- `otaman_list_agents(cwd)`, `otaman_set_agent(cwd, name)`, `otaman_cleanup(cwd)` — agent registry / housekeeping

Why the split: bus checks happen dozens of times per session, and the MCP-via-instruction path proved unreliable across model variants (2026-04-29 incident — see plugin CLAUDE.md). The Bash CLI is deterministic. Heavier write operations stay on MCP because their structured payload is worth the schema-load overhead.

**CC fan-out works the same from both transports.** As of `cli-send-cc-fanout-parity`, `otaman send <to> --cc <agent>` via bash CLI writes per-recipient CC copies with `x-cc: true` identical to MCP `otaman_send(..., cc=[...])`. CC recipients see the message in `otaman check` regardless of which transport the sender used.

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
- Your queue file: `{m}/.agents/queue/{repo["owner"]}.md`
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

### Sequenced Task-Assignments (coordination contract)

When a `task-assignment` you SEND has cross-agent ordering — its work depends on, or is depended on by, another agent's step in the same work item — it MUST carry BOTH the sequencing frontmatter AND the coordination sections. One without the other is malformed and `otaman send` refuses it, naming the missing half. Single-task assignments with no ordering carry NONE of this — don't tax the common case.

**Frontmatter (all four fields, mandatory when sequenced):**
- `sequence-id: <slug>` — shared by every step of the work item (lowercase `[a-z0-9][a-z0-9._-]`, max 64 chars)
- `step: <n>/<m>` — the recipient's step out of m total (`1 <= n <= m`)
- `depends-on: [step N, ...]` — steps that must finish first; empty `[]` for step 1
- `stop-at: <short state>` — a machine-quotable statement of the stop point

Send form: `otaman send <to> --type task-assignment --sequence-id <id> --step <n>/<m> --depends-on "step N" --stop-at "<state>"` — cli validates and refuses a malformed `step` or an unknown `depends-on` reference at send time.

**Five body sections (include every one that applies):**
1. `## Sequence` — the ordered steps × owners table for the whole item, with the recipient's row marked **YOU ARE HERE**.
2. `## Your step` — the scope boundary plus an explicit **STOP-AT**: the state at which continuing would conflict with another step (e.g. "stop when the PR is open — do NOT merge").
3. `## Handoff` — what "done" produces, who consumes it, and what it unblocks.
4. `## Context` — where this sits in the larger scope (the parent change / campaign / outcome it serves, and why now), whenever the item belongs to one.
5. `## Artifacts` — direct links/paths to the documents for THIS task (specs, design docs, PRs, evidence messages); `none` is an acceptable value.

**STOP-AT discipline (recipients — honor it over initiative):** when you reach your step's STOP-AT, STOP, report the handoff, and do NOT begin a later step even when the follow-on work is obvious. The stop exists to prevent a conflict with another agent's step (see the 2026-08-18 amendment-race incident).

**`otaman check`** annotates a pending assignment whose `depends-on` is unsatisfied with `[waiting on step N (owner)]` — advisory (acting isn't hard-blocked), but treat it as a real gate unless you know the dependency has cleared.
{specs_section}
{standards_section}
{methodology_section}
{domain_rules_section}
{knowledge_section}
{connection_section}

### Git Workflow
- Work in branches: `agent/{repo["owner"]}/{{feature-name}}`
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
    hook_source = _find_plugin_script("scripts/spec-change-hook.sh")

    if hook_source is None:
        return "WARNING: spec-change-hook.sh not found (looked in package + dev tree)"

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
    hook_source = _find_plugin_script("scripts/post-commit-hook.sh")

    if hook_source is None:
        results.append("WARNING: post-commit-hook.sh not found (looked in package + dev tree)")
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
                results.append(
                    f"Appended post-commit hook to existing {repo['name']}/.git/hooks/post-commit"
                )
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
    hook_source = _find_plugin_script("scripts/check-branch.sh")

    if hook_source is None:
        results.append("WARNING: check-branch.sh not found (looked in package + dev tree)")
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


def _is_plugin_repo(repo_dir: Path) -> bool:
    """True if repo_dir is the otaman-plugin repo itself.

    Checked via the on-disk .claude-plugin/plugin.json marker (name ==
    "otaman"), not via __file__ path math — the latter reflects whichever
    install of otaman_plugin is currently executing, which need not be the
    dev checkout being configured.
    """
    plugin_json = repo_dir / ".claude-plugin" / "plugin.json"
    if not plugin_json.is_file():
        return False
    try:
        return json.loads(plugin_json.read_text(encoding="utf-8")).get("name") == "otaman"
    except (json.JSONDecodeError, OSError):
        return False


def install_mcp_config(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Write .mcp.json in each repo so MCP tools are available.

    When the plugin is installed from the catalog, Claude Code auto-discovers
    MCP servers via ${CLAUDE_PLUGIN_ROOT} in the plugin's .mcp.json — no
    per-repo config needed. This function is only needed for local development
    (--plugin-dir) where the plugin path isn't managed by Claude Code.

    Writes absolute-Python invocations:

        "otaman-bus": {
            "command": "<sys.executable>",
            "args": ["-m", "otaman_plugin.servers.bus_server"],
            ...
        }

    The absolute path captures the Python interpreter that has otaman_plugin
    installed at init time — typically the operator's pipx venv. This is
    stable across cwds (claude reads .mcp.json from cwd; relative paths
    broke when sessions launched from a different directory) and doesn't
    depend on a shell wrapper. Replaces an earlier
    `bash run-server.sh <module>.py` pattern that relied on per-repo
    relative-path math + the wrapper's own Python-resolution heuristics —
    both of which produced "2 MCP servers failed" symptoms when the venv
    layout didn't match the wrapper's expectations (e.g. when the otaman
    install is via pipx, not a repo-local .venv).
    """
    results: list[str] = []

    # Skip if plugin is catalog-installed (CLAUDE_PLUGIN_ROOT is set by Claude Code)
    # In that case, the plugin's own .mcp.json with ${CLAUDE_PLUGIN_ROOT} works natively.
    if os.environ.get("CLAUDE_PLUGIN_ROOT") and not os.environ.get("OTAMAN_FORCE_MCP_INSTALL"):
        results.append("Skipping .mcp.json install (plugin loaded from catalog)")
        return results

    # The Python interpreter that's currently running otaman init — i.e. the
    # one that has otaman_plugin importable. Captured as an absolute path so
    # `.mcp.json` works regardless of the agent's cwd.
    py_exe = sys.executable

    # Pre-flight: confirm otaman_plugin is actually importable from this
    # interpreter. If not, writing .mcp.json with this path would produce
    # immediately-failing MCPs. Don't fail init — emit a warning + skip.
    try:
        import otaman_plugin  # noqa: F401
    except ImportError:
        results.append(
            f"WARNING: otaman_plugin not importable from {py_exe}; "
            f"skipping .mcp.json generation. Install otaman-plugin into "
            f"the same venv as otaman-cli."
        )
        return results

    for repo in config["repos"]:
        repo_dir = (project_root / repo["path"]).resolve()
        if not repo_dir.is_dir():
            continue

        # Skip the plugin's own repo: it ships its own canonical .mcp.json with
        # ${CLAUDE_PLUGIN_ROOT} paths (loaded when Claude Code reads it as a
        # plugin config via --plugin-dir / catalog). Overwriting it with the
        # absolute-Python form would break the plugin-context load.
        #
        # Identified by the on-disk .claude-plugin/plugin.json marker rather
        # than by comparing __file__-derived paths: __file__ resolves to
        # whichever install of otaman_plugin is executing `otaman init`
        # (often a pipx venv), which is commonly a *different* path than the
        # dev git checkout being configured here. Comparing those paths
        # silently failed to skip in that setup and overwrote the plugin's
        # own canonical .mcp.json.
        if _is_plugin_repo(repo_dir):
            results.append(f"{repo['name']}: skipped (plugin repo ships its own .mcp.json)")
            continue

        mcp_config = {
            "mcpServers": {
                "otaman-bus": {
                    "command": py_exe,
                    "args": ["-m", "otaman_plugin.servers.bus_server"],
                    "env": {"PYTHONUNBUFFERED": "1"},
                },
                "otaman-estimation": {
                    "command": py_exe,
                    "args": ["-m", "otaman_plugin.servers.estimation_server"],
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
            results.append(
                f"{repo['name']}: added {added} permission(s) to .claude/settings.local.json"
            )

    return results


def install_maestro_markers(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Write .maestro marker files in each managed repo pointing back to the maestro folder.  # legacy: pre-rebrand reference

    Also ensures each repo's .gitignore lists the generator's local-only
    files — the .otaman marker and CLAUDE.local.md — so adopting the
    orchestration mechanism needs no manual .gitignore edit.
    Returns list of status messages.
    """
    results: list[str] = []
    expected_account = (config.get("account") or "").strip() or None
    for repo in config["repos"]:
        repo_dir = (project_root / repo["path"]).resolve()
        if not repo_dir.is_dir():
            results.append(
                f"WARNING: Repo not found: {repo['path']}, skipping .maestro marker"  # legacy: pre-rebrand reference
            )
            continue

        # Compute relative path from repo to maestro folder  # legacy: pre-rebrand reference
        try:
            rel = os.path.relpath(project_root.resolve(), repo_dir)
            rel_posix = Path(rel).as_posix()
        except ValueError:
            rel_posix = project_root.resolve().as_posix()

        # Write .maestro marker  # legacy: pre-rebrand reference
        marker = repo_dir / ".otaman"
        # Preserve the `agent:` identity field an existing marker may carry —
        # a plain rewrite destroyed it fleet-wide (landing-agent evidence,
        # msg 20260816T215216).
        existing_agent = ""
        if marker.exists():
            for line in marker.read_text(encoding="utf-8").splitlines():
                if line.startswith("agent:"):
                    existing_agent = line.split(":", 1)[1].strip()
                    break
        lines = [
            "# Path to maestro folder (relative to this repo root)",  # legacy: pre-rebrand reference
            "# Written by maestro init — do not edit manually",  # legacy: pre-rebrand reference
            rel_posix,
        ]
        if existing_agent:
            lines.append(f"agent: {existing_agent}")
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

        # Ensure the local-only files the generator writes are gitignored:
        # the .otaman marker AND CLAUDE.local.md (the private orchestration
        # rules). Auto-adding CLAUDE.local.md here is what makes it safe for
        # a repo to adopt the mechanism just by running init — no manual
        # .gitignore edit, no window where the private file is committable.
        gitignore = repo_dir / ".gitignore"
        wanted = [
            ("# Otaman marker file (local pointer to otaman workspace)", ".otaman"),
            (
                "# Local-only orchestration rules written by `otaman init` (gitignored, never committed)",
                "CLAUDE.local.md",
            ),
        ]
        content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        present = set(content.splitlines())
        missing = [(comment, entry) for comment, entry in wanted if entry not in present]
        if missing:
            with open(gitignore, "a", encoding="utf-8") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                for comment, entry in missing:
                    f.write(f"\n{comment}\n{entry}\n")
            added = ", ".join(entry for _, entry in missing)
            verb = "Updated" if content else "Created"
            results.append(f"{verb}: {repo['name']}/.gitignore (added {added})")

    return results


def install_secrets_infra(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Ensure .otaman/ runtime dir, secrets.env.example stub, and gitignore entry.

    The maestro folder houses ``.otaman/secrets.env`` for local secret storage  # legacy: pre-rebrand reference
    (gitignored, mode 0600). The ``.example`` stub is committed and documents
    the expected keys.
    """
    results: list[str] = []
    runtime_dir = project_root / ".otaman"
    if runtime_dir.exists() and not runtime_dir.is_dir():
        # A file-shape `.otaman` marker occupies this path (both marker
        # shapes are live in the fleet). `mkdir(exist_ok=True)` only
        # tolerates an existing *directory*, so a file here crashed with
        # FileExistsError and blocked init --update. Skip the .otaman/
        # runtime dir + secrets stub gracefully — the load-bearing
        # CLAUDE.local.md generation happens elsewhere and is unaffected.
        # (cli-agent 20260818T210201.)
        results.append(
            f"WARNING: {runtime_dir} is a file-shape marker, not a runtime "
            "directory — skipping .otaman/ secrets-infra setup"
        )
        return results
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
        existing_lines = {ln.strip() for ln in gitignore.read_text(encoding="utf-8").splitlines()}
        missing = [e for e in entries_needed if e not in existing_lines]
        if missing:
            with open(gitignore, "a", encoding="utf-8") as f:
                existing = gitignore.read_text(encoding="utf-8")
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(
                    "\n# Maestro runtime state (secrets, bridge sockets, AFK flag)\n"  # legacy: pre-rebrand reference
                )
                for e in missing:
                    f.write(f"{e}\n")
            results.append(f"Updated: .gitignore (+{len(missing)} entries for .otaman/ runtime)")
    else:
        gitignore.write_text(
            "# Maestro runtime state (secrets, bridge sockets, AFK flag)\n"  # legacy: pre-rebrand reference
            + "\n".join(entries_needed)
            + "\n",
            encoding="utf-8",
        )
        results.append(
            "Created: .gitignore (maestro runtime entries)"  # legacy: pre-rebrand reference
        )

    return results


def main() -> int:
    # 2B.2-A: dry-run early return. Full per-write gating in 2B.2-B.
    import sys as _sys

    if "--dry-run" in _sys.argv:
        print("  [dry-run] generate-agent-config: skipping all writes")
        print("  [dry-run] would generate: .agents/, ownership.json, queue files,")
        print("  [dry-run]                 per-repo CLAUDE.local.md, .mcp.json, .claude/,")
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
    if py_ver < (3, 11):
        print(
            f"WARNING: Python 3.11+ recommended (you have {plat.python_version()})", file=sys.stderr
        )

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

    _phase("Writing per-repo CLAUDE.local.md", count=len(config["repos"]))
    # Write per-repo orchestration rules to gitignored CLAUDE.local.md
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

    _phase(
        "Updating per-repo .claude/settings.local.json (permissions)", count=len(config["repos"])
    )
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
        from otaman_cli.cleanup_bus import cleanup as _cleanup_run
        from otaman_cli.cleanup_bus import migrate_flat_to_active

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
