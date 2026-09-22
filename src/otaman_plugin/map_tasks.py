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
import os
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

# spec-gate-hardening 1.3(c): same slug shape otaman-core's validate_message
# enforces on x-gate-waived, so an invalid/malformed env value is dropped
# here rather than shipped as a message that fails validation downstream.
_GATE_WAIVED_SLUG = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")

#: A task line's repo annotation. Used ONLY to tell a DROP (annotated for a
#: repo that resolved to nobody — the haulops silence) from a line that is
#: legitimately nobody's. Owner resolution itself is `map_tasks_to_owners`;
#: this must not become a second implementation of it.
_ANNOTATION_RE = re.compile(r"@otaman-[a-z0-9-]+", re.IGNORECASE)


def _owner_map(entries: Any) -> dict[str, str]:
    """``{repo_name: owner}`` from a ``repos`` list, skipping disabled repos
    (archived/suspended) so tasks are never assigned to them."""
    if not isinstance(entries, list):
        return {}
    return {
        repo["name"]: repo["owner"]
        for repo in entries
        if isinstance(repo, dict)
        and repo.get("name")
        and repo.get("owner")
        and not repo.get("disabled", False)
    }


def load_ownership(project_root: Path) -> dict[str, str]:
    """Owner map from ``.agents/ownership.json``, falling back to
    ``platform.yaml`` ``repos[]``.

    The fallback is not cosmetic. This module replaced a second
    implementation (``scripts/map-tasks.py``) that read owners from
    platform.yaml and never looked at ownership.json, so a tree carrying only
    platform.yaml used to dispatch fine through the hook. Requiring
    ownership.json here would have quietly narrowed that while fixing the
    root-resolution bug — trading one silent dispatch failure for another.

    ownership.json still WINS when present: `otaman init` generates it, and it
    is the file that records `disabled` repos.
    """
    path = project_root / ".agents" / "ownership.json"
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                owners = _owner_map(json.load(f).get("repos", []))
            if owners:
                return owners
        except (OSError, json.JSONDecodeError):
            pass  # fall through — a broken file should not kill dispatch
    return _owner_map(load_platform_config(project_root).get("repos", []))


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
            task_text = task_text[: at_match.start()].strip()

        # Try to extract repo hint from **repo-name**: prefix
        bold_match = re.match(r"\*\*([\w-]+)\*\*:\s*(.+)", task_text)
        if bold_match:
            repo_hint = bold_match.group(1)
            task_text = bold_match.group(2).strip()

        tasks.append(
            {
                "text": task_text,
                "done": done,
                "group": current_group,
                "repo_hint": repo_hint,
            }
        )

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
    """Create bus messages for each agent with their assigned tasks.

    spec-gate-hardening 1.3(c): when the dispatching `otaman assign` ran
    under an active gate waiver, it sets OTAMAN_GATE_WAIVED=<violation-slug>
    before calling into this module (in-process, per the agreed seam —
    map_tasks is the actual frontmatter emitter for dispatch assignments,
    cli's own code never writes these files directly). Every assignment
    created in that call carries `x-gate-waived: <slug>` so recipients can
    see the dispatch proceeded despite an unresolved gate violation. Absent
    or malformed env value (doesn't match the slug shape otaman-core's
    validate_message enforces) is silently treated as no active waiver —
    the normal case.
    """
    bus_rel = config.get("communication", {}).get("bus_path", ".agents/bus")
    active_dir = project_root / bus_rel / "active"
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "acks").mkdir(exist_ok=True)

    gate_waived = os.environ.get("OTAMAN_GATE_WAIVED", "").strip()
    if gate_waived and not _GATE_WAIVED_SLUG.match(gate_waived):
        gate_waived = ""
    gate_waived_line = f"x-gate-waived: {gate_waived}\n" if gate_waived else ""

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
        filename = f"{ts}-otaman-to-{owner}-tasks-{slug}.md"

        task_lines = []
        for t in pending_tasks:
            repo_tag = f" ({t['repo']})" if t.get("repo") else ""
            task_lines.append(f"- [ ] {t['text']}{repo_tag}")

        orchestrator_id = "otaman"
        content = f"""---
id: {msg_id}
from: {orchestrator_id}
to: {owner}
priority: normal
type: task-assignment
timestamp: {now_iso}
status: pending
{gate_waived_line}---

## Subject: Tasks assigned from "{feature_name}"

The following tasks from the feature "{feature_name}" are assigned to you:

{chr(10).join(task_lines)}

Please implement these in your owned repos and send a completion message when done.
"""
        msg_path = active_dir / filename
        msg_path.write_text(content, encoding="utf-8")
        created.append(msg_path.relative_to(project_root).as_posix())

    return created


def check_dispatch_allowed(tasks_path: Path, config: dict[str, Any]) -> tuple[bool, list[str]]:
    """Consult the dispatch gate for the change owning *tasks_path*.

    Returns ``(may_dispatch, messages)``.

    spec-lifecycle-enforcement D5: dispatch requires stage >= ``spec-approved``;
    absent it, the configured enforcement MODE decides. This path never
    consulted the gate at all, so an authored change fanned out
    task-assignments the moment its folder was touched — spec-agent caught
    exactly that (20260922T194019) when PR #470 dispatched two authored
    changes.

    Worth being precise about cause: the gate was always missing here, but the
    path was DEAD until the root-resolution fix (#57) made hook-driven
    dispatch work. Fixing the dispatcher is what turned a latent ungated path
    into a live one.

    Honouring the mode rather than hard-refusing is deliberate. Under
    ``warn`` the dispatch proceeds and says so; hard-refusing would override a
    policy someone chose. Making refusal unconditional is a POLICY change
    (``enforcement: block``), not a conformance fix.

    Degrades to allow-with-no-message when core lacks the gate or the change
    carries no ``.openspec.yaml`` — a dispatcher must not be disarmed by a
    laggard bundle, and the read surfaces refuse loudly instead.
    """
    try:
        import yaml as _yaml
        from otaman_core.spec_lifecycle import check_dispatch_gate, resolve_spec_policy
    except Exception:
        return True, []

    meta = tasks_path.parent / ".openspec.yaml"
    if not meta.is_file():
        return True, []

    try:
        change = _yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
        program = config.get("spec_policy") if isinstance(config, dict) else None
        decision = check_dispatch_gate(change, resolve_spec_policy(program_block=program))
    except Exception:
        return True, []

    violations = list(getattr(decision, "violations", ()) or ())
    if not violations:
        return True, []

    stage = change.get("stage", "<unset>")
    # Loud either way: a gate that fires silently is the defect it exists to
    # prevent (no-silent-success clause 1 — say what was refused and why).
    verb = "DISPATCH REFUSED" if not decision.allowed else "DISPATCH WARNING"
    lines = [
        f"[map-tasks] {verb}: change {tasks_path.parent.name!r} is stage={stage}",
        *(f"[map-tasks]   - {v}" for v in violations),
    ]
    if decision.allowed:
        lines.append(
            "[map-tasks]   dispatching anyway: spec_policy enforcement is "
            f"{getattr(decision, 'mode', 'warn')!r}. Set enforcement: block to refuse."
        )
    else:
        lines.append("[map-tasks]   no task-assignments were written.")
    return decision.allowed, lines


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
        # no-silent-success 1.2: "not found" and "found nothing to do" are
        # DISTINCT outcomes, with distinct exit codes. This also named the
        # wrong file — the resolver looks for the otaman root (platform.yaml
        # via the repo's .otaman marker), not ownership.json, and that
        # misdirection cost real debugging time on haulops.
        print(
            f"ERROR: no otaman root found from {tasks_path} — "
            "the repo needs an .otaman marker pointing at the otaman folder "
            "(the one holding platform.yaml). Nothing was dispatched.",
            file=sys.stderr,
        )
        return 3

    # Load data
    ownership = load_ownership(project_root)
    config = load_platform_config(project_root)

    # Dispatch gate (spec-lifecycle-enforcement D5) — BEFORE any bus write.
    may_dispatch, gate_lines = check_dispatch_allowed(tasks_path, config)
    for line in gate_lines:
        print(line, file=sys.stderr)
    if not may_dispatch:
        return 1

    # Parse and map tasks
    tasks = parse_tasks_md(tasks_path)
    if not tasks:
        # Legitimate zero work — STATED, not disguised, and not an error:
        # a tasks.md with no checklist items is a valid thing to commit.
        print(f"0 dispatched: no checklist tasks in {tasks_path.name}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "feature": feature_name,
                    "outcome": "no-tasks-in-file",
                    "total_tasks": 0,
                    "dispatched": 0,
                    "bus_messages_created": [],
                },
                indent=2,
            )
        )
        return 0

    tasks = map_tasks_to_owners(tasks, ownership)

    # A task ANNOTATED for a repo that did not resolve to an owner is a DROP,
    # not an absence: someone asked for it and nobody got it. An unannotated
    # line is legitimately nobody's and is not counted here. This is exactly
    # the haulops silence — @otaman-haulops-firmware resolved to nothing and
    # was skipped without a word.
    dropped = [
        t_["text"]
        for t_ in tasks
        if not t_.get("owner") and _ANNOTATION_RE.search(t_.get("text", ""))
    ]

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
    report["dispatched"] = len(created)
    report["dropped"] = len(dropped)
    report["dropped_tasks"] = dropped

    # Counts on every run, on stderr so they are visible even when stdout is
    # consumed as JSON. A verb that did work says what it did.
    print(
        f"{len(created)} dispatched to {len(report['by_owner'])} agent(s); "
        f"{report['assigned']} task(s) assigned, {report['dropped']} dropped",
        file=sys.stderr,
    )

    if dropped:
        # A drop is an error, not a silent omission (delta, scenario 1).
        report["outcome"] = "drops"
        print(
            f"ERROR: {len(dropped)} task(s) carry an @otaman-<repo> annotation that "
            "resolved to no owner — they were NOT dispatched:",
            file=sys.stderr,
        )
        for text in dropped:
            print(f"  - {text}", file=sys.stderr)
        print(
            "Check that each annotated repo appears in platform.yaml repos[] with an owner.",
            file=sys.stderr,
        )
        print(json.dumps(report, indent=2))
        return 5

    if not created:
        # Tasks existed, none were for anyone here. Stated, not disguised.
        report["outcome"] = "nothing-to-dispatch"
        print(
            f"0 dispatched: none of the {len(tasks)} task(s) are annotated for a known repo",
            file=sys.stderr,
        )
        print(json.dumps(report, indent=2))
        return 0

    report["outcome"] = "dispatched"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
