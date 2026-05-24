#!/usr/bin/env python3
"""Map OpenSpec tasks to repo owners and generate bus notifications.

Reads tasks.md from an OpenSpec active feature directory, parses task items,
maps them to repo owners using ownership.json, and creates bus messages for
each assigned agent.

Usage:
    python map-tasks.py <path-to-tasks.md>
    python map-tasks.py <openspec-feature-dir>

Output:
    - JSON report to stdout with task-to-owner mapping
    - Bus message files created in .agents/bus/

Exit codes:
    0 — success
    1 — no tasks found or mapping failed
    2 — error (file not found, parse error)
"""

from __future__ import annotations

import json
import re
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


from otaman_core._resolve import find_maestro_root as find_project_root  # shared resolver


def load_ownership(project_root: Path) -> dict[str, str]:
    """Load ownership.json and return {repo_name: owner} for active repos only.

    Disabled repos (archived/suspended) are skipped so tasks aren't assigned to them.
    """
    path = project_root / ".agents" / "ownership.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        repo["name"]: repo["owner"]
        for repo in data.get("repos", [])
        if not repo.get("disabled", False)
    }


def load_platform_config(project_root: Path) -> dict[str, Any]:
    """Load platform.yaml."""
    for name in ("platform.yaml", "platform.yml"):
        path = project_root / name
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
    return {}


def parse_tasks_md(tasks_path: Path) -> list[dict[str, Any]]:
    """Parse a tasks.md file into structured task items.

    Supports formats:
    - [ ] Task description
    - [ ] Task description @repo-name
    - [ ] **repo-name**: Task description
    - Markdown headers as task groups
    """
    content = tasks_path.read_text(encoding="utf-8")
    tasks: list[dict[str, Any]] = []
    current_group = ""

    for line in content.splitlines():
        stripped = line.strip()

        # Track group headers
        header_match = re.match(r"^#{1,3}\s+(.+)", stripped)
        if header_match:
            current_group = header_match.group(1).strip()
            continue

        # Match task items: - [ ] or - [x]
        task_match = re.match(r"^-\s+\[([ xX])\]\s+(.+)", stripped)
        if not task_match:
            continue

        done = task_match.group(1).lower() == "x"
        task_text = task_match.group(2).strip()

        # Try to extract repo hint from @repo-name
        repo_hint = None
        at_match = re.search(r"@([\w-]+)\s*$", task_text)
        if at_match:
            repo_hint = at_match.group(1)
            task_text = task_text[:at_match.start()].strip()

        # Try to extract repo hint from **repo-name**: prefix
        bold_match = re.match(r"\*\*([\w-]+)\*\*:\s*(.+)", task_text)
        if bold_match:
            repo_hint = bold_match.group(1)
            task_text = bold_match.group(2).strip()

        tasks.append({
            "text": task_text,
            "done": done,
            "group": current_group,
            "repo_hint": repo_hint,
        })

    return tasks


def infer_repo_from_task(task_text: str, repo_names: list[str]) -> str | None:
    """Try to infer which repo a task belongs to from keywords in the task text."""
    text_lower = task_text.lower()
    for name in repo_names:
        if name.lower() in text_lower:
            return name
    # Common keyword heuristics
    frontend_keywords = {"ui", "component", "page", "frontend", "css", "layout", "view"}
    backend_keywords = {"endpoint", "api", "database", "migration", "model", "service", "handler"}
    if any(kw in text_lower for kw in frontend_keywords):
        for name in repo_names:
            if any(hint in name.lower() for hint in ("web", "frontend", "app", "ui")):
                return name
    if any(kw in text_lower for kw in backend_keywords):
        for name in repo_names:
            if any(hint in name.lower() for hint in ("api", "service", "backend", "server")):
                return name
    return None


def map_tasks_to_owners(
    tasks: list[dict[str, Any]],
    ownership: dict[str, str],
) -> list[dict[str, Any]]:
    """Map each task to a repo owner. Returns enriched task list."""
    repo_names = list(ownership.keys())
    for task in tasks:
        repo = task.get("repo_hint")
        if not repo:
            repo = infer_repo_from_task(task["text"], repo_names)
        task["repo"] = repo
        task["owner"] = ownership.get(repo, "") if repo else ""
    return tasks


def create_bus_messages(
    project_root: Path,
    tasks: list[dict[str, Any]],
    feature_name: str,
    config: dict[str, Any],
) -> list[str]:
    """Create bus messages for each agent with their assigned tasks."""
    bus_rel = config.get("communication", {}).get("bus_path", ".agents/bus")
    active_dir = project_root / bus_rel / "active"
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "acks").mkdir(exist_ok=True)

    # Group tasks by owner
    by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unassigned: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("owner"):
            by_owner[task["owner"]].append(task)
        else:
            unassigned.append(task)

    created: list[str] = []
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    for i, (owner, owner_tasks) in enumerate(sorted(by_owner.items())):
        pending_tasks = [t for t in owner_tasks if not t["done"]]
        if not pending_tasks:
            continue

        slug = feature_name.lower().replace(" ", "-")[:30]
        # Add index suffix to avoid collisions when multiple agents get tasks in same second
        ts = f"{now_ts}{i:02d}" if i > 0 else now_ts
        msg_id = f"{ts}-tasks-{slug}"
        filename = f"{ts}-maestro-to-{owner}-tasks-{slug}.md"  # legacy: bus orchestrator identity is still "maestro" until cross-repo rename

        task_lines = []
        for t in pending_tasks:
            repo_tag = f" ({t['repo']})" if t.get("repo") else ""
            task_lines.append(f"- [ ] {t['text']}{repo_tag}")

        orchestrator_id = "maestro"  # legacy: bus orchestrator agent identity until cross-repo rename
        content = f"""---
id: {msg_id}
from: {orchestrator_id}
to: {owner}
priority: normal
type: task-assignment
timestamp: {now_iso}
status: pending
---

## Subject: Tasks assigned from "{feature_name}"

The following tasks from the feature "{feature_name}" are assigned to you:

{chr(10).join(task_lines)}

Please implement these in your owned repos and send a completion message when done.
"""
        msg_path = active_dir / filename
        msg_path.write_text(content, encoding="utf-8")
        created.append(msg_path.relative_to(project_root).as_posix())

    return created


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: map-tasks.py <path-to-tasks.md or openspec-feature-dir>", file=sys.stderr)
        return 2

    target = Path(sys.argv[1]).resolve()

    # Determine tasks.md path
    if target.is_dir():
        tasks_path = target / "tasks.md"
        feature_name = target.name
    else:
        tasks_path = target
        feature_name = target.parent.name

    if not tasks_path.exists():
        print(f"ERROR: Tasks file not found: {tasks_path}", file=sys.stderr)
        return 2

    # Find project root
    project_root = find_project_root(tasks_path)
    if not project_root:
        print("ERROR: Could not find .agents/ownership.json in any parent directory", file=sys.stderr)
        return 2

    # Load data
    ownership = load_ownership(project_root)
    config = load_platform_config(project_root)

    # Parse and map tasks
    tasks = parse_tasks_md(tasks_path)
    if not tasks:
        print("No tasks found in file", file=sys.stderr)
        return 1

    tasks = map_tasks_to_owners(tasks, ownership)

    # Create bus messages
    created = create_bus_messages(project_root, tasks, feature_name, config)

    # Build report
    report = {
        "feature": feature_name,
        "total_tasks": len(tasks),
        "assigned": sum(1 for t in tasks if t.get("owner")),
        "unassigned": sum(1 for t in tasks if not t.get("owner")),
        "done": sum(1 for t in tasks if t["done"]),
        "pending": sum(1 for t in tasks if not t["done"]),
        "by_owner": {},
        "unassigned_tasks": [t["text"] for t in tasks if not t.get("owner")],
        "bus_messages_created": created,
    }

    by_owner: dict[str, list[str]] = defaultdict(list)
    for t in tasks:
        if t.get("owner"):
            by_owner[t["owner"]].append(t["text"])
    report["by_owner"] = dict(by_owner)

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
