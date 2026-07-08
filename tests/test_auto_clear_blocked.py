"""Tests for auto-clear-blocked-entries (tasks 1.1, 1.3, 1.4, 1.6, 1.7).

Covers the seven unit cases enumerated in task 1.6 plus a full
integration round-trip from ``otaman_propose`` → ``otaman_send`` with a
``spec-change-approved`` payload that should auto-tombstone the
proposing agent's blocked entry.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from otaman_plugin.servers.bus_server import (  # noqa: E402
    _auto_tombstone_blocked,
    _extract_proposal_stems,
    otaman_propose,
    otaman_send,
)


# ---------------------------------------------------------------------------
# Fixture — project root with a couple of agent blocked files
# ---------------------------------------------------------------------------

_BLOCKED_ENTRY_TEMPLATE = """
## Blocked: {title}
- **Proposal**: {stem}
- **Change**: {change}
- **Blocked since**: 2026-06-10T16:15:00Z
- **Depends on**: spec-change-approved + spec-change notification
- **Task to resume**: Implement feature after spec is committed
"""


def _write_blocked(path: Path, *entries: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(_BLOCKED_ENTRY_TEMPLATE.format(**e) for e in entries)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / "my-otaman"
    root.mkdir()
    (root / "platform.yaml").write_text(
        yaml.dump({"project": "test", "version": "1.0"}), encoding="utf-8"
    )
    (root / ".agents").mkdir()
    return root


# ---------------------------------------------------------------------------
# _extract_proposal_stems
# ---------------------------------------------------------------------------

class TestExtractProposalStems:
    def test_finds_canonical_stem(self):
        body = (
            "**Original proposal**: "
            "20260610T161500-plugin-agent-to-human-spec-change-request"
        )
        assert _extract_proposal_stems(body) == [
            "20260610T161500-plugin-agent-to-human-spec-change-request"
        ]

    def test_finds_multi_part_slug(self):
        body = (
            "Proposal "
            "20260609T162536-cofounder-agent-to-human-spec-change-request-differentiator-mapper-skill"
            " approved"
        )
        assert _extract_proposal_stems(body) == [
            "20260609T162536-cofounder-agent-to-human-spec-change-request-differentiator-mapper-skill"
        ]

    def test_empty_body(self):
        assert _extract_proposal_stems("") == []

    def test_no_stem(self):
        assert _extract_proposal_stems("nothing to see here") == []


# ---------------------------------------------------------------------------
# _auto_tombstone_blocked — 7 unit cases per task 1.6
# ---------------------------------------------------------------------------

class TestAutoTombstoneBlocked:
    # a) approval tombstones matching entry
    def test_approval_tombstones_matching_entry(self, project):
        stem = "20260610T161500-plugin-agent-to-human-spec-change-request"
        _write_blocked(
            project / ".agents" / "blocked" / "plugin-agent.md",
            {"title": "foo bar", "stem": stem, "change": "foo-bar"},
        )
        result = _auto_tombstone_blocked(
            project,
            "spec-change-approved",
            f"**Original proposal**: {stem}",
        )
        assert len(result) == 1
        assert result[0]["agent"] == "plugin-agent"
        assert result[0]["title"] == "foo bar"
        assert result[0]["reason"] == "approved"
        text = (project / ".agents" / "blocked" / "plugin-agent.md").read_text()
        assert "<!-- ## Blocked: foo bar" in text
        assert "— approved -->" in text
        # The line-leading `^## Blocked:` no longer appears active
        assert "\n## Blocked: foo bar" not in text

    # b) rejection tombstones with correct reason
    def test_rejection_uses_rejected_reason(self, project):
        stem = "20260610T161500-plugin-agent-to-human-spec-change-request"
        _write_blocked(
            project / ".agents" / "blocked" / "plugin-agent.md",
            {"title": "bad idea", "stem": stem, "change": "bad-idea"},
        )
        result = _auto_tombstone_blocked(
            project,
            "spec-change-rejected",
            f"Original proposal {stem} rejected",
        )
        assert result[0]["reason"] == "rejected"
        text = (project / ".agents" / "blocked" / "plugin-agent.md").read_text()
        assert "— rejected -->" in text

    # c) task-assignment fallback tombstones if entry still present
    def test_task_assignment_fallback_tombstones(self, project):
        _write_blocked(
            project / ".agents" / "blocked" / "plugin-agent.md",
            {
                "title": "ship the feature",
                "stem": "20260610T161500-plugin-agent-to-human-spec-change-request",
                "change": "ship-the-feature",
            },
        )
        result = _auto_tombstone_blocked(
            project,
            "task-assignment",
            body="Tasks 1.1-1.5 of ship-the-feature assigned to plugin-agent.",
            change_name="ship-the-feature",
        )
        assert len(result) == 1
        assert result[0]["reason"] == "task-assigned"

    # d) task-assignment no-ops if entry already tombstoned
    def test_idempotent_already_tombstoned(self, project):
        stem = "20260610T161500-plugin-agent-to-human-spec-change-request"
        path = project / ".agents" / "blocked" / "plugin-agent.md"
        _write_blocked(path, {"title": "thing", "stem": stem, "change": "thing"})
        # First call tombstones
        first = _auto_tombstone_blocked(project, "spec-change-approved", stem)
        assert len(first) == 1
        before = path.read_text()
        # Second call should be a no-op
        second = _auto_tombstone_blocked(project, "spec-change-approved", stem)
        assert second == []
        assert path.read_text() == before

    # e) no-match leaves file unchanged
    def test_no_match_leaves_file_unchanged(self, project):
        stem = "20260610T161500-plugin-agent-to-human-spec-change-request"
        path = project / ".agents" / "blocked" / "plugin-agent.md"
        _write_blocked(path, {"title": "thing", "stem": stem, "change": "thing"})
        before = path.read_text()
        result = _auto_tombstone_blocked(
            project,
            "spec-change-approved",
            "Original proposal "
            "20260610T161500-other-agent-to-human-spec-change-request approved",
        )
        assert result == []
        assert path.read_text() == before

    # f) entry without Change: field skipped silently on task-assignment
    def test_missing_change_field_skipped_on_task_assignment(self, project):
        path = project / ".agents" / "blocked" / "plugin-agent.md"
        # Legacy entry format — no Change: field
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (
                "\n## Blocked: legacy entry\n"
                "- **Proposal**: 20260601T000000-old-agent-to-human-spec-change-request\n"
                "- **Blocked since**: 2026-06-01T00:00:00Z\n"
                "- **Depends on**: spec\n"
                "- **Task to resume**: implement\n"
            ),
            encoding="utf-8",
        )
        before = path.read_text()
        result = _auto_tombstone_blocked(
            project,
            "task-assignment",
            body="Tasks for legacy assigned",
            change_name="legacy",
        )
        assert result == []
        assert path.read_text() == before

    # g) multi-agent — only the matching one is updated
    def test_multi_agent_only_matching_updated(self, project):
        match_stem = "20260610T161500-plugin-agent-to-human-spec-change-request"
        other_stem = "20260610T000000-cli-agent-to-human-spec-change-request"
        _write_blocked(
            project / ".agents" / "blocked" / "plugin-agent.md",
            {"title": "match", "stem": match_stem, "change": "match"},
        )
        cli_path = project / ".agents" / "blocked" / "cli-agent.md"
        _write_blocked(
            cli_path,
            {"title": "other", "stem": other_stem, "change": "other"},
        )
        before_cli = cli_path.read_text()
        result = _auto_tombstone_blocked(project, "spec-change-approved", match_stem)
        assert len(result) == 1
        assert result[0]["agent"] == "plugin-agent"
        # cli-agent's file untouched
        assert cli_path.read_text() == before_cli


# ---------------------------------------------------------------------------
# Integration test (task 1.7) — propose → approve → verify tombstoned
# ---------------------------------------------------------------------------

@pytest.fixture
def integration_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    otaman = tmp_path / "my-otaman"
    otaman.mkdir()
    (otaman / "platform.yaml").write_text(
        yaml.dump({"project": "test", "version": "1.0"}), encoding="utf-8"
    )
    (otaman / ".agents").mkdir()

    # plugin-agent's repo (proposer)
    plugin = tmp_path / "repo-plugin"
    plugin.mkdir()
    (plugin / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: plugin-agent\n", encoding="utf-8"
    )
    # human "repo" — purely a cwd to send approval from
    human = tmp_path / "repo-human"
    human.mkdir()
    (human / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: human\n", encoding="utf-8"
    )
    return {"root": tmp_path, "otaman": otaman, "plugin": plugin, "human": human}


def test_full_propose_approve_tombstone_lifecycle(integration_workspace):
    """End-to-end: propose creates a blocked entry; an approval referencing
    the proposal stem auto-tombstones the entry and the file no longer
    reads as a `## Blocked:` header.

    F012 (2026-07-08): `spec-change-approved` is a PRIVILEGED_TYPES message
    — otaman_send now categorically refuses to send it over MCP (no
    interactive human confirmation is possible there); real approvals go
    through the CLI's human-confirmed `otaman approve` instead (see
    test_otaman_send_refuses_privileged_approval below). This test now
    exercises `_auto_tombstone_blocked` directly with the same body that a
    CLI-written approval message would carry, to keep the tombstone-
    matching logic itself under regression coverage.
    """
    propose_result = otaman_propose.fn(
        cwd=str(integration_workspace["plugin"]),
        title="my new feature",
        what_needs_to_change="add the thing",
        why_needed="because",
    )
    assert propose_result["proposed"] is True
    proposal_stem = propose_result["message"]

    blocked_file = integration_workspace["otaman"] / ".agents" / "blocked" / "plugin-agent.md"
    assert blocked_file.is_file()
    pre = blocked_file.read_text()
    assert "## Blocked: my new feature" in pre

    approval_body = (
        "The spec-change-request from **plugin-agent** has been **approved**.\n\n"
        f"**Original proposal**: {proposal_stem}\n"
    )
    tombstoned = _auto_tombstone_blocked(
        integration_workspace["otaman"], "spec-change-approved", approval_body
    )
    assert len(tombstoned) == 1
    assert tombstoned[0]["agent"] == "plugin-agent"

    post = blocked_file.read_text()
    # Line-leading active header is gone (would be matched by check-blocked.sh)
    assert "\n## Blocked: my new feature" not in post
    # Tombstone wrapper + reason trailer present
    assert "<!-- ## Blocked: my new feature" in post
    assert "— approved -->" in post


def test_otaman_send_refuses_privileged_approval(integration_workspace):
    """F012: otaman_send must refuse spec-change-approved outright — this is
    exactly the MCP path that would otherwise let any agent self-approve
    its own proposal, bypassing HITL. No blocked-entry file is touched."""
    otaman_propose.fn(
        cwd=str(integration_workspace["plugin"]),
        title="self-approval attempt",
        what_needs_to_change=".",
        why_needed=".",
    )
    send_result = otaman_send.fn(
        cwd=str(integration_workspace["human"]),
        to="plugin-agent",
        subject="Approved: self-approval attempt",
        body="**Original proposal**: fake-stem\n",
        msg_type="spec-change-approved",
        priority="high",
    )
    assert "error" in send_result
    assert "sent" not in send_result


def test_task_assignment_uses_change_field(integration_workspace):
    """Sending a task-assignment with ``change`` set tombstones a blocked
    entry whose ``Change:`` field matches — the fallback path that fires
    when the approval message body didn't carry the stem."""
    otaman_propose.fn(
        cwd=str(integration_workspace["plugin"]),
        title="another feature",
        what_needs_to_change=".",
        why_needed=".",
    )
    blocked_file = (
        integration_workspace["otaman"] / ".agents" / "blocked" / "plugin-agent.md"
    )
    assert "## Blocked: another feature" in blocked_file.read_text()

    send_result = otaman_send.fn(
        cwd=str(integration_workspace["human"]),
        to="plugin-agent",
        subject="Tasks for another-feature",
        body="Implement task 1.1.",  # no stem in body
        msg_type="task-assignment",
        priority="high",
        change="another-feature",
    )
    assert "auto_tombstoned" in send_result
    assert send_result["auto_tombstoned"][0]["reason"] == "task-assigned"
    text = blocked_file.read_text()
    assert "\n## Blocked: another feature" not in text
    assert "— task-assigned -->" in text


def test_change_field_written_to_outgoing_frontmatter(integration_workspace):
    """When ``change`` is passed to ``otaman_send`` it surfaces as a
    ``change:`` frontmatter field on the message file."""
    result = otaman_send.fn(
        cwd=str(integration_workspace["plugin"]),
        to="spec-agent",
        subject="task complete on x",
        body="done",
        msg_type="task-complete",
        change="some-change-name",
    )
    bus = integration_workspace["otaman"] / ".agents" / "bus" / "active"
    msg_file = bus / f"{result['stem']}.md"
    text = msg_file.read_text()
    assert "change: some-change-name" in text
