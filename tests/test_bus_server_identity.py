"""Tests for ``bus_server._get_agent_identity`` per-repo resolution.

F013 fix (security GAP finding, 2026-07-08): this function now delegates to
``otaman_core.identity.resolve_enforcement_identity()``, the single
canonical enforcement-identity resolver, instead of its own three-step
chain. Only the per-directory ``.otaman`` ``agent:`` marker (CWD ancestry
walk) is trusted:

- The ``CLAUDE.md`` `` You are `<name>` `` regex is NO LONGER honored —
  a committed doc string isn't the enforcement-grade signal that matters,
  and giving it precedence over the marker was extra surface for drift.
- The ``.agents/current-agent`` global fallback is NO LONGER honored — it
  is a single mutable file shared across every concurrent agent session in
  the project; trusting it is exactly what caused the 2026-06-08 incident
  (every MCP call misattributed to ``plugin-agent``, the agent that
  happened to last write that file).

With no ``.otaman`` marker found anywhere up the tree, identity is now
``None`` rather than falling back to a guess.
"""

from __future__ import annotations

import pytest

from otaman_plugin.servers.bus_server import _get_agent_identity


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Build a sibling-layout workspace under tmp_path.

        tmp_path/
            my-otaman/                       (project root)
                platform.yaml
                .agents/
                    current-agent            (says: plugin-agent — must NOT be trusted)
            repo-a/
                .otaman                      (otaman_root: ../my-otaman, agent: agent-a)
            repo-b/
                .otaman                      (otaman_root: ../my-otaman, agent: agent-b)
            repo-no-marker/
                CLAUDE.md                    (no .otaman; regex must not be trusted either)

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
    (repo_a / ".otaman").write_text("otaman_root: ../my-otaman\nagent: agent-a\n", encoding="utf-8")

    repo_b = tmp_path / "repo-b"
    repo_b.mkdir()
    (repo_b / ".otaman").write_text("otaman_root: ../my-otaman\nagent: agent-b\n", encoding="utf-8")

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
        # `plugin-agent`. The .otaman marker in repo-b must take precedence
        # and the current-agent file must never be consulted at all.
        identity = _get_agent_identity(workspace["otaman"], str(workspace["repo_b"]))
        assert identity == "agent-b"

    def test_cwd_inside_otaman_root_has_no_marker_resolves_none(self, workspace):
        # cwd is the otaman project root itself — no .otaman marker here.
        # The current-agent fallback is gone (F013), so this is unresolved.
        identity = _get_agent_identity(workspace["otaman"], str(workspace["otaman"]))
        assert identity is None

    def test_repo_without_marker_resolves_none(self, workspace):
        # CLAUDE.md exists but carries no .otaman marker anywhere up the
        # tree — unresolved, not a guess from current-agent.
        identity = _get_agent_identity(workspace["otaman"], str(workspace["repo_no_marker"]))
        assert identity is None


class TestClaudeMdNoLongerTrusted:
    def test_claude_md_regex_no_longer_wins_over_marker(self, workspace):
        # Add a CLAUDE.md to repo-a with the "You are `X`" pattern. F013:
        # this must NOT override the .otaman agent: field anymore.
        (workspace["repo_a"] / "CLAUDE.md").write_text(
            "You are `custom-agent` for this project.\n", encoding="utf-8"
        )
        identity = _get_agent_identity(workspace["otaman"], str(workspace["repo_a"]))
        assert identity == "agent-a"


class TestNoCwd:
    def test_no_cwd_returns_none(self, workspace):
        # F013: no current-agent fallback left to consult without a cwd.
        identity = _get_agent_identity(workspace["otaman"], None)
        assert identity is None

    def test_no_cwd_and_no_current_agent_returns_none(self, workspace):
        (workspace["otaman"] / ".agents" / "current-agent").unlink()
        identity = _get_agent_identity(workspace["otaman"], None)
        assert identity is None
