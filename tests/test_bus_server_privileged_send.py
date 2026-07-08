"""Tests for otaman_send refusing PRIVILEGED_TYPES (F012, 2026-07-08).

Prior to this fix, otaman_send did zero type allow-listing: any agent
could send `type: spec-change-approved` / `human-decision` /
`spec-change-rejected` / `emergency-halt` over MCP with no interactive
human confirmation possible, defeating the platform's HITL guarantee.
otaman_send must now categorically refuse these types regardless of
`from:` — that path is reserved for the CLI's human-confirmed commands.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from otaman_plugin.servers.bus_server import otaman_send

_send = otaman_send.fn

PRIVILEGED_TYPES = ("human-decision", "spec-change-approved", "spec-change-rejected", "emergency-halt")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A minimal otaman project + a per-repo `.otaman` agent marker so
    identity resolves for the non-privileged (allowed) send path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / "proj"
    root.mkdir()
    (root / "platform.yaml").write_text("project: test\nversion: \"1.0\"\n", encoding="utf-8")
    (root / ".agents").mkdir()
    (root / ".otaman").write_text("agent: sender-agent\n", encoding="utf-8")
    return root


class TestPrivilegedTypesRefused:
    @pytest.mark.parametrize("msg_type", PRIVILEGED_TYPES)
    def test_privileged_type_refused_regardless_of_recipient(self, repo, msg_type):
        result = _send(
            cwd=str(repo),
            to="human",
            subject="fake approval",
            body="body",
            msg_type=msg_type,
        )
        assert "error" in result
        assert msg_type in result["error"]

    @pytest.mark.parametrize("msg_type", PRIVILEGED_TYPES)
    def test_privileged_type_writes_no_file(self, repo, msg_type):
        bus = repo / ".agents" / "bus" / "active"
        _send(cwd=str(repo), to="all", subject="fake", body="body", msg_type=msg_type)
        assert not bus.exists() or not any(bus.glob("*.md"))

    def test_refusal_does_not_require_resolvable_identity(self, tmp_path, monkeypatch):
        # No .otaman marker at all — identity would fail to resolve. The
        # privileged-type refusal must fire before identity resolution, so
        # this still returns the privileged-type error, not a generic
        # "No agent identity found".
        monkeypatch.setenv("HOME", str(tmp_path))
        root = tmp_path / "proj-no-identity"
        root.mkdir()
        (root / "platform.yaml").write_text("project: test\nversion: \"1.0\"\n", encoding="utf-8")
        (root / ".agents").mkdir()
        result = _send(cwd=str(root), to="human", subject="x", body="y", msg_type="emergency-halt")
        assert "error" in result
        assert "emergency-halt" in result["error"]


class TestNonPrivilegedTypesStillWork:
    def test_info_type_still_sends(self, repo):
        result = _send(cwd=str(repo), to="human", subject="normal update", body="body", msg_type="info")
        assert "error" not in result
        bus = repo / ".agents" / "bus" / "active"
        files = list(bus.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "type: info" in content
        assert "from: sender-agent" in content

    def test_task_complete_type_still_sends(self, repo):
        result = _send(cwd=str(repo), to="human", subject="done", body="body", msg_type="task-complete")
        assert "error" not in result
