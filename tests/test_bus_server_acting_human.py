"""Tests for otaman_send stamping acting-human (team-mode-registers-and-
sessions 2.1/B1, plugin's reader half).

Bridge writes <otaman-root>/.otaman/acting-human.json for a multi-human
tenant's runner-spawned session (otaman_bridge.acting_human.write_acting_human);
otaman_send reads it and stamps `acting-human: <email>` on the outgoing
message's frontmatter. Absent file (CE/single-human, or bridge never ran)
is the normal case — no stamp, zero behavior change.

Sibling layout (repo + otaman-root as separate dirs, `.otaman` FILE marker
in repo pointing at the root's `.otaman` DIRECTORY of state files) — the
two `.otaman` paths never collide in production; a single flattened
fixture dir would collide the marker FILE with the state-file DIRECTORY.
"""

from __future__ import annotations

import json

import pytest

from otaman_plugin.servers.bus_server import otaman_send

_send = otaman_send.fn


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """otaman_root (platform.yaml + .agents/) + repo (.otaman marker
    pointing at otaman_root, for identity resolution).

    bus-test-isolation 4.2 footgun: delete OTAMAN_ROOT/MAESTRO_ROOT on top
    of the shared isolate_bus fixture (pins OTAMAN_ROOT at an unrelated
    sandbox) so resolution actually walks up to otaman_root here.
    """
    monkeypatch.delenv("OTAMAN_ROOT", raising=False)
    monkeypatch.delenv("MAESTRO_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    otaman_root = tmp_path / "otaman-meta"
    otaman_root.mkdir()
    (otaman_root / "platform.yaml").write_text('project: test\nversion: "1.0"\n', encoding="utf-8")
    (otaman_root / ".agents").mkdir()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".otaman").write_text("../otaman-meta\nagent: sender-agent\n", encoding="utf-8")

    return {"root": otaman_root, "repo": repo}


def _write_acting_human(otaman_root, **fields) -> None:
    (otaman_root / ".otaman").mkdir(parents=True, exist_ok=True)
    (otaman_root / ".otaman" / "acting-human.json").write_text(json.dumps(fields), encoding="utf-8")


def _sole_message(otaman_root) -> str:
    bus = otaman_root / ".agents" / "bus" / "active"
    files = list(bus.glob("*.md"))
    assert len(files) == 1
    return files[0].read_text(encoding="utf-8")


class TestNoActingHumanFile:
    def test_no_stamp_when_absent(self, workspace):
        result = _send(cwd=str(workspace["repo"]), to="human", subject="hi", body="b")
        assert "error" not in result
        assert "acting-human" not in _sole_message(workspace["root"])


class TestActingHumanPresent:
    def test_stamps_email_in_frontmatter(self, workspace):
        _write_acting_human(
            workspace["root"],
            email="alice@example.com",
            name="Alice",
            roles=["cofounder"],
            source="attach-jwt",
        )
        result = _send(cwd=str(workspace["repo"]), to="human", subject="hi", body="b")
        assert "error" not in result
        content = _sole_message(workspace["root"])
        assert "acting-human: alice@example.com" in content
        frontmatter = content.split("---")[1]
        assert "acting-human: alice@example.com" in frontmatter

    def test_empty_email_no_stamp(self, workspace):
        _write_acting_human(workspace["root"], email="", name="Nobody")
        result = _send(cwd=str(workspace["repo"]), to="human", subject="hi", body="b")
        assert "error" not in result
        assert "acting-human" not in _sole_message(workspace["root"])

    def test_malformed_json_no_stamp_no_crash(self, workspace):
        (workspace["root"] / ".otaman").mkdir(parents=True, exist_ok=True)
        (workspace["root"] / ".otaman" / "acting-human.json").write_text(
            "{not json", encoding="utf-8"
        )
        result = _send(cwd=str(workspace["repo"]), to="human", subject="hi", body="b")
        assert "error" not in result
        assert "acting-human" not in _sole_message(workspace["root"])

    def test_cc_copy_also_carries_the_stamp(self, workspace, monkeypatch):
        """CC copies are built from the already-stamped primary content
        (_inject_x_cc operates post-hoc), so the stamp propagates."""
        _write_acting_human(workspace["root"], email="bob@example.com", name="Bob")
        result = _send(
            cwd=str(workspace["repo"]),
            to="human",
            subject="hi",
            body="b",
            cc=["spec-agent"],
        )
        assert "error" not in result
        bus = workspace["root"] / ".agents" / "bus" / "active"
        cc_files = list(bus.glob("*-cc-*.md"))
        assert len(cc_files) == 1
        assert "acting-human: bob@example.com" in cc_files[0].read_text(encoding="utf-8")
