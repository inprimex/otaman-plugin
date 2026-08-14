#!/usr/bin/env python3
"""Actualize task completion in tasks.md files.

Reads a task-complete bus message (or explicit task list), finds the
corresponding tasks.md file in the OpenSpec changes directory, and updates
checkboxes from [ ] to [x] (or Status: pending -> Status: done).

Usage:
    # From a bus message file:
    python actualize-tasks.py --message <bus-message-file>

    # Explicit task IDs:
    python actualize-tasks.py --change <change-name> --tasks "2.1,2.3,3.1-3.5"

    # Mark all tasks done for a change:
    python actualize-tasks.py --change <change-name> --all

Output:
    JSON report to stdout with updated task counts.

Exit codes:
    0 — success (tasks updated)
    1 — no matching tasks found
    2 — error (file not found, parse error)
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


from otaman_core._resolve import find_maestro_root as find_project_root  # shared resolver


def load_platform_config(project_root: Path) -> dict[str, Any]:
    """Load platform.yaml."""
    for name in ("platform.yaml", "platform.yml"):
        path = project_root / name
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


def find_tasks_md(project_root: Path, change_name: str, config: dict[str, Any]) -> Path | None:
    """Find tasks.md for a given change name.

    Searches in:
    1. {specs.path}/openspec/changes/{change_name}/tasks.md
    2. {specs.path}/changes/{change_name}/tasks.md
    3. {specs.path}/openspec/changes/*/tasks.md (fuzzy match on change_name)
    """
    specs_path = config.get("specs", {}).get("path", "")
    if not specs_path:
        return None

    specs_dir = project_root / specs_path

    # Direct matches
    candidates = [
        specs_dir / "openspec" / "changes" / change_name / "tasks.md",
        specs_dir / "changes" / change_name / "tasks.md",
    ]
    for c in candidates:
        if c.exists():
            return c

    # Fuzzy: search for change name as substring
    for search_dir in [specs_dir / "openspec" / "changes", specs_dir / "changes"]:
        if not search_dir.is_dir():
            continue
        for d in search_dir.iterdir():
            if d.is_dir() and change_name.lower() in d.name.lower():
                tasks_file = d / "tasks.md"
                if tasks_file.exists():
                    return tasks_file

    return None


def parse_task_ids(task_spec: str) -> set[str]:
    """Parse a task specification string into a set of task IDs.

    Supports:
    - Single: "2.1"
    - Comma-separated: "2.1, 2.3, 3.1"
    - Ranges: "3.1-3.5" (expands to 3.1, 3.2, 3.3, 3.4, 3.5)
    - Mixed: "2.1, 3.1-3.5, 4.2"
    """
    ids: set[str] = set()
    for part in task_spec.split(","):
        part = part.strip()
        if not part:
            continue

        range_match = re.match(r"^(\d+)\.(\d+)\s*-\s*(\d+)\.(\d+)$", part)
        if range_match:
            major1, minor1 = int(range_match.group(1)), int(range_match.group(2))
            major2, minor2 = int(range_match.group(3)), int(range_match.group(4))
            if major1 == major2:
                for m in range(minor1, minor2 + 1):
                    ids.add(f"{major1}.{m}")
            else:
                # Cross-major range: complete first major, middles, start of last
                for m in range(minor1, 100):  # generous upper bound
                    ids.add(f"{major1}.{m}")
                for maj in range(major1 + 1, major2):
                    for m in range(1, 100):
                        ids.add(f"{maj}.{m}")
                for m in range(1, minor2 + 1):
                    ids.add(f"{major2}.{m}")
        else:
            ids.add(part)

    return ids


def parse_tasks_from_message(message_path: Path) -> dict[str, Any]:
    """Parse a task-complete bus message to extract change name and task IDs.

    Expected message body format:
    ## Subject: Tasks complete: {change-name}

    Completed tasks:
    - [x] 2.1 Description
    - [x] 2.2 Description

    Or:
    Tasks 2.1-2.5 complete for change "add-pagination"
    """
    content = message_path.read_text(encoding="utf-8")

    # Parse YAML frontmatter
    fm_match = re.match(r"^---\n(.+?)\n---", content, re.DOTALL)
    if not fm_match:
        return {"error": "No YAML frontmatter found"}

    fm = yaml.safe_load(fm_match.group(1))
    if not isinstance(fm, dict):
        return {"error": "Invalid frontmatter"}

    body = content[fm_match.end() :].strip()

    # Extract change name from subject or frontmatter
    change_name = fm.get("change", "")
    if not change_name:
        # Try subject line
        subj_match = re.search(
            r"##\s*Subject:.*?(?:complete|done|finished).*?[:\-]\s*(\S+)", body, re.IGNORECASE
        )
        if subj_match:
            change_name = subj_match.group(1).strip("\"'")
        else:
            # Try "for change X" pattern
            for_match = re.search(
                r'(?:for|in)\s+(?:change\s+)?"?([a-z0-9][\w-]*)"?', body, re.IGNORECASE
            )
            if for_match:
                change_name = for_match.group(1)

    # Extract task IDs
    task_ids: set[str] = set()
    mark_all = False

    # Check for "all tasks complete" pattern
    if re.search(r"all\s+tasks?\s+(?:complete|done|finished)", body, re.IGNORECASE):
        mark_all = True

    # Check for range pattern: "tasks 2.1-2.5"
    range_matches = re.findall(r"tasks?\s+([\d.]+(?:\s*[-,]\s*[\d.]+)*)", body, re.IGNORECASE)
    for match in range_matches:
        task_ids |= parse_task_ids(match)

    # Check for checked items: - [x] 2.1 Description
    for line in body.splitlines():
        checked = re.match(r"^\s*-\s+\[x\]\s+(\d+\.\d+)", line, re.IGNORECASE)
        if checked:
            task_ids.add(checked.group(1))

    # Check for plain list: "- 2.1 Description" in completed section
    in_completed = False
    for line in body.splitlines():
        if re.match(r"^#+\s*completed|^completed\s*tasks", line, re.IGNORECASE):
            in_completed = True
            continue
        if in_completed and line.startswith("#"):
            in_completed = False
            continue
        if in_completed:
            plain_match = re.match(r"^\s*-\s+(\d+\.\d+)", line)
            if plain_match:
                task_ids.add(plain_match.group(1))

    return {
        "change": change_name,
        "task_ids": task_ids,
        "mark_all": mark_all,
        "from": fm.get("from", ""),
        "message_stem": message_path.stem,
    }


def update_tasks_md(
    tasks_path: Path,
    task_ids: set[str],
    mark_all: bool = False,
    agent_name: str = "",
) -> dict[str, Any]:
    """Update tasks.md, marking specified tasks as complete.

    Handles two formats:
    1. Checkbox: - [ ] 2.1 Description  ->  - [x] 2.1 Description
    2. Status:   **Status**: pending     ->  **Status**: done (agent-name, date)

    Returns report with counts.
    """
    content = tasks_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    updated_count = 0
    already_done = 0
    not_found_ids = set(task_ids) if task_ids else set()
    updated_lines: list[str] = []
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    agent_tag = f" ({agent_name}, {date_str})" if agent_name else f" ({date_str})"

    for line in lines:
        new_line = line

        # Match checkbox format: - [ ] 2.1 Description or - [ ] **repo**: 2.1 Description
        checkbox_match = re.match(
            r"^(\s*-\s+)\[([ xX])\]\s+((?:\*\*[\w-]+\*\*:\s*)?(\d+\.\d+)\s+.+)",
            line,
        )
        if checkbox_match:
            prefix = checkbox_match.group(1)
            check = checkbox_match.group(2)
            rest = checkbox_match.group(3)
            task_id = checkbox_match.group(4)

            should_update = mark_all or task_id in task_ids
            if should_update:
                not_found_ids.discard(task_id)
                if check.strip() == "":  # unchecked
                    new_line = f"{prefix}[x] {rest}"
                    updated_count += 1
                else:
                    already_done += 1

        # Match status format: **Status**: pending or - **Status**: pending
        status_match = re.match(
            r"^(\s*(?:-\s+)?)\*\*Status\*\*:\s*(pending|todo|in.?progress)",
            line,
            re.IGNORECASE,
        )
        if status_match and (
            mark_all or _line_matches_task_context(lines, updated_lines, task_ids)
        ):
            prefix = status_match.group(1)
            new_line = f"{prefix}**Status**: done{agent_tag}"
            updated_count += 1

        updated_lines.append(new_line)

    new_content = "\n".join(updated_lines)
    # Preserve trailing newline if original had one
    if content.endswith("\n"):
        new_content += "\n"

    if updated_count > 0:
        tasks_path.write_text(new_content, encoding="utf-8")

    return {
        "tasks_file": str(tasks_path),
        "updated": updated_count,
        "already_done": already_done,
        "not_found": sorted(not_found_ids) if not mark_all else [],
        "mark_all": mark_all,
    }


def _line_matches_task_context(
    all_lines: list[str],
    processed_lines: list[str],
    task_ids: set[str],
) -> bool:
    """Check if a Status line is within a task block that matches our target IDs.

    Looks backward from current position for a task ID reference.
    """
    if not task_ids:
        return False

    # Look at last few processed lines for a task ID
    for prev_line in reversed(processed_lines[-5:]):
        for tid in task_ids:
            if tid in prev_line:
                return True
    return False


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Actualize task completion in tasks.md")
    parser.add_argument("--message", "-m", help="Path to task-complete bus message file")
    parser.add_argument("--change", "-c", help="Change name (OpenSpec change directory)")
    parser.add_argument("--tasks", "-t", help="Task IDs to mark complete (e.g., '2.1,3.1-3.5')")
    parser.add_argument("--all", action="store_true", help="Mark ALL tasks as complete")
    parser.add_argument("--agent", "-a", help="Agent name for attribution")
    parser.add_argument("--tasks-file", help="Direct path to tasks.md (overrides auto-discovery)")
    parser.add_argument("--project-root", help="Project root (overrides auto-detection)")
    parsed = parser.parse_args()

    # Determine project root
    if parsed.project_root:
        project_root = Path(parsed.project_root).resolve()
    else:
        project_root = find_project_root(Path.cwd())

    if not project_root:
        print("ERROR: Could not find otaman project root", file=sys.stderr)
        return 2

    config = load_platform_config(project_root)

    # Mode 1: From bus message
    if parsed.message:
        msg_path = Path(parsed.message).resolve()
        if not msg_path.exists():
            print(f"ERROR: Message file not found: {msg_path}", file=sys.stderr)
            return 2

        info = parse_tasks_from_message(msg_path)
        if "error" in info:
            print(f"ERROR: {info['error']}", file=sys.stderr)
            return 2

        change_name = info["change"]
        task_ids = info["task_ids"]
        mark_all = info["mark_all"]
        agent_name = info.get("from", "")

        if not change_name:
            print("ERROR: Could not determine change name from message", file=sys.stderr)
            return 2

    # Mode 2: Explicit
    elif parsed.change:
        change_name = parsed.change
        task_ids = parse_task_ids(parsed.tasks) if parsed.tasks else set()
        mark_all = parsed.all
        agent_name = parsed.agent or ""

        if not task_ids and not mark_all:
            print("ERROR: Specify --tasks or --all", file=sys.stderr)
            return 2
    else:
        print("ERROR: Specify --message or --change", file=sys.stderr)
        parser.print_help()
        return 2

    # Find tasks.md
    if parsed.tasks_file:
        tasks_path = Path(parsed.tasks_file).resolve()
    else:
        tasks_path = find_tasks_md(project_root, change_name, config)

    if not tasks_path or not tasks_path.exists():
        print(f"ERROR: tasks.md not found for change '{change_name}'", file=sys.stderr)
        return 2

    # Update
    report = update_tasks_md(tasks_path, task_ids, mark_all, agent_name)
    report["change"] = change_name

    if report["updated"] == 0 and not report["not_found"]:
        report["note"] = "All specified tasks were already marked as done"

    print(json.dumps(report, indent=2))
    return 0 if report["updated"] > 0 or report.get("note") else 1


if __name__ == "__main__":
    sys.exit(main())
