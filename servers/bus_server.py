#!/usr/bin/env python3
"""Maestro Bus MCP Server — structured tool access to the agent message bus.

Provides tools for checking messages, sending messages, acknowledging,
and querying blocked tasks. Operates on the same file-based bus as the
slash commands (/otaman:check, /otaman:propose, etc.).

Transport: stdio (launched by Claude Code via .mcp.json)
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

mcp = FastMCP(
    name="maestro-bus",
    instructions=(
        "Maestro bus tools for multi-repo agent orchestration. "
        "Use these tools to check messages, send messages, acknowledge, "
        "and manage blocked tasks on the maestro message bus."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_path(p: str) -> Path:
    """Handle WSL ↔ Windows path differences."""
    path = Path(p)
    if path.exists():
        return path
    # /mnt/c/... → C:/...
    m = re.match(r"^/mnt/([a-zA-Z])(/.*)", p)
    if m:
        win = Path(f"{m.group(1).upper()}:{m.group(2)}")
        if win.exists():
            return win
    # C:/... → /mnt/c/...
    m = re.match(r"^([A-Za-z]):(.*)", p)
    if m:
        wsl = Path(f"/mnt/{m.group(1).lower()}{m.group(2)}")
        if wsl.exists():
            return wsl
    return path


def _find_project_root(start: str | None = None) -> Path | None:
    """Find maestro root via .maestro file, env var, or walk-up fallback.

    Robust to bad/missing cwd from the agent: if ``start`` is empty, whitespace,
    or doesn't normalize to an existing path on this host (e.g. a Windows path
    fed to a Linux server), fall back to the server's own cwd. Each managed
    repo carries a .maestro marker, so the server cwd resolves correctly even
    when the agent supplies a useless value.
    """
    import sys as _sys
    _scripts = Path(__file__).resolve().parent.parent / "scripts"
    from otaman_core._resolve import find_maestro_root

    if start and start.strip():
        normalized = _normalize_path(start)
        if normalized.exists():
            root = find_maestro_root(normalized)
            if root:
                return root

    return find_maestro_root()


def _bus_dir(root: Path) -> Path:
    """Return bus/active directory path."""
    return root / ".agents" / "bus" / "active"


def _acks_dir(root: Path) -> Path:
    return _bus_dir(root) / "acks"


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse YAML frontmatter from a message file (lightweight, no PyYAML)."""
    fm: dict[str, str] = {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return fm
    for line in m.group(1).splitlines():
        kv = line.split(":", 1)
        if len(kv) == 2:
            fm[kv[0].strip()] = kv[1].strip()
    return fm


def _extract_subject(text: str) -> str:
    """Extract subject line from message body."""
    for line in text.splitlines():
        if line.startswith("## Subject:") or line.startswith("## "):
            return line.lstrip("#").strip().removeprefix("Subject:").strip()
    return "(no subject)"


def _get_agent_identity(root: Path, cwd: str | None = None) -> str | None:
    """Determine agent name from CLAUDE.md (repo-specific) or current-agent (global).

    CLAUDE.md is checked first because it's per-repo and more specific,
    while current-agent is a project-wide default.
    """
    # 1. Try CLAUDE.md in cwd (most specific — per-repo identity)
    if cwd:
        claude_md = _normalize_path(cwd) / "CLAUDE.md"
        if claude_md.exists():
            text = claude_md.read_text(encoding="utf-8")
            m = re.search(r"You are `([^`]+)`", text)
            if m:
                return m.group(1)
    # 2. Fall back to global current-agent file
    agent_file = root / ".agents" / "current-agent"
    if agent_file.exists():
        name = agent_file.read_text(encoding="utf-8").strip()
        if name:
            return name
    return None


def _timestamp_id() -> str:
    """Generate a timestamp-based message ID."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool
def maestro_check(
    cwd: str,
    status_filter: str = "pending",
) -> dict[str, Any]:
    """Check the maestro message bus for messages addressed to the current agent.

    Args:
        cwd: Current working directory of the calling agent (used to find project root)
        status_filter: Filter by status: pending, read, resolved, all (default: pending)

    Returns:
        Dict with agent name, messages list, blocked tasks, and summary counts.
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found (no .agents/ownership.json in parent directories)"}

    agent = _get_agent_identity(root, cwd)
    if not agent:
        return {"error": "No agent identity found. Set via .agents/current-agent or CLAUDE.md"}

    bus = _bus_dir(root)
    acks = _acks_dir(root)
    messages: list[dict[str, Any]] = []

    if bus.is_dir():
        for msg_path in sorted(bus.glob("*.md")):
            text = msg_path.read_text(encoding="utf-8")
            fm = _parse_frontmatter(text)

            # Check addressing
            to = fm.get("to", "").strip()
            if to != agent and to != "all":
                continue

            stem = msg_path.stem

            # Check ack status for this agent
            ack_file = acks / f"{stem}.{agent}.ack"
            if ack_file.exists():
                ack_val = ack_file.read_text(encoding="utf-8").strip()
            else:
                ack_val = "pending"

            # Apply filter
            if status_filter != "all" and ack_val != status_filter:
                continue

            messages.append({
                "stem": stem,
                "from": fm.get("from", "unknown"),
                "to": to,
                "type": fm.get("type", "info"),
                "priority": fm.get("priority", "normal"),
                "timestamp": fm.get("timestamp", ""),
                "status": ack_val,
                "subject": _extract_subject(text),
            })

    # Sort: urgent first, then by timestamp descending
    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    messages.sort(key=lambda m: (priority_order.get(m["priority"], 2), m["timestamp"]), reverse=False)
    messages.sort(key=lambda m: priority_order.get(m["priority"], 2))

    # Check blocked tasks
    blocked: list[dict[str, str]] = []
    blocked_file = root / ".agents" / "blocked" / f"{agent}.md"
    if blocked_file.exists():
        text = blocked_file.read_text(encoding="utf-8")
        for block_match in re.finditer(
            r"## Blocked: (.+?)\n.*?- \*\*Proposal\*\*: (.+?)\n.*?- \*\*Blocked since\*\*: (.+?)\n",
            text,
            re.DOTALL,
        ):
            task_name, proposal, since = block_match.groups()
            # Cross-reference with messages
            status_note = "waiting for approval"
            for msg in messages:
                if msg["type"] == "spec-change-approved" and proposal in msg.get("stem", ""):
                    status_note = "approved — waiting for spec commit"
                if msg["type"] == "spec-change" and msg["status"] == "pending":
                    status_note = "READY TO RESUME — specs updated"
            blocked.append({
                "task": task_name.strip(),
                "proposal": proposal.strip(),
                "blocked_since": since.strip(),
                "status_note": status_note,
            })

    counts = {
        "pending": sum(1 for m in messages if m["status"] == "pending"),
        "read": sum(1 for m in messages if m["status"] == "read"),
        "resolved": sum(1 for m in messages if m["status"] == "resolved"),
    }

    return {
        "agent": agent,
        "project_root": str(root),
        "messages": messages,
        "blocked_tasks": blocked,
        "counts": counts,
    }


@mcp.tool
def maestro_send(
    cwd: str,
    to: str,
    subject: str,
    body: str,
    msg_type: str = "info",
    priority: str = "normal",
) -> dict[str, Any]:
    """Send a message to another agent or all agents via the maestro bus.

    Args:
        cwd: Current working directory of the calling agent
        to: Recipient agent name, or "all" for broadcast, or "human" for human
        subject: Short subject line
        body: Message body (markdown)
        msg_type: Message type: info, question, contract-change, spec-change-request, review-request, proposal
        priority: Priority: low, normal, high, urgent
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    agent = _get_agent_identity(root, cwd)
    if not agent:
        return {"error": "No agent identity found"}

    ts = _timestamp_id()
    ts_iso = datetime.now(timezone.utc).isoformat()
    slug = re.sub(r"[^a-z0-9]+", "-", subject.lower())[:40].strip("-")
    filename = f"{ts}-{agent}-to-{to}-{slug}.md"

    content = f"""---
id: {ts}-{agent[:8]}
from: {agent}
to: {to}
priority: {priority}
type: {msg_type}
timestamp: {ts_iso}
status: pending
---

## Subject: {subject}

{body}
"""

    bus = _bus_dir(root)
    bus.mkdir(parents=True, exist_ok=True)
    msg_path = bus / filename
    msg_path.write_text(content, encoding="utf-8")

    return {
        "sent": True,
        "filename": filename,
        "stem": msg_path.stem,
        "from": agent,
        "to": to,
    }


@mcp.tool
def maestro_ack(
    cwd: str,
    message_stem: str,
    ack_status: str = "resolved",
) -> dict[str, Any]:
    """Acknowledge a message on the bus (mark as read or resolved).

    Args:
        cwd: Current working directory of the calling agent
        message_stem: The message filename without .md extension
        ack_status: Ack status: "read" or "resolved" (default: resolved)
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    agent = _get_agent_identity(root, cwd)
    if not agent:
        return {"error": "No agent identity found"}

    if ack_status not in ("read", "resolved"):
        return {"error": f"Invalid ack_status: {ack_status}. Must be 'read' or 'resolved'."}

    # Verify message exists
    bus = _bus_dir(root)
    msg_file = bus / f"{message_stem}.md"
    if not msg_file.exists():
        # Try partial match
        matches = list(bus.glob(f"*{message_stem}*.md"))
        if len(matches) == 1:
            message_stem = matches[0].stem
        elif len(matches) > 1:
            return {
                "error": f"Ambiguous stem '{message_stem}', matches: {[m.stem for m in matches[:5]]}",
            }
        else:
            return {"error": f"Message not found: {message_stem}"}

    # --- Ack integrity: task-assignment requires prior task-complete ---
    if ack_status == "resolved":
        resolved_msg = bus / f"{message_stem}.md"
        if resolved_msg.exists():
            fm = _parse_frontmatter(resolved_msg.read_text(encoding="utf-8"))
            if fm.get("type") == "task-assignment":
                # Verify this agent has sent at least one task-complete message
                found_complete = False
                for candidate in bus.glob("*.md"):
                    try:
                        c_fm = _parse_frontmatter(candidate.read_text(encoding="utf-8"))
                        if c_fm.get("from") == agent and c_fm.get("type") == "task-complete":
                            found_complete = True
                            break
                    except OSError:
                        continue
                if not found_complete:
                    return {
                        "error": (
                            "Cannot ack task-assignment as 'resolved' without reporting completion. "
                            "Run maestro_complete(cwd, change_name, tasks) first."
                        ),
                        "hint": "Lifecycle: task-assignment -> ack 'read' -> implement -> maestro_complete -> ack 'resolved'",
                    }

    acks = _acks_dir(root)
    acks.mkdir(parents=True, exist_ok=True)
    ack_file = acks / f"{message_stem}.{agent}.ack"
    ack_file.write_text(ack_status, encoding="utf-8")

    return {
        "acknowledged": True,
        "message_stem": message_stem,
        "agent": agent,
        "status": ack_status,
    }


@mcp.tool
def maestro_status(cwd: str) -> dict[str, Any]:
    """Get a summary of the maestro project: agents, message counts, blocked tasks.

    Args:
        cwd: Current working directory (used to find project root)
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    result: dict[str, Any] = {"project_root": str(root)}

    # Read agents.yaml for agent list
    agents_file = root / ".agents" / "agents.yaml"
    if agents_file.exists():
        import yaml
        data = yaml.safe_load(agents_file.read_text(encoding="utf-8"))
        result["project"] = data.get("project", "unknown")
        result["agents"] = data.get("agents", [])
    else:
        result["project"] = root.name

    # Count bus messages by status
    bus = _bus_dir(root)
    acks = _acks_dir(root)
    total = 0
    types: dict[str, int] = {}

    if bus.is_dir():
        for msg_path in bus.glob("*.md"):
            total += 1
            text = msg_path.read_text(encoding="utf-8")
            fm = _parse_frontmatter(text)
            t = fm.get("type", "info")
            types[t] = types.get(t, 0) + 1

    result["bus"] = {"total_messages": total, "by_type": types}

    # Count blocked tasks across all agents
    blocked_dir = root / ".agents" / "blocked"
    blocked_count = 0
    if blocked_dir.is_dir():
        for bf in blocked_dir.glob("*.md"):
            text = bf.read_text(encoding="utf-8")
            blocked_count += len(re.findall(r"^## Blocked:", text, re.MULTILINE))
    result["blocked_tasks"] = blocked_count

    # Pending reviews
    pending_reviews = root / ".agents" / "reviews" / "pending"
    if pending_reviews.is_dir():
        result["pending_reviews"] = len(list(pending_reviews.glob("*.md")))
    else:
        result["pending_reviews"] = 0

    return result


@mcp.tool
def maestro_blocked(
    cwd: str,
    action: str = "list",
    task_name: str | None = None,
) -> dict[str, Any]:
    """Check or clear blocked tasks for the current agent.

    Args:
        cwd: Current working directory of the calling agent
        action: "list" to show blocked tasks, "clear" to remove a specific one
        task_name: Task name to clear (required when action=clear)
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    agent = _get_agent_identity(root, cwd)
    if not agent:
        return {"error": "No agent identity found"}

    blocked_file = root / ".agents" / "blocked" / f"{agent}.md"

    if action == "list":
        if not blocked_file.exists():
            return {"agent": agent, "blocked_tasks": [], "count": 0}

        text = blocked_file.read_text(encoding="utf-8")
        tasks: list[dict[str, str]] = []
        for m in re.finditer(
            r"## Blocked: (.+?)\n(.*?)(?=\n## Blocked:|\Z)",
            text,
            re.DOTALL,
        ):
            name = m.group(1).strip()
            body = m.group(2).strip()
            proposal = ""
            since = ""
            pm = re.search(r"\*\*Proposal\*\*: (.+)", body)
            if pm:
                proposal = pm.group(1).strip()
            sm = re.search(r"\*\*Blocked since\*\*: (.+)", body)
            if sm:
                since = sm.group(1).strip()
            tasks.append({"task": name, "proposal": proposal, "blocked_since": since})

        return {"agent": agent, "blocked_tasks": tasks, "count": len(tasks)}

    elif action == "clear":
        if not task_name:
            return {"error": "task_name is required for action=clear"}
        if not blocked_file.exists():
            return {"error": f"No blocked tasks file for {agent}"}

        text = blocked_file.read_text(encoding="utf-8")
        # Remove the matching blocked section
        pattern = rf"## Blocked: {re.escape(task_name)}.*?(?=\n## Blocked:|\Z)"
        updated = re.sub(pattern, "", text, flags=re.DOTALL).strip()

        if updated:
            blocked_file.write_text(updated + "\n", encoding="utf-8")
        else:
            blocked_file.unlink()

        return {"cleared": True, "task": task_name, "agent": agent}

    return {"error": f"Unknown action: {action}. Use 'list' or 'clear'."}


@mcp.tool
def maestro_read_message(
    cwd: str,
    message_stem: str,
) -> dict[str, Any]:
    """Read the full content of a specific bus message.

    Args:
        cwd: Current working directory of the calling agent
        message_stem: The message filename without .md extension (or partial match)
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    bus = _bus_dir(root)
    msg_file = bus / f"{message_stem}.md"

    if not msg_file.exists():
        matches = list(bus.glob(f"*{message_stem}*.md"))
        if len(matches) == 1:
            msg_file = matches[0]
        elif len(matches) > 1:
            return {"error": f"Ambiguous, matches: {[m.stem for m in matches[:5]]}"}
        else:
            return {"error": f"Message not found: {message_stem}"}

    text = msg_file.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)

    # Body is everything after the frontmatter
    body_match = re.match(r"^---\s*\n.*?\n---\s*\n(.*)", text, re.DOTALL)
    body = body_match.group(1).strip() if body_match else text

    return {
        "stem": msg_file.stem,
        "frontmatter": fm,
        "body": body,
        "subject": _extract_subject(text),
    }


@mcp.tool
def maestro_complete(
    cwd: str,
    change_name: str,
    tasks: str = "",
    mark_all: bool = False,
) -> dict[str, Any]:
    """Report task completion: update tasks.md and send bus notification.

    Call this after implementing tasks from a task-assignment. It updates the
    tasks.md checkboxes in the specs repo and sends a task-complete message.

    Args:
        cwd: Current working directory of the calling agent
        change_name: OpenSpec change directory name (e.g., "add-pagination")
        tasks: Comma-separated task IDs or ranges (e.g., "2.1, 3.1-3.5")
        mark_all: If True, mark ALL tasks as complete (overrides tasks param)
    """
    import subprocess
    import sys

    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    agent = _get_agent_identity(root, cwd)
    if not agent:
        return {"error": "No agent identity found"}

    if not tasks and not mark_all:
        return {"error": "Specify tasks (e.g., '2.1, 3.1-3.5') or set mark_all=True"}

    # Call actualize-tasks.py
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    script = scripts_dir / "actualize-tasks.py"

    cmd = [sys.executable, str(script), "--change", change_name, "--agent", agent, "--project-root", str(root)]
    if mark_all:
        cmd.append("--all")
    elif tasks:
        cmd.extend(["--tasks", tasks])

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 2:
        return {"error": result.stderr.strip() or result.stdout.strip()}

    import json
    try:
        report = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        report = {"raw_output": result.stdout}

    # Send bus notification
    task_label = "all tasks" if mark_all else f"tasks {tasks}"
    send_result = maestro_send(
        cwd=cwd,
        to="all",
        subject=f"Tasks complete: {change_name}",
        body=f"**Agent**: {agent}\n**Change**: {change_name}\n**Completed**: {task_label}\n**Updated**: {report.get('updated', 0)} task(s) in tasks.md",
        msg_type="task-complete",
        priority="normal",
    )

    return {
        "actualized": report,
        "bus_message": send_result,
        "agent": agent,
        "change": change_name,
    }


@mcp.tool
def maestro_propose(
    cwd: str,
    title: str,
    what_needs_to_change: str = "",
    why_needed: str = "",
    affected_repos: str = "",
) -> dict[str, Any]:
    """Propose a spec change (creates spec-change-request on bus, blocks the agent).

    Use this when you discover a missing endpoint, contract gap, or spec change
    needed during implementation. After proposing, STOP working on the blocked
    feature and switch to other tasks.

    Args:
        cwd: Current working directory
        title: Short title for the proposed change (e.g., "add pagination to /users")
        what_needs_to_change: Description of the proposed spec change
        why_needed: What was discovered during implementation that triggered this
        affected_repos: Which repos will need changes after spec updates
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    agent = _get_agent_identity(root, cwd)
    if not agent:
        return {"error": "No agent identity found"}

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    now_ts = now.strftime("%Y%m%dT%H%M%S")

    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    msg_id = f"{now_ts}-scr-{slug}"
    filename = f"{now_ts}-{agent}-to-human-spec-change-request.md"

    bus = _bus_dir(root)
    bus.mkdir(parents=True, exist_ok=True)
    _acks_dir(root).mkdir(parents=True, exist_ok=True)

    content = f"""---
id: {msg_id}
from: {agent}
to: human
priority: high
type: spec-change-request
timestamp: {now_iso}
status: pending
---

## Subject: Spec change request: {title}

### What needs to change
{what_needs_to_change or "TODO: Describe the proposed spec change."}

### Why this is needed
{why_needed or "TODO: What was discovered during implementation that triggered this."}

### Affected repos
{affected_repos or "TODO: Which repos will need implementation changes."}
"""

    filepath = bus / filename
    filepath.write_text(content, encoding="utf-8")

    # Record blocked task
    blocked_dir = root / ".agents" / "blocked"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    blocked_file = blocked_dir / f"{agent}.md"
    blocked_entry = f"""
## Blocked: {title}
- **Proposal**: {filepath.stem}
- **Blocked since**: {now_iso}
- **Depends on**: spec-change-approved + spec-change notification
- **Task to resume**: Implement feature after spec is committed
"""
    with open(blocked_file, "a", encoding="utf-8") as f:
        f.write(blocked_entry)

    return {
        "proposed": True,
        "message": filepath.stem,
        "agent": agent,
        "title": title,
        "blocked": True,
        "warning": "STOP: Do NOT implement features depending on this spec change. Switch to other tasks. Check /otaman:check for approval.",
    }


@mcp.tool
def maestro_set_agent(cwd: str, agent_name: str) -> dict[str, Any]:
    """Set the current agent identity for this session.

    Args:
        cwd: Current working directory
        agent_name: Agent name to set (e.g., "auth-agent", "payment-agent")
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    agent_file = root / ".agents" / "current-agent"
    agent_file.parent.mkdir(parents=True, exist_ok=True)
    agent_file.write_text(agent_name.strip() + "\n", encoding="utf-8")

    return {"agent": agent_name, "file": str(agent_file)}


@mcp.tool
def maestro_list_agents(cwd: str) -> dict[str, Any]:
    """List all agents, their owned repos, and roles.

    Args:
        cwd: Current working directory
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    agents_file = root / ".agents" / "agents.yaml"
    if not agents_file.exists():
        return {"error": "agents.yaml not found"}

    # Parse agents.yaml (lightweight, no PyYAML dependency)
    text = agents_file.read_text(encoding="utf-8")
    agents: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    in_owns = False
    in_triggers = False

    for line in text.splitlines():
        stripped = line.strip()
        if line.startswith("- name:") or line.startswith("  - name:"):
            if current:
                agents.append(current)
            current = {"name": stripped.split(":", 1)[1].strip()}
            in_owns = False
            in_triggers = False
        elif stripped.startswith("role:"):
            current["role"] = stripped.split(":", 1)[1].strip()
        elif stripped == "owns:":
            in_owns = True
            in_triggers = False
            current["owns"] = []
        elif stripped == "triggers:":
            in_triggers = True
            in_owns = False
            current["triggers"] = []
        elif stripped.startswith("- ") and in_owns:
            current.setdefault("owns", []).append(stripped[2:].strip())
        elif stripped.startswith("- ") and in_triggers:
            current.setdefault("triggers", []).append(stripped[2:].strip())
        elif not stripped.startswith("-") and not stripped.startswith("  "):
            in_owns = False
            in_triggers = False
    if current:
        agents.append(current)

    # Current identity
    identity = _get_agent_identity(root, cwd)

    return {
        "agents": agents,
        "current_agent": identity,
        "count": len(agents),
    }


@mcp.tool
def maestro_cleanup(cwd: str, dry_run: bool = False) -> dict[str, Any]:
    """Archive old bus messages that are fully acknowledged.

    Args:
        cwd: Current working directory
        dry_run: If True, show what would be archived without doing it
    """
    import subprocess
    import sys

    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    script = scripts_dir / "cleanup-bus.py"

    cmd = [sys.executable, str(script), str(root)]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(cmd, capture_output=True, text=True)

    import json
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return {"raw_output": result.stdout, "stderr": result.stderr}


@mcp.tool
def maestro_read_spec(
    cwd: str,
    spec_path: str = "",
) -> dict[str, Any]:
    """Read a spec file from the specs repo without needing bash permissions.

    Args:
        cwd: Current working directory
        spec_path: Relative path within the specs repo (e.g., "openspec/specs/auth/spec.md").
                   If empty, lists available spec directories.
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    # Find specs path from platform.yaml
    config_file = root / "platform.yaml"
    specs_rel = ""
    if config_file.exists():
        for line in config_file.read_text(encoding="utf-8").splitlines():
            # Simple extraction: look for path: under specs: section
            stripped = line.strip()
            if stripped.startswith("path:") and specs_rel == "_pending":
                specs_rel = stripped.split(":", 1)[1].strip()
                break
            if stripped == "specs:":
                specs_rel = "_pending"

    if not specs_rel or specs_rel == "_pending":
        return {"error": "No specs.path configured in platform.yaml"}

    specs_dir = (root / specs_rel).resolve()
    if not specs_dir.is_dir():
        return {"error": f"Specs directory not found: {specs_rel}"}

    if not spec_path:
        # List available spec directories
        entries: list[str] = []
        for entry in sorted(specs_dir.rglob("*.md")):
            rel = entry.relative_to(specs_dir).as_posix()
            entries.append(rel)
        return {
            "specs_root": str(specs_dir),
            "files": entries[:100],  # limit to 100
            "count": len(entries),
        }

    target = specs_dir / spec_path
    if not target.exists():
        return {"error": f"Spec file not found: {spec_path}"}
    if not target.is_file():
        # It's a directory — list contents
        entries = []
        for entry in sorted(target.rglob("*.md")):
            entries.append(entry.relative_to(specs_dir).as_posix())
        return {"directory": spec_path, "files": entries[:100]}

    content = target.read_text(encoding="utf-8")
    return {
        "path": spec_path,
        "content": content,
        "size": len(content),
    }


@mcp.tool
def maestro_queue(
    cwd: str,
    action: str = "read",
    content: str = "",
) -> dict[str, Any]:
    """Read or update the agent's task queue file.

    Args:
        cwd: Current working directory
        action: "read" to view queue, "update" to replace queue content
        content: New queue content (only used with action="update")
    """
    root = _find_project_root(cwd)
    if not root:
        return {"error": "No maestro project found"}

    agent = _get_agent_identity(root, cwd)
    if not agent:
        return {"error": "No agent identity found"}

    queue_file = root / ".agents" / "queue" / f"{agent}.md"

    if action == "read":
        if not queue_file.exists():
            return {"agent": agent, "queue": "(no queue file)", "empty": True}
        text = queue_file.read_text(encoding="utf-8")
        return {"agent": agent, "queue": text, "empty": not text.strip()}

    elif action == "update":
        if not content:
            return {"error": "content required for action='update'"}
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(content, encoding="utf-8")
        return {"agent": agent, "updated": True}

    return {"error": f"Unknown action: {action}. Use 'read' or 'update'."}


if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)
