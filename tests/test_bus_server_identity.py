"""Tests for ``bus_server._get_agent_identity`` per-repo resolution.

The resolution chain (after the 2026-06-08 fix) is:

1. ``CLAUDE.md`` regex ``You are `<name>``` in ``cwd`` (rarely matches in
   practice — most repos' CLAUDE.md don't carry that exact phrasing).
2. ``.otaman`` marker ``agent:`` field via CWD ancestry walk — canonical
   per-repo identity.
3. ``.agents/current-agent`` at the project root — global fallback only.

Before the fix, step 3 was step 2, which meant every MCP call from any repo
inside a otaman-managed workspace resolved to whatever identity was last
written to the project-root ``current-agent`` file (usually ``plugin-agent``,
since that's the agent that runs MCP-touching code). The fix wires step 2
to the per-repo ``.otaman`` marker so attribution is correct.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


from otaman_plugin.servers.bus_server import _get_agent_identity


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Build a sibling-layout workspace under tmp_path.

        tmp_path/
            my-otaman/                       (project root)
                platform.yaml
                .agents/
                    current-agent            (says: plugin-agent)
            repo-a/
                .otaman                      (otaman_root: ../my-otaman, agent: agent-a)
            repo-b/
                .otaman                      (otaman_root: ../my-otaman, agent: agent-b)
            repo-no-marker/
                CLAUDE.md                    (no `You are` regex; no .otaman)

    Patch ``HOME`` so the ``.otaman`` marker passes
    ``otaman_core._resolve._safe_marker_path`` checks (markers must resolve
    inside ``$HOME``).
    """
    monkeypatch.setenv("HOME", str(tmp_path))

    otaman = tmp_path / "my-otaman"
    otaman.mkdir()
    (otaman / "platform.yaml").write_text("project: test\nversion: 1.0\n", encoding="utf-8")
    agents_dir = otaman / ".agents"
    agents_dir.mkdir()
    (agents_dir / "current-agent").write_text("plugin-agent\n", encoding="utf-8")

    repo_a = tmp_path / "repo-a"
    repo_a.mkdir()
    (repo_a / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: agent-a\n", encoding="utf-8"
    )

    repo_b = tmp_path / "repo-b"
    repo_b.mkdir()
    (repo_b / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: agent-b\n", encoding="utf-8"
    )

    repo_no_marker = tmp_path / "repo-no-marker"
    repo_no_marker.mkdir()
    (repo_no_marker / "CLAUDE.md").write_text(
        "Some doc without the identity pattern.\n", encoding="utf-8"
    )

    return {
        "root": tmp_path,
        "otaman": otaman,
        "repo_a": repo_a,
        "repo_b": repo_b,
        "repo_no_marker": repo_no_marker,
    }


class TestPerRepoMarkerResolution:
    def test_cwd_in_repo_a_returns_agent_a(self, workspace):
        identity = _get_agent_identity(workspace["otaman"], str(workspace["repo_a"]))
        assert identity == "agent-a"

    def test_cwd_in_repo_b_returns_agent_b(self, workspace):
        # Crucially: project root is `my-otaman` whose current-agent says
        # `plugin-agent`. The .otaman marker in repo-b must take precedence.
        identity = _get_agent_identity(workspace["otaman"], str(workspace["repo_b"]))
        assert identity == "agent-b"

    def test_cwd_inside_otaman_root_falls_back_to_current_agent(self, workspace):
        # cwd is the otaman project root itself — no .otaman marker here, so
        # the global current-agent fallback fires.
        identity = _get_agent_identity(workspace["otaman"], str(workspace["otaman"]))
        assert identity == "plugin-agent"

    def test_repo_without_marker_falls_back_to_current_agent(self, workspace):
        # CLAUDE.md exists but doesn't match the identity regex; no .otaman;
        # the global current-agent fallback runs.
        identity = _get_agent_identity(
            workspace["otaman"], str(workspace["repo_no_marker"])
        )
        assert identity == "plugin-agent"


class TestClaudeMdTakesPrecedence:
    def test_claude_md_regex_wins_over_marker(self, workspace):
        # Add a CLAUDE.md to repo-a with the "You are `X`" pattern.
        # That should win over the .otaman agent: field.
        (workspace["repo_a"] / "CLAUDE.md").write_text(
            "You are `custom-agent` for this project.\n", encoding="utf-8"
        )
        identity = _get_agent_identity(workspace["otaman"], str(workspace["repo_a"]))
        assert identity == "custom-agent"


class TestNoCwd:
    def test_no_cwd_uses_current_agent_fallback(self, workspace):
        identity = _get_agent_identity(workspace["otaman"], None)
        assert identity == "plugin-agent"

    def test_no_cwd_and_no_current_agent_returns_none(self, workspace):
        (workspace["otaman"] / ".agents" / "current-agent").unlink()
        identity = _get_agent_identity(workspace["otaman"], None)
        assert identity is None
