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
import json
import os
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


def _report(r: subprocess.CompletedProcess) -> dict:
    """The surviving implementation emits a JSON report on stdout.

    `scripts/map-tasks.py` is now a shim over `otaman_plugin.map_tasks`
    (the module `otaman notify-change` already used). Consolidating onto one
    implementation means its contract wins: a machine-readable report instead
    of `notified <agent>: N task(s)` lines, and NON-ZERO exits on real errors
    instead of the old "return 0 on every failure path", which deploy-agent
    identified as the load-bearing cause of the silent dispatch outage
    (20260921T152252).
    """
    return json.loads(r.stdout)


def _run(tasks_md: Path) -> subprocess.CompletedProcess:
    # bus-test-isolation 4.2 footgun, in its subprocess form: the autouse
    # isolate_bus fixture PINS OTAMAN_ROOT at a sandbox, and the child
    # inherits it. map-tasks now resolves the root through the SHARED
    # resolver, which prefers OTAMAN_ROOT over an ancestor walk — so without
    # stripping it the child resolves the isolation sandbox instead of this
    # test's own workspace and finds no repos. The old script ignored the env
    # entirely, which is why these tests did not need this before.
    env = {k: v for k, v in os.environ.items() if k not in ("OTAMAN_ROOT", "MAESTRO_ROOT")}
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(tasks_md)],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
        env=env,
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
        rep = _report(r)
        assert len(rep["by_owner"]["cli-agent"]) == 2
        assert len(rep["by_owner"]["plugin-agent"]) == 1
        assert len(rep["by_owner"]["core-agent"]) == 1

    def test_same_line_with_multiple_annotations_does_not_double_count(self, workspace):
        # A single task line carrying the same annotation twice must still
        # count once for that agent.
        tasks_md = _write_tasks_md(
            workspace,
            "dup-anno",
            "- [ ] 1.1 @otaman-cli @otaman-cli — repeated annotation\n",
        )
        r = _run(tasks_md)
        assert r.returncode == 0
        assert len(_report(r)["by_owner"]["cli-agent"]) == 1


# ---------------------------------------------------------------------------
# (b) unknown annotation silently skipped
# ---------------------------------------------------------------------------


class TestUnknownAnnotationIsADrop:
    """Renamed from TestUnknownAnnotationSkipped. "Skipped" WAS the defect:
    no-silent-success 1.2 makes an annotated-but-unresolvable task a drop —
    named and non-zero — because someone asked for it and nobody got it.
    That is the haulops silence in miniature."""

    def test_unknown_repo_is_reported_as_a_drop(self, workspace):
        tasks_md = _write_tasks_md(
            workspace,
            "ghost-change",
            "- [ ] 1.1 @otaman-cli Real task\n- [ ] 1.2 @otaman-nonexistent Ghost task\n",
        )
        r = _run(tasks_md)
        # Exit 5, not 0: the known annotation dispatched, the unknown one was
        # LOST, and a partial dispatch must not report bare success.
        assert r.returncode == 5
        rep = _report(r)
        assert list(rep["by_owner"]) == ["cli-agent"], "the known annotation still dispatches"
        assert rep["dropped"] == 1
        assert any("nonexistent" in task for task in rep["dropped_tasks"])
        assert "NOT dispatched" in r.stderr

    def test_no_recognized_annotations_states_the_outcome(self, workspace):
        tasks_md = _write_tasks_md(
            workspace,
            "specless",
            "- [ ] 1.1 Plain task with no annotation\n- [ ] 1.2 @otaman-nonexistent Unknown only\n",
        )
        r = _run(tasks_md)
        # One line is unannotated (legitimately nobody's) and one is annotated
        # for an unknown repo (a drop) — so this is a drop, not quiet zero work.
        assert r.returncode == 5
        rep = _report(r)
        assert rep["assigned"] == 0
        assert rep["bus_messages_created"] == []
        assert rep["dropped"] == 1, "the annotated line is lost work, not an absence"


# ---------------------------------------------------------------------------
# (c) bus message written with correct frontmatter shape
# ---------------------------------------------------------------------------


class TestBusMessageShape:
    def test_message_file_layout_and_frontmatter(self, workspace):
        tasks_md = _write_tasks_md(
            workspace,
            "msg-shape",
            "- [ ] 1.1 @otaman-cli Refactor the thing\n- [ ] 1.2 @otaman-cli Test the refactor\n",
        )
        r = _run(tasks_md)
        assert r.returncode == 0
        bus = workspace / ".agents" / "bus" / "active"
        # The surviving implementation writes `<ts>-otaman-to-<agent>-tasks-<change>.md`
        # (the convention `otaman notify-change` has always produced); the
        # retired script used `-map-tasks-to-`.
        files = list(bus.glob("*-otaman-to-cli-agent-tasks-msg-shape.md"))
        assert len(files) == 1, f"expected exactly one message file: {list(bus.glob('*.md'))}"
        body = files[0].read_text(encoding="utf-8")
        # Frontmatter shape
        assert "from: otaman\n" in body
        assert "to: cli-agent\n" in body
        assert "type: task-assignment\n" in body
        assert "priority: normal\n" in body
        assert "status: pending\n" in body
        # Subject + body. The surviving implementation's subject names the
        # CHANGE ("Tasks assigned from ..."), which is what every real
        # dispatch on the bus already reads.
        assert '## Subject: Tasks assigned from "msg-shape"' in body
        assert "1.1 @otaman-cli Refactor the thing" in body
        assert "1.2 @otaman-cli Test the refactor" in body
        # The retired script appended an openspec path footer; the surviving
        # implementation names the change in the subject and lists the task
        # lines instead. Assert what it DOES carry rather than pinning a
        # footer that no longer exists.
        assert "Please implement these in your owned repos" in body


# ---------------------------------------------------------------------------
# (d) real errors exit NON-ZERO
#
# These used to assert exit 0 on every failure. That contract IS the defect
# deploy-agent root-caused (20260921T152252): the retired script returned 0
# from every error path ("caller ignores exit codes anyway"), so a total
# dispatch outage was invisible — even removing the hook's `|| true` would
# have changed nothing. The surviving implementation exits non-zero and says
# why; the hook keeps `|| true` so a commit never fails, but no longer
# discards stderr.
# ---------------------------------------------------------------------------


class TestLoudExits:
    def test_unresolvable_root_exits_nonzero(self, tmp_path):
        # Create a tasks.md with no platform.yaml anywhere above it.
        # Use /tmp which is far above any otaman project.
        bare = tmp_path / "lonely" / "openspec" / "changes" / "x"
        bare.mkdir(parents=True)
        tasks_md = bare / "tasks.md"
        tasks_md.write_text("- [ ] 1.1 @otaman-cli Task\n", encoding="utf-8")
        r = _run(tasks_md)
        # Exit 3: "not found" is now distinct from "found nothing to do" (2).
        assert r.returncode == 3, "an unresolvable root must not look like success"
        assert r.stderr.strip(), "and must say why"

    def test_missing_tasks_md_exits_nonzero(self, workspace):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), str(workspace / "no-such.md")],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        assert r.returncode == 2

    def test_no_args_exits_nonzero_with_usage(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        assert r.returncode == 2
        assert "usage:" in r.stderr.lower()


# ---------------------------------------------------------------------------
# Pure-function unit tests for parse_annotations
# ---------------------------------------------------------------------------


def _pure_annotations(tasks_md: Path) -> list[dict]:
    """Checklist tasks parsed by the SURVIVING implementation.

    These pure tests used to load `scripts/map-tasks.py` and call its
    `parse_annotations`. That function went with the duplicate; the module's
    `parse_tasks_md` is the one definition now.
    """
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from otaman_plugin.map_tasks import parse_tasks_md

    return parse_tasks_md(tasks_md)


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
        out = _pure_annotations(f)
        # One entry: the checklist line. The heading and the prose line both
        # mention @otaman-cli and must NOT become tasks.
        assert [task["text"] for task in out] == ["1.1 @otaman-cli Real task"]

    def test_checked_and_unchecked_both_included(self, tmp_path):
        f = tmp_path / "t.md"
        f.write_text(
            "- [ ] 1.1 @otaman-cli Open\n- [x] 1.2 @otaman-cli Done\n",
            encoding="utf-8",
        )
        out = _pure_annotations(f)
        assert len(out) == 2, "checked and unchecked items both count as tasks"
        assert {task["done"] for task in out} == {True, False}


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
            / "otaman-specs"
            / "openspec"
            / "changes"
            / "cli-send-cc-fanout-parity"
            / "tasks.md"
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
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        assert r.returncode == 0, f"stderr: {r.stderr}"

        # cli-agent must have received tasks 1.1-1.7 (the seven cli tasks
        # in section 1 of cli-send-cc-fanout-parity)
        bus = ws / ".agents" / "bus" / "active"
        cli_msg = list(bus.glob("*-map-tasks-to-cli-agent-cli-send-cc-fanout-parity.md"))
        assert len(cli_msg) == 1, (
            f"expected one cli-agent msg, got {[p.name for p in bus.iterdir()]}"
        )
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
