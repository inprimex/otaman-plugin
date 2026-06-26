"""Tests for map-tasks-dispatch tasks 1.1-1.8.

Coverage:

Task 1.7 — unit tests:
  (a) correct agent-task mapping from a fixture tasks.md
  (b) unknown annotation (no matching repo) silently skipped
  (c) bus message written with correct frontmatter shape
  (d) exits 0 on missing platform.yaml

Task 1.8 — integration test: invoke map-tasks.py against the live
``cli-send-cc-fanout-parity/tasks.md`` fixture; assert cli-agent
receives tasks 1.1-1.7 and core-agent receives task 2.1.

The script lives at ``scripts/map-tasks.py``. We invoke it as a real
subprocess to verify the CLI shape, not just the importable functions.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "map-tasks.py"


def _load_module():
    """Import map-tasks.py despite the hyphen in the filename."""
    spec = importlib.util.spec_from_file_location("map_tasks", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def workspace(tmp_path):
    """Minimal otaman project: platform.yaml + .agents/ + an openspec change."""
    project = tmp_path / "my-project"
    project.mkdir()
    (project / ".agents" / "bus" / "active").mkdir(parents=True)
    platform_data = {
        "project": "test",
        "version": "1.0",
        "repos": [
            {"name": "otaman-cli", "path": "../otaman-cli", "owner": "cli-agent"},
            {"name": "otaman-plugin", "path": "../otaman-plugin", "owner": "plugin-agent"},
            {"name": "otaman-core", "path": "../otaman-core", "owner": "core-agent"},
        ],
    }
    (project / "platform.yaml").write_text(yaml.dump(platform_data), encoding="utf-8")
    return project


def _write_tasks_md(project: Path, change_name: str, body: str) -> Path:
    """Create a change dir under openspec/changes/ and write tasks.md."""
    change_dir = project / "openspec" / "changes" / change_name
    change_dir.mkdir(parents=True)
    tasks = change_dir / "tasks.md"
    tasks.write_text(body, encoding="utf-8")
    return tasks


def _run(tasks_md: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(tasks_md)],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


# ---------------------------------------------------------------------------
# (a) correct agent-task mapping
# ---------------------------------------------------------------------------

class TestAgentTaskMapping:
    def test_multi_agent_mapping(self, workspace):
        tasks_md = _write_tasks_md(
            workspace,
            "demo-change",
            "## 1. @otaman-cli\n"
            "- [ ] 1.1 @otaman-cli First cli task\n"
            "- [ ] 1.2 @otaman-cli Second cli task\n"
            "## 2. @otaman-plugin\n"
            "- [ ] 2.1 @otaman-plugin Plugin task\n"
            "## 3. @otaman-core\n"
            "- [x] 3.1 @otaman-core Already-ticked core task\n",
        )
        r = _run(tasks_md)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        # Stdout should mention one summary line per agent
        assert "notified cli-agent: 2 task(s)" in r.stdout
        assert "notified plugin-agent: 1 task(s)" in r.stdout
        assert "notified core-agent: 1 task(s)" in r.stdout

    def test_same_line_with_multiple_annotations_does_not_double_count(
        self, workspace
    ):
        # A single task line carrying the same annotation twice must still
        # count once for that agent.
        tasks_md = _write_tasks_md(
            workspace,
            "dup-anno",
            "- [ ] 1.1 @otaman-cli @otaman-cli — repeated annotation\n",
        )
        r = _run(tasks_md)
        assert r.returncode == 0
        assert "notified cli-agent: 1 task(s)" in r.stdout


# ---------------------------------------------------------------------------
# (b) unknown annotation silently skipped
# ---------------------------------------------------------------------------

class TestUnknownAnnotationSkipped:
    def test_unknown_repo_does_not_error(self, workspace):
        tasks_md = _write_tasks_md(
            workspace,
            "ghost-change",
            "- [ ] 1.1 @otaman-cli Real task\n"
            "- [ ] 1.2 @otaman-nonexistent Ghost task\n",
        )
        r = _run(tasks_md)
        assert r.returncode == 0
        assert "notified cli-agent: 1 task(s)" in r.stdout
        # No agent named for the unknown repo
        assert "nonexistent" not in r.stdout

    def test_no_recognized_annotations_exits_0_silently(self, workspace):
        tasks_md = _write_tasks_md(
            workspace,
            "specless",
            "- [ ] 1.1 Plain task with no annotation\n"
            "- [ ] 1.2 @otaman-nonexistent Unknown only\n",
        )
        r = _run(tasks_md)
        assert r.returncode == 0
        assert r.stdout.strip() == ""  # nothing notified, nothing written


# ---------------------------------------------------------------------------
# (c) bus message written with correct frontmatter shape
# ---------------------------------------------------------------------------

class TestBusMessageShape:
    def test_message_file_layout_and_frontmatter(self, workspace):
        tasks_md = _write_tasks_md(
            workspace,
            "msg-shape",
            "- [ ] 1.1 @otaman-cli Refactor the thing\n"
            "- [ ] 1.2 @otaman-cli Test the refactor\n",
        )
        r = _run(tasks_md)
        assert r.returncode == 0
        bus = workspace / ".agents" / "bus" / "active"
        files = list(bus.glob("*-map-tasks-to-cli-agent-msg-shape.md"))
        assert len(files) == 1, f"expected exactly one message file: {list(bus.glob('*.md'))}"
        body = files[0].read_text(encoding="utf-8")
        # Frontmatter shape
        assert "from: otaman-specs\n" in body
        assert "to: cli-agent\n" in body
        assert "type: task-assignment\n" in body
        assert "priority: high\n" in body
        assert "status: pending\n" in body
        # Subject + body
        assert "## Subject: task-assignment: msg-shape" in body
        assert "1.1 @otaman-cli Refactor the thing" in body
        assert "1.2 @otaman-cli Test the refactor" in body
        # Spec path footer
        assert "openspec/changes/msg-shape/" in body


# ---------------------------------------------------------------------------
# (d) exits 0 on missing platform.yaml
# ---------------------------------------------------------------------------

class TestGracefulExits:
    def test_missing_platform_yaml_exits_0(self, tmp_path):
        # Create a tasks.md with no platform.yaml anywhere above it.
        # Use /tmp which is far above any otaman project.
        bare = tmp_path / "lonely" / "openspec" / "changes" / "x"
        bare.mkdir(parents=True)
        tasks_md = bare / "tasks.md"
        tasks_md.write_text(
            "- [ ] 1.1 @otaman-cli Task\n", encoding="utf-8"
        )
        r = _run(tasks_md)
        assert r.returncode == 0  # graceful exit
        # No stdout — nothing was dispatched
        assert r.stdout.strip() == ""

    def test_missing_tasks_md_exits_0(self, workspace):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), str(workspace / "no-such.md")],
            capture_output=True, text=True, check=False, timeout=15,
        )
        assert r.returncode == 0

    def test_no_args_exits_0(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, check=False, timeout=15,
        )
        assert r.returncode == 0
        assert "usage:" in r.stderr


# ---------------------------------------------------------------------------
# Pure-function unit tests for parse_annotations
# ---------------------------------------------------------------------------

class TestParseAnnotationsPure:
    def test_ignores_non_checklist_lines(self, tmp_path):
        # A heading containing @otaman-cli is NOT a checklist line and must
        # not produce a task entry.
        f = tmp_path / "t.md"
        f.write_text(
            "## @otaman-cli — section header (must be ignored)\n"
            "Some prose with @otaman-cli inline (ignored, not a list item)\n"
            "- [ ] 1.1 @otaman-cli Real task\n",
            encoding="utf-8",
        )
        mod = _load_module()
        out = mod.parse_annotations(f, {"otaman-cli": "cli-agent"})
        assert out == {"cli-agent": ["- [ ] 1.1 @otaman-cli Real task"]}

    def test_checked_and_unchecked_both_included(self, tmp_path):
        f = tmp_path / "t.md"
        f.write_text(
            "- [ ] 1.1 @otaman-cli Open\n"
            "- [x] 1.2 @otaman-cli Done\n",
            encoding="utf-8",
        )
        mod = _load_module()
        out = mod.parse_annotations(f, {"otaman-cli": "cli-agent"})
        assert len(out["cli-agent"]) == 2


# ---------------------------------------------------------------------------
# Task 1.8 — integration test against the LIVE cli-send-cc-fanout-parity
# tasks.md (not a fixture). This is the real cross-change check.
# ---------------------------------------------------------------------------

class TestIntegrationAgainstLiveFanoutParity:
    """The spec says: invoke against ``cli-send-cc-fanout-parity/tasks.md``;
    assert cli-agent receives 1.1-1.7 and core-agent receives 2.1.
    """

    def _live_tasks_path(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent.parent
            / "otaman-specs" / "openspec" / "changes"
            / "cli-send-cc-fanout-parity" / "tasks.md"
        )

    def test_dispatches_to_cli_agent_and_core_agent(self, tmp_path):
        live_tasks = self._live_tasks_path()
        if not live_tasks.is_file():
            pytest.skip(
                "cli-send-cc-fanout-parity/tasks.md not present in this checkout; "
                "integration test requires the sibling otaman-specs repo"
            )
        # Stage the live tasks.md into a tmp workspace so we don't pollute
        # the real bus. Mirror the directory layout the script expects.
        ws = tmp_path / "ws"
        change_dir = ws / "openspec" / "changes" / "cli-send-cc-fanout-parity"
        change_dir.mkdir(parents=True)
        staged_tasks = change_dir / "tasks.md"
        staged_tasks.write_text(live_tasks.read_text(encoding="utf-8"), encoding="utf-8")
        # platform.yaml mirroring the production agent map (this is the
        # mapping spec-change-hook would actually use)
        platform_data = {
            "project": "test",
            "version": "1.0",
            "repos": [
                {"name": "otaman-cli", "path": "../otaman-cli", "owner": "cli-agent"},
                {"name": "otaman-plugin", "path": "../otaman-plugin", "owner": "plugin-agent"},
                {"name": "otaman-core", "path": "../otaman-core", "owner": "core-agent"},
            ],
        }
        (ws / "platform.yaml").write_text(yaml.dump(platform_data), encoding="utf-8")
        (ws / ".agents" / "bus" / "active").mkdir(parents=True)

        r = subprocess.run(
            [sys.executable, str(SCRIPT), str(staged_tasks)],
            capture_output=True, text=True, check=False, timeout=15,
        )
        assert r.returncode == 0, f"stderr: {r.stderr}"

        # cli-agent must have received tasks 1.1-1.7 (the seven cli tasks
        # in section 1 of cli-send-cc-fanout-parity)
        bus = ws / ".agents" / "bus" / "active"
        cli_msg = list(bus.glob("*-map-tasks-to-cli-agent-cli-send-cc-fanout-parity.md"))
        assert len(cli_msg) == 1, f"expected one cli-agent msg, got {[p.name for p in bus.iterdir()]}"
        cli_body = cli_msg[0].read_text(encoding="utf-8")
        for i in range(1, 8):  # 1.1 ... 1.7
            assert f"1.{i} @otaman-cli" in cli_body, f"missing task 1.{i} in cli-agent msg"

        # core-agent must have received task 2.1
        core_msg = list(bus.glob("*-map-tasks-to-core-agent-cli-send-cc-fanout-parity.md"))
        assert len(core_msg) == 1, "expected one core-agent msg"
        core_body = core_msg[0].read_text(encoding="utf-8")
        assert "2.1 @otaman-core" in core_body

        # plugin-agent may or may not get a message — task 3.1 is in the
        # tasks.md. If it's annotated @otaman-plugin, plugin gets a msg.
        # Don't assert on it (out of scope for the 1.8 acceptance criteria).
