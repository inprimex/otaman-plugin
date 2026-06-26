#!/usr/bin/env python3
"""map-tasks.py — parse a tasks.md, dispatch one task-assignment per agent.

Called by ``spec-change-hook.sh`` after a spec PR is committed/merged, and
by ``otaman notify-change`` (cli) / ``otaman_notify_change`` (MCP) when
the post-commit path didn't run (e.g. GitHub-side merge).

Algorithm (per map-tasks-dispatch design.md):

  1. Receive one positional arg: path to a tasks.md file
  2. Walk up to find platform.yaml (max 8 levels)
  3. For every checklist line containing ``@otaman-<repo>``:
     - look up the repo's ``owner`` in ``platform.yaml repos[]``
     - collect the task line under that owner
  4. Write one ``task-assignment`` bus message per agent to
     ``<project_root>/.agents/bus/active/``
  5. Print one summary line per agent to stdout
  6. Exit 0 on ALL error conditions — the hook ignores exit codes anyway
     and a hard failure would break the spec-change notification chain.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path


_TASK_LINE_RE = re.compile(r"^\s*-\s*\[[ xX]\]")
_ANNOTATION_RE = re.compile(r"@otaman-([a-z0-9-]+)", re.IGNORECASE)
_MAX_WALK_UP = 8


def _find_project_root(start: Path) -> Path:
    """Walk up from `start` looking for `platform.yaml`. Max 8 levels."""
    current = start if start.is_dir() else start.parent
    current = current.resolve()
    for _ in range(_MAX_WALK_UP + 1):
        if (current / "platform.yaml").is_file():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        f"platform.yaml not found within {_MAX_WALK_UP} levels above {start}"
    )


def _lookup_owners(platform_yaml: Path) -> dict[str, str]:
    """Read platform.yaml, return dict {repo_name: owner_name}.

    Unparseable / missing yaml returns an empty dict — caller handles
    fallback (which is "skip the unknown annotation silently").
    """
    try:
        import yaml
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(platform_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    repos = data.get("repos") or []
    if not isinstance(repos, list):
        return {}
    out: dict[str, str] = {}
    for r in repos:
        if not isinstance(r, dict):
            continue
        name = r.get("name")
        owner = r.get("owner")
        if isinstance(name, str) and isinstance(owner, str) and owner:
            out[name] = owner
    return out


def parse_annotations(
    tasks_md: Path,
    owners: dict[str, str],
) -> dict[str, list[str]]:
    """Return ``{agent_name: [task_line, ...]}``.

    Annotations whose repo isn't in ``owners`` are silently skipped (per
    spec — better to under-notify than mis-notify). One task line can have
    multiple annotations; each one routes a copy of the line to that
    agent's list. Duplicates within an agent's list are de-duped while
    preserving order (a single task line never appears twice to the same
    agent even if it carries the same annotation twice).
    """
    agents: dict[str, list[str]] = {}
    try:
        text = tasks_md.read_text(encoding="utf-8")
    except OSError:
        return agents
    seen: dict[str, set[str]] = {}
    for line in text.splitlines():
        if not _TASK_LINE_RE.match(line):
            continue
        stripped = line.strip()
        for m in _ANNOTATION_RE.finditer(line):
            repo_name = "otaman-" + m.group(1).lower()
            agent = owners.get(repo_name)
            if not agent:
                continue
            if agent not in agents:
                agents[agent] = []
                seen[agent] = set()
            if stripped in seen[agent]:
                continue
            agents[agent].append(stripped)
            seen[agent].add(stripped)
    return agents


def build_message(
    *,
    agent: str,
    change_name: str,
    task_lines: list[str],
    timestamp_iso: str,
    msg_id: str,
) -> str:
    """Render a single task-assignment bus message body."""
    tasks_block = "\n".join(task_lines)
    return (
        "---\n"
        f"id: {msg_id}\n"
        "from: otaman-specs\n"
        f"to: {agent}\n"
        "priority: high\n"
        "type: task-assignment\n"
        f"timestamp: {timestamp_iso}\n"
        "status: pending\n"
        "---\n"
        "\n"
        f"## Subject: task-assignment: {change_name}\n"
        "\n"
        f"Spec change **{change_name}** has landed. Your tasks:\n"
        "\n"
        f"{tasks_block}\n"
        "\n"
        f"**Spec path:** `openspec/changes/{change_name}/`\n"
        "\n"
        "Read `proposal.md` → `design.md` → `tasks.md` for full context.\n"
    )


def write_messages(
    bus_dir: Path,
    agents: dict[str, list[str]],
    change_name: str,
) -> dict[str, Path]:
    """Write one task-assignment per agent. Return ``{agent: path}``."""
    bus_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%S")
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    written: dict[str, Path] = {}
    for agent, lines in agents.items():
        filename = f"{ts}-map-tasks-to-{agent}-{change_name}.md"
        msg_id = f"{ts}-map-{agent[:8]}"
        body = build_message(
            agent=agent,
            change_name=change_name,
            task_lines=lines,
            timestamp_iso=iso,
            msg_id=msg_id,
        )
        path = bus_dir / filename
        try:
            path.write_text(body, encoding="utf-8")
        except OSError as exc:
            print(f"[map-tasks] write failed for {agent}: {exc}", file=sys.stderr)
            continue
        written[agent] = path
    return written


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("[map-tasks] usage: map-tasks.py <tasks.md>", file=sys.stderr)
        return 0  # graceful — caller ignores exit codes anyway

    tasks_path = Path(argv[1]).resolve()
    if not tasks_path.is_file():
        print(f"[map-tasks] tasks.md not found: {tasks_path}", file=sys.stderr)
        return 0

    try:
        project_root = _find_project_root(tasks_path)
    except FileNotFoundError as exc:
        print(f"[map-tasks] {exc}", file=sys.stderr)
        return 0

    platform_yaml = project_root / "platform.yaml"
    owners = _lookup_owners(platform_yaml)
    if not owners:
        print(
            f"[map-tasks] no usable repos[] entries in {platform_yaml}",
            file=sys.stderr,
        )
        return 0

    change_name = tasks_path.parent.name  # openspec/changes/<change>/tasks.md
    agents = parse_annotations(tasks_path, owners)
    if not agents:
        # No @otaman-<repo> annotations resolved to a known repo. Not an
        # error — some changes are spec-side only.
        return 0

    bus_dir = project_root / ".agents" / "bus" / "active"
    try:
        written = write_messages(bus_dir, agents, change_name)
    except Exception as exc:  # defensive; write_messages itself is robust
        print(f"[map-tasks] dispatch failed: {exc}", file=sys.stderr)
        return 0

    for agent, lines in agents.items():
        if agent in written:
            print(f"[map-tasks] notified {agent}: {len(lines)} task(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
