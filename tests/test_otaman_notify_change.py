"""Tests for post-merge-spec-notify task 2.1 — `otaman_notify_change` MCP tool.

The MCP tool is a thin wrapper around `otaman_cli.notify_change.notify_change`.
These tests verify the wrapper layer:

(a) Successful invocation forwards `exit_code` and `summary` dict.
(b) Unknown cwd returns ``{"error": "No otaman project found"}``.
(c) Change name pointing at a non-existent change directory surfaces
    cli's exit code 1 + error string.
(d) Both the no-tasks.md fallback (`["spec-agent"]`) and no-annotations
    fallback (`["spec-agent", "human"]`) propagate correctly.
(e) Message file lands in `.agents/bus/active/`.

We rebuild a minimal otaman workspace under tmp_path so the test is
self-contained and doesn't depend on the live `otaman-meta` layout.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from otaman_plugin.servers.bus_server import otaman_notify_change


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Build a minimal project: platform.yaml + .agents/ + sibling specs repo."""
    monkeypatch.setenv("HOME", str(tmp_path))

    # Project root with platform.yaml — keep the dirname distinct from the
    # specs sibling so the `_resolve_specs_path` fallback exercises the
    # explicit `specs.path` reference rather than name-based guessing.
    project = tmp_path / "my-project"
    project.mkdir()
    (project / ".agents").mkdir()
    (project / ".agents" / "bus" / "active" / "acks").mkdir(parents=True)

    # platform.yaml — declare two repos with distinct owners
    platform_data = {
        "project": "test",
        "version": "1.0",
        "specs": {"path": "../my-project-specs", "format": "openspec"},
        "repos": [
            {"name": "otaman-cli", "path": "../otaman-cli", "owner": "cli-agent"},
            {"name": "otaman-plugin", "path": "../otaman-plugin", "owner": "plugin-agent"},
            {"name": "otaman-core", "path": "../otaman-core", "owner": "core-agent"},
        ],
    }
    (project / "platform.yaml").write_text(yaml.dump(platform_data), encoding="utf-8")

    # Sibling specs repo
    specs = tmp_path / "my-project-specs"
    (specs / "openspec" / "changes").mkdir(parents=True)
    # init a git repo so `_git_metadata` doesn't blow up
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=specs, check=False)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "init", "-q"],
                   cwd=specs, check=False)

    # An agent identity for the bus_server's _get_agent_identity path
    (project / ".otaman").write_text(
        f"otaman_root: .\nagent: plugin-agent\n", encoding="utf-8"
    )

    return {"project": project, "specs": specs}


def _write_change(specs: Path, name: str, tasks_md: str | None = None) -> Path:
    """Create a change dir under specs; optionally write tasks.md."""
    change_dir = specs / "openspec" / "changes" / name
    change_dir.mkdir(parents=True)
    if tasks_md is not None:
        (change_dir / "tasks.md").write_text(tasks_md, encoding="utf-8")
    return change_dir


# ---------------------------------------------------------------------------
# (a) Successful invocation forwards the summary dict and exit code
# ---------------------------------------------------------------------------

class TestSuccessfulInvocation:
    def test_returns_summary_with_exit_code(self, workspace):
        _write_change(
            workspace["specs"],
            "cool-change",
            tasks_md=(
                "## 1. @otaman-cli — first piece\n"
                "- [ ] 1.1 @otaman-cli Something\n"
                "## 2. @otaman-plugin — second piece\n"
                "- [ ] 2.1 @otaman-plugin Something else\n"
            ),
        )

        result = otaman_notify_change.fn(
            cwd=str(workspace["project"]),
            change_name="cool-change",
        )
        assert result.get("exit_code") == 0
        assert result["change_name"] == "cool-change"
        assert set(result["recipients"]) == {"cli-agent", "plugin-agent"}
        assert result["message_path"], "message_path must be populated"
        assert result.get("error") is None

    def test_message_file_lands_in_bus_active(self, workspace):
        _write_change(
            workspace["specs"],
            "cool-change",
            tasks_md="- [ ] 1.1 @otaman-cli Task\n",
        )
        result = otaman_notify_change.fn(
            cwd=str(workspace["project"]),
            change_name="cool-change",
        )
        msg_path = Path(result["message_path"])
        assert msg_path.is_file()
        # Filename ends with -spec-change.md and lives in bus/active
        assert msg_path.parent.name == "active"
        assert msg_path.name.endswith("-spec-change.md")
        # Body carries the change name + recipient list
        body = msg_path.read_text(encoding="utf-8")
        assert "**Change**: cool-change" in body
        assert "to: cli-agent" in body
        assert "type: spec-change" in body


# ---------------------------------------------------------------------------
# (b) Unknown / missing project
# ---------------------------------------------------------------------------

class TestNoProject:
    def test_missing_platform_yaml_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        empty = tmp_path / "nowhere"
        empty.mkdir()
        result = otaman_notify_change.fn(cwd=str(empty), change_name="x")
        assert result == {"error": "No otaman project found"}


# ---------------------------------------------------------------------------
# (c) Non-existent change directory
# ---------------------------------------------------------------------------

class TestNonexistentChange:
    def test_unknown_change_surfaces_exit_code_1_and_error(self, workspace):
        result = otaman_notify_change.fn(
            cwd=str(workspace["project"]),
            change_name="never-shipped",
        )
        assert result.get("exit_code") == 1
        assert "error" in result
        assert "change directory not found" in result["error"]
        assert result.get("message_path") is None


# ---------------------------------------------------------------------------
# (d) Recipient fallback rules
# ---------------------------------------------------------------------------

class TestRecipientFallbacks:
    def test_no_tasks_md_falls_back_to_spec_agent_only(self, workspace):
        _write_change(workspace["specs"], "no-tasks-yet")  # no tasks.md
        result = otaman_notify_change.fn(
            cwd=str(workspace["project"]),
            change_name="no-tasks-yet",
        )
        assert result["recipients"] == ["spec-agent"]

    def test_tasks_md_without_annotations_falls_back_to_spec_agent_human(
        self, workspace
    ):
        _write_change(
            workspace["specs"],
            "no-annotations",
            tasks_md="- [ ] 1.1 Just a task with no @otaman annotation\n",
        )
        result = otaman_notify_change.fn(
            cwd=str(workspace["project"]),
            change_name="no-annotations",
        )
        assert result["recipients"] == ["spec-agent", "human"]

    def test_unknown_annotation_still_falls_back(self, workspace):
        # @otaman-nonexistent doesn't match any repo in platform.yaml,
        # so owner-lookup returns nothing and we fall back to spec-agent+human.
        _write_change(
            workspace["specs"],
            "unknown-repo",
            tasks_md="- [ ] 1.1 @otaman-nonexistent Task\n",
        )
        result = otaman_notify_change.fn(
            cwd=str(workspace["project"]),
            change_name="unknown-repo",
        )
        assert result["recipients"] == ["spec-agent", "human"]


# ---------------------------------------------------------------------------
# (e) map-tasks.py graceful degradation
# ---------------------------------------------------------------------------

class TestMapTasksGracefulDegradation:
    def test_missing_map_tasks_does_not_break_invocation(self, workspace):
        # The cli `_find_map_tasks_py` walks a few candidate paths. In a
        # tmp_path workspace with no `scripts/map-tasks.py` anywhere, the
        # tool must still write the spec-change message and return exit 0.
        _write_change(
            workspace["specs"],
            "graceful",
            tasks_md="- [ ] 1.1 @otaman-cli Task\n",
        )
        result = otaman_notify_change.fn(
            cwd=str(workspace["project"]),
            change_name="graceful",
        )
        assert result.get("exit_code") == 0
        assert result["message_path"]  # message still written
        # map_tasks_called may be False (script absent) or True (if the dev
        # has it laying around). Either is acceptable per the graceful
        # degradation contract; what matters is no crash.
        assert "map_tasks_called" in result
