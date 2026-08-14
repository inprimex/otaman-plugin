"""Tests for servers/bus_server.py _find_project_root resilience.

The MCP tool surface accepts ``cwd`` from the calling agent. The agent can
supply garbage (empty string, relative path, or a Windows-style path against
a Linux server). The resolver must fall back to the server's own cwd so tools
keep working — every managed repo carries a .maestro marker, and the server
process is launched from the repo Claude Code is open in.
"""

from __future__ import annotations

import pytest

# _resolve now imported from otaman_core (sibling repo on pytest pythonpath)
from otaman_plugin.servers.bus_server import _find_project_root


@pytest.fixture
def sibling_layout(tmp_path, monkeypatch):
    """Sibling layout: otaman folder + repos under one parent.

        tmp_path/
            my-otaman-root/
                platform.yaml
                .agents/ownership.json
            repo-a/
                .maestro    (-> ../my-otaman-root)
            repo-b/
                .maestro    (-> ../my-otaman-root)

    The ``HOME=tmp_path`` patch is what makes otaman-core's
    ``_safe_marker_path`` (added in `142abf3` — rejects markers that
    resolve outside ``$HOME``) accept these fixture-built layouts:
    pytest's ``tmp_path`` lives under ``/tmp/...`` which is outside
    ``$HOME`` on most CI runners, and the resolver would otherwise
    return ``None`` for every test case here. legacy: filename
    ``.maestro`` retained per workspace-resolution spec fallback.
    """
    monkeypatch.setenv("HOME", str(tmp_path))

    maestro = tmp_path / "my-maestro"  # legacy: fixture folder name retained
    maestro.mkdir()
    (maestro / "platform.yaml").write_text("project: test\n")
    (maestro / ".agents").mkdir()
    (maestro / ".agents" / "ownership.json").write_text("{}")

    repo_a = tmp_path / "repo-a"
    repo_a.mkdir()
    (repo_a / ".maestro").write_text(
        "../my-maestro\n"
    )  # legacy: marker filename + relative path target

    repo_b = tmp_path / "repo-b"
    repo_b.mkdir()
    (repo_b / ".maestro").write_text(
        "../my-maestro\n"
    )  # legacy: marker filename + relative path target

    return {"maestro": maestro.resolve(), "repo_a": repo_a, "repo_b": repo_b}


class TestSiblingLayout:
    """The original bug — sibling repo cwd should resolve to the maestro folder."""

    def test_resolves_from_sibling_repo(self, sibling_layout):
        root = _find_project_root(str(sibling_layout["repo_a"]))
        assert root == sibling_layout["maestro"]

    def test_resolves_from_other_sibling_repo(self, sibling_layout):
        root = _find_project_root(str(sibling_layout["repo_b"]))
        assert root == sibling_layout["maestro"]

    def test_resolves_from_deep_subdir(self, sibling_layout):
        deep = sibling_layout["repo_a"] / "src" / "components"
        deep.mkdir(parents=True)
        root = _find_project_root(str(deep))
        assert root == sibling_layout["maestro"]


class TestFallbackToServerCwd:
    """When agent supplies useless cwd, fall back to server's own cwd."""

    def test_empty_string_uses_server_cwd(self, sibling_layout, monkeypatch):
        monkeypatch.chdir(sibling_layout["repo_a"])
        assert _find_project_root("") == sibling_layout["maestro"]

    def test_whitespace_uses_server_cwd(self, sibling_layout, monkeypatch):
        monkeypatch.chdir(sibling_layout["repo_b"])
        assert _find_project_root("   ") == sibling_layout["maestro"]

    def test_none_uses_server_cwd(self, sibling_layout, monkeypatch):
        monkeypatch.chdir(sibling_layout["repo_a"])
        assert _find_project_root(None) == sibling_layout["maestro"]

    def test_nonexistent_path_uses_server_cwd(self, sibling_layout, monkeypatch):
        monkeypatch.chdir(sibling_layout["repo_a"])
        # Simulate an agent supplying a Windows path while the server is on Linux,
        # or any other path that doesn't exist on this host.
        bogus = "/this/path/does/not/exist/anywhere"
        assert _find_project_root(bogus) == sibling_layout["maestro"]


class TestNoProject:
    """When neither agent cwd nor server cwd points anywhere useful."""

    def test_returns_none_if_nothing_resolves(self, tmp_path, monkeypatch):
        # Empty workspace, server cwd is also empty.
        monkeypatch.chdir(tmp_path)
        assert _find_project_root(str(tmp_path)) is None

    def test_returns_none_for_garbage_cwd_and_empty_server_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert _find_project_root("") is None
