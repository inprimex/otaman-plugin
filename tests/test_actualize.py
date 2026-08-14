"""Tests for actualize-tasks.py — task completion actualization.

Covers all scenarios from the bug report:
1. Single task completion updates tasks.md
2. Bulk task completion (range) updates tasks.md
3. Partial completion only updates specified tasks
4. Status format variant (non-checkbox)
5. Acknowledgment requires actualization (idempotency)
6. End-to-end orchestration (message parsing + update)
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
import yaml

# Add scripts/ to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

actualize = importlib.import_module("otaman_plugin.actualize_tasks")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a minimal maestro project with specs structure."""
    root = tmp_path / "project"
    root.mkdir()

    # platform.yaml
    config = {
        "project": "test-platform",
        "version": "1.0",
        "repos": [
            {"name": "backend", "path": "./backend", "owner": "backend-agent"},
            {"name": "frontend", "path": "./frontend", "owner": "frontend-agent"},
        ],
        "specs": {"path": "./specs", "format": "openspec"},
    }
    (root / "platform.yaml").write_text(yaml.dump(config), encoding="utf-8")

    # .agents structure
    agents = root / ".agents"
    agents.mkdir()
    ownership = {
        "repos": [
            {"name": "backend", "owner": "backend-agent"},
            {"name": "frontend", "owner": "frontend-agent"},
        ]
    }
    (agents / "ownership.json").write_text(json.dumps(ownership), encoding="utf-8")
    (agents / "current-agent").write_text("backend-agent", encoding="utf-8")
    (agents / "bus" / "active" / "acks").mkdir(parents=True)
    (agents / "blocked").mkdir()

    return root


def make_tasks_md(project: Path, change_name: str, content: str) -> Path:
    """Create a tasks.md in the specs openspec/changes directory."""
    change_dir = project / "specs" / "openspec" / "changes" / change_name
    change_dir.mkdir(parents=True, exist_ok=True)
    tasks_file = change_dir / "tasks.md"
    tasks_file.write_text(content, encoding="utf-8")
    return tasks_file


def make_bus_message(project: Path, filename: str, content: str) -> Path:
    """Create a bus message file."""
    msg_file = project / ".agents" / "bus" / "active" / filename
    msg_file.write_text(content, encoding="utf-8")
    return msg_file


# ---------------------------------------------------------------------------
# Test 1: Single task completion
# ---------------------------------------------------------------------------


class TestSingleTaskCompletion:
    def test_single_task_checked(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "add-pagination",
            """\
# Phase 2: Implementation

- [ ] 2.1 Implement pagination endpoint
- [ ] 2.2 Add query parameters
- [ ] 2.3 Update response wrapper
""",
        )

        result = actualize.update_tasks_md(tasks_file, {"2.1"})

        content = tasks_file.read_text(encoding="utf-8")
        assert "- [x] 2.1 Implement pagination endpoint" in content
        assert "- [ ] 2.2 Add query parameters" in content
        assert "- [ ] 2.3 Update response wrapper" in content
        assert result["updated"] == 1

    def test_single_task_with_agent_attribution(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "add-auth",
            """\
- [ ] 1.1 Add login endpoint
""",
        )

        result = actualize.update_tasks_md(tasks_file, {"1.1"}, agent_name="backend-agent")

        content = tasks_file.read_text(encoding="utf-8")
        assert "- [x] 1.1 Add login endpoint" in content
        assert result["updated"] == 1


# ---------------------------------------------------------------------------
# Test 2: Bulk task completion (range)
# ---------------------------------------------------------------------------


class TestBulkTaskCompletion:
    def test_range_tasks_checked(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "multi-radar",
            """\
# Phase 3

- [ ] 3.1 Task one
- [ ] 3.2 Task two
- [ ] 3.3 Task three
- [ ] 3.4 Task four
- [ ] 3.5 Task five
""",
        )

        task_ids = actualize.parse_task_ids("3.1-3.5")
        result = actualize.update_tasks_md(tasks_file, task_ids)

        content = tasks_file.read_text(encoding="utf-8")
        for i in range(1, 6):
            assert f"- [x] 3.{i}" in content
        assert result["updated"] == 5

    def test_mark_all(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "config-cleanup",
            """\
- [ ] 1.1 Clean config A
- [ ] 1.2 Clean config B
- [ ] 2.1 Validate configs
""",
        )

        result = actualize.update_tasks_md(tasks_file, set(), mark_all=True)

        content = tasks_file.read_text(encoding="utf-8")
        assert "[ ]" not in content
        assert content.count("[x]") == 3
        assert result["updated"] == 3


# ---------------------------------------------------------------------------
# Test 3: Partial completion
# ---------------------------------------------------------------------------


class TestPartialCompletion:
    def test_only_specified_tasks_updated(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "tactiq-map",
            """\
- [ ] 4.1 First task
- [ ] 4.2 Second task
- [ ] 4.3 Third task
- [ ] 4.4 Fourth task
- [ ] 4.5 Fifth task
""",
        )

        result = actualize.update_tasks_md(tasks_file, {"4.1", "4.3"})

        content = tasks_file.read_text(encoding="utf-8")
        assert "- [x] 4.1 First task" in content
        assert "- [ ] 4.2 Second task" in content
        assert "- [x] 4.3 Third task" in content
        assert "- [ ] 4.4 Fourth task" in content
        assert "- [ ] 4.5 Fifth task" in content
        assert result["updated"] == 2

    def test_not_found_ids_reported(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "test-change",
            """\
- [ ] 1.1 Existing task
""",
        )

        result = actualize.update_tasks_md(tasks_file, {"1.1", "9.9"})
        assert "9.9" in result["not_found"]
        assert result["updated"] == 1


# ---------------------------------------------------------------------------
# Test 4: Status format variant
# ---------------------------------------------------------------------------


class TestStatusFormatVariant:
    def test_status_pending_to_done_with_mark_all(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "status-format",
            """\
## Task 1.1: Implement feature

- **Status**: pending
- **Assignee**: backend-agent

## Task 1.2: Write tests

- **Status**: pending
- **Assignee**: backend-agent
""",
        )

        result = actualize.update_tasks_md(
            tasks_file, set(), mark_all=True, agent_name="backend-agent"
        )

        content = tasks_file.read_text(encoding="utf-8")
        assert "**Status**: done" in content
        assert "backend-agent" in content
        assert result["updated"] == 2

    def test_mixed_formats(self, project: Path) -> None:
        """Tasks.md with both checkbox and status formats."""
        tasks_file = make_tasks_md(
            project,
            "mixed",
            """\
# Tasks

- [ ] 1.1 Checkbox task A
- [ ] 1.2 Checkbox task B

# Detailed Tasks

## 1.1 Checkbox task A
- **Status**: pending

## 1.2 Checkbox task B
- **Status**: pending
""",
        )

        result = actualize.update_tasks_md(tasks_file, set(), mark_all=True)

        content = tasks_file.read_text(encoding="utf-8")
        assert "- [x] 1.1" in content
        assert "- [x] 1.2" in content
        assert result["updated"] >= 2


# ---------------------------------------------------------------------------
# Test 5: Idempotency (already done tasks)
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_already_checked_not_recounted(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "already-done",
            """\
- [x] 1.1 Already done task
- [ ] 1.2 Still pending task
""",
        )

        result = actualize.update_tasks_md(tasks_file, {"1.1", "1.2"})

        assert result["updated"] == 1
        assert result["already_done"] == 1

    def test_double_update_is_safe(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "double-update",
            """\
- [ ] 1.1 Task one
- [ ] 1.2 Task two
""",
        )

        # First update
        actualize.update_tasks_md(tasks_file, {"1.1"})
        # Second update with same + new
        result = actualize.update_tasks_md(tasks_file, {"1.1", "1.2"})

        assert result["updated"] == 1  # only 1.2 was updated
        assert result["already_done"] == 1  # 1.1 was already done
        content = tasks_file.read_text(encoding="utf-8")
        assert content.count("[x]") == 2


# ---------------------------------------------------------------------------
# Test 6: End-to-end (message parsing + update)
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_parse_task_complete_message(self, project: Path) -> None:
        msg_file = make_bus_message(
            project,
            "20260327T120000-backend-agent-to-all-task-complete.md",
            """\
---
id: 20260327T120000-complete-add-pagination
from: backend-agent
to: all
priority: normal
type: task-complete
change: add-pagination
timestamp: 2026-03-27T12:00:00Z
status: pending
---

## Subject: Tasks complete: add-pagination

Completed tasks:
- [x] 2.1 Implement pagination endpoint
- [x] 2.2 Add query parameters
""",
        )

        info = actualize.parse_tasks_from_message(msg_file)
        assert info["change"] == "add-pagination"
        assert "2.1" in info["task_ids"]
        assert "2.2" in info["task_ids"]
        assert info["from"] == "backend-agent"

    def test_parse_range_message(self, project: Path) -> None:
        msg_file = make_bus_message(
            project,
            "20260327T130000-frontend-agent-to-all-task-complete.md",
            """\
---
id: 20260327T130000-complete-tactiq-map
from: frontend-agent
to: all
type: task-complete
change: tactiq-map-ux
timestamp: 2026-03-27T13:00:00Z
status: pending
---

## Subject: Tasks complete: tactiq-map-ux

Tasks 3.1-3.5 complete for change "tactiq-map-ux"
""",
        )

        info = actualize.parse_tasks_from_message(msg_file)
        assert info["change"] == "tactiq-map-ux"
        expected = {"3.1", "3.2", "3.3", "3.4", "3.5"}
        assert expected.issubset(info["task_ids"])

    def test_parse_all_complete_message(self, project: Path) -> None:
        msg_file = make_bus_message(
            project,
            "20260327T140000-backend-agent-to-all-task-complete.md",
            """\
---
id: 20260327T140000-complete-config-cleanup
from: backend-agent
to: all
type: task-complete
change: config-cleanup
timestamp: 2026-03-27T14:00:00Z
status: pending
---

## Subject: Tasks complete: config-cleanup

All tasks complete for this change.
""",
        )

        info = actualize.parse_tasks_from_message(msg_file)
        assert info["change"] == "config-cleanup"
        assert info["mark_all"] is True

    def test_full_e2e_message_to_update(self, project: Path) -> None:
        """Full flow: parse message -> find tasks.md -> update checkboxes."""
        # Create tasks.md
        make_tasks_md(
            project,
            "e2e-test",
            """\
# Phase 1

- [ ] 1.1 Setup project
- [ ] 1.2 Configure database

# Phase 2

- [ ] 2.1 Implement API
- [ ] 2.2 Write tests
- [ ] 2.3 Documentation
""",
        )

        # Create completion message
        msg_file = make_bus_message(
            project,
            "20260327T150000-backend-agent-to-all-task-complete.md",
            """\
---
id: 20260327T150000-complete-e2e-test
from: backend-agent
to: all
type: task-complete
change: e2e-test
timestamp: 2026-03-27T15:00:00Z
status: pending
---

## Subject: Tasks complete: e2e-test

Completed tasks:
- [x] 1.1 Setup project
- [x] 1.2 Configure database
- [x] 2.1 Implement API
""",
        )

        # Parse message
        info = actualize.parse_tasks_from_message(msg_file)
        assert info["change"] == "e2e-test"

        # Find tasks.md
        config = {"specs": {"path": "./specs", "format": "openspec"}}
        tasks_path = actualize.find_tasks_md(project, info["change"], config)
        assert tasks_path is not None

        # Update
        result = actualize.update_tasks_md(tasks_path, info["task_ids"], agent_name=info["from"])

        content = tasks_path.read_text(encoding="utf-8")
        assert "- [x] 1.1 Setup project" in content
        assert "- [x] 1.2 Configure database" in content
        assert "- [x] 2.1 Implement API" in content
        assert "- [ ] 2.2 Write tests" in content  # not completed
        assert "- [ ] 2.3 Documentation" in content  # not completed
        assert result["updated"] == 3


# ---------------------------------------------------------------------------
# Task ID parsing
# ---------------------------------------------------------------------------


class TestParseTaskIds:
    def test_single_id(self) -> None:
        assert actualize.parse_task_ids("2.1") == {"2.1"}

    def test_comma_separated(self) -> None:
        assert actualize.parse_task_ids("2.1, 2.3, 4.1") == {"2.1", "2.3", "4.1"}

    def test_range(self) -> None:
        result = actualize.parse_task_ids("3.1-3.5")
        assert result == {"3.1", "3.2", "3.3", "3.4", "3.5"}

    def test_mixed(self) -> None:
        result = actualize.parse_task_ids("1.1, 3.1-3.3, 5.2")
        assert "1.1" in result
        assert "3.1" in result
        assert "3.2" in result
        assert "3.3" in result
        assert "5.2" in result

    def test_empty(self) -> None:
        assert actualize.parse_task_ids("") == set()


# ---------------------------------------------------------------------------
# find_tasks_md discovery
# ---------------------------------------------------------------------------


class TestFindTasksMd:
    def test_finds_in_openspec_changes(self, project: Path) -> None:
        tasks_file = make_tasks_md(project, "my-feature", "- [ ] 1.1 Task")
        config = {"specs": {"path": "./specs", "format": "openspec"}}
        found = actualize.find_tasks_md(project, "my-feature", config)
        assert found == tasks_file

    def test_fuzzy_match(self, project: Path) -> None:
        tasks_file = make_tasks_md(project, "add-user-pagination", "- [ ] 1.1 Task")
        config = {"specs": {"path": "./specs", "format": "openspec"}}
        found = actualize.find_tasks_md(project, "pagination", config)
        assert found == tasks_file

    def test_not_found_returns_none(self, project: Path) -> None:
        config = {"specs": {"path": "./specs", "format": "openspec"}}
        found = actualize.find_tasks_md(project, "nonexistent", config)
        assert found is None

    def test_no_specs_path(self, project: Path) -> None:
        found = actualize.find_tasks_md(project, "anything", {})
        assert found is None


# ---------------------------------------------------------------------------
# Repo hint preservation
# ---------------------------------------------------------------------------


class TestRepoHintPreservation:
    def test_repo_prefix_preserved(self, project: Path) -> None:
        tasks_file = make_tasks_md(
            project,
            "multi-repo",
            """\
- [ ] **backend**: 1.1 Implement endpoint
- [ ] **frontend**: 1.2 Add UI component
""",
        )

        result = actualize.update_tasks_md(tasks_file, {"1.1"})

        content = tasks_file.read_text(encoding="utf-8")
        assert "- [x] **backend**: 1.1 Implement endpoint" in content
        assert "- [ ] **frontend**: 1.2 Add UI component" in content
        assert result["updated"] == 1
