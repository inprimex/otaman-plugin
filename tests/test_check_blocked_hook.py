"""Tests for scripts/check-blocked.sh (issue #73).

The hook must stop over-blocking: a pending spec proposal should only deny
writes to CODE in the agent's OWN repo, while self-healing entries whose
proposal is already approved/rejected and always allowing coordination
data (.agents/**), scratchpad, and other repos. Denials must surface the
reason (permissionDecisionReason + systemMessage) and exit 0, not exit 2.

These tests execute the real shell hook via subprocess against a fixture
otaman project, mirroring test_bus_status_hook.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "scripts" / "check-blocked.sh"
AGENT = "test-agent"


@pytest.fixture
def project(tmp_path):
    """A fixture otaman project: an otaman folder (proj/) plus two sibling
    repos, one owned by AGENT and one by another agent."""
    root = tmp_path / "proj"
    (root / ".agents" / "blocked").mkdir(parents=True)
    (root / ".agents" / "bus" / "active" / "acks").mkdir(parents=True)
    (root / "platform.yaml").write_text("project: test\nversion: \"1.0\"\n", encoding="utf-8")
    (root / ".otaman").write_text(".\n", encoding="utf-8")
    # Pretty-printed (one field per line) to match what `otaman init`
    # actually generates — the sed field extraction in check-blocked.sh /
    # check-ownership.sh reads one "path"/"owner" per line.
    (root / ".agents" / "ownership.json").write_text(
        json.dumps(
            {
                "project": "test",
                "repos": [
                    {"name": "myrepo", "path": "../myrepo", "owner": AGENT},
                    {"name": "otherrepo", "path": "../otherrepo", "owner": "other-agent"},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (tmp_path / "myrepo" / "src").mkdir(parents=True)
    (tmp_path / "otherrepo" / "src").mkdir(parents=True)
    return {
        "root": root,
        "owned_file": tmp_path / "myrepo" / "src" / "foo.py",
        "other_file": tmp_path / "otherrepo" / "src" / "bar.py",
        "coord_file": root / ".agents" / "blocked" / f"{AGENT}.md",
        "scratch_file": tmp_path / "scratch" / "note.txt",
        "blocked_path": root / ".agents" / "blocked" / f"{AGENT}.md",
        "acks": root / ".agents" / "bus" / "active" / "acks",
    }


def set_blocked(project, content: str) -> None:
    project["blocked_path"].write_text(content, encoding="utf-8")


def run_hook(project, target: Path, *, ownership: bool = True) -> tuple[int, dict | None]:
    """Run the hook for a Write to `target`. Returns (returncode, parsed_json
    or None if allow/no-output)."""
    root = project["root"]
    if not ownership:
        (root / ".agents" / "ownership.json").unlink()
    payload = json.dumps(
        {"tool_name": "Edit", "tool_input": {"file_path": str(target)}, "file_path": str(target)}
    )
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(root),
        env={"PATH": "/usr/bin:/bin", "OTAMAN_AGENT": AGENT, "HOME": str(root)},
    )
    out = proc.stdout.strip()
    parsed = json.loads(out) if out else None
    return proc.returncode, parsed


def assert_allowed(rc: int, parsed: dict | None):
    assert rc == 0, f"expected exit 0, got {rc}"
    assert parsed is None, f"expected no output (allow), got {parsed}"


def assert_denied(rc: int, parsed: dict | None):
    # Deny MUST exit 0 (not 2) so Claude Code reads the JSON — issue #73.
    assert rc == 0, f"deny must exit 0 (not {rc}); exit 2 makes stdout JSON be ignored"
    assert parsed is not None, "deny must emit JSON on stdout"
    hso = parsed["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert hso.get("permissionDecisionReason"), "reason must be surfaced to the model"
    assert parsed.get("systemMessage"), "systemMessage must be surfaced to the operator"


_ACTIVE_ENTRY = (
    "## Blocked: Feature X pending\n"
    "- **Proposal**: 20260101T000000-test-agent-to-human-spec-change-request\n"
    "- **Blocked since**: 2026-01-01T00:00:00Z\n"
)


class TestAllowPaths:
    def test_no_blocked_file_allows(self, project):
        # Fixture creates the blocked/ dir but no blocked file by default.
        assert not project["blocked_path"].exists()
        assert_allowed(*run_hook(project, project["owned_file"]))

    def test_active_block_allows_coordination_file(self, project):
        set_blocked(project, _ACTIVE_ENTRY)
        # Editing the .agents/ blocked file itself must never be frozen —
        # otherwise clearing a stale block is a catch-22.
        assert_allowed(*run_hook(project, project["coord_file"]))

    def test_active_block_allows_scratchpad(self, project):
        set_blocked(project, _ACTIVE_ENTRY)
        assert_allowed(*run_hook(project, project["scratch_file"]))

    def test_active_block_allows_other_agents_repo(self, project):
        # check-ownership.sh handles other-agent repos; check-blocked must
        # not double-deny with the wrong (blocked) reason.
        set_blocked(project, _ACTIVE_ENTRY)
        assert_allowed(*run_hook(project, project["other_file"]))

    def test_tombstoned_entry_allows(self, project):
        set_blocked(
            project,
            "<!-- ## Blocked: Old thing\n"
            "- **Proposal**: 20259999T000000-test-agent-to-human-spec-change-request\n"
            "cleared 2026-01-01 — approved -->\n",
        )
        assert_allowed(*run_hook(project, project["owned_file"]))

    def test_missing_ownership_json_allows(self, project):
        set_blocked(project, _ACTIVE_ENTRY)
        assert_allowed(*run_hook(project, project["owned_file"], ownership=False))


class TestSelfHeal:
    def test_approved_proposal_self_heals(self, project):
        set_blocked(project, _ACTIVE_ENTRY)
        (project["acks"] / "20260101T000000-test-agent-to-human-spec-change-request.human.ack").write_text(
            "approved\n", encoding="utf-8"
        )
        assert_allowed(*run_hook(project, project["owned_file"]))

    def test_rejected_proposal_self_heals(self, project):
        set_blocked(project, _ACTIVE_ENTRY)
        (project["acks"] / "20260101T000000-test-agent-to-human-spec-change-request.human.ack").write_text(
            "rejected\n", encoding="utf-8"
        )
        assert_allowed(*run_hook(project, project["owned_file"]))

    def test_read_ack_does_not_self_heal(self, project):
        # A "read" ack is not a resolution — the block stays active.
        set_blocked(project, _ACTIVE_ENTRY)
        (project["acks"] / "20260101T000000-test-agent-to-human-spec-change-request.human.ack").write_text(
            "read\n", encoding="utf-8"
        )
        assert_denied(*run_hook(project, project["owned_file"]))


class TestDenyPaths:
    def test_active_block_denies_owned_repo_code(self, project):
        set_blocked(project, _ACTIVE_ENTRY)
        assert_denied(*run_hook(project, project["owned_file"]))

    def test_entry_without_proposal_denies(self, project):
        # No **Proposal** field → cannot self-heal → still blocks own code.
        set_blocked(project, "## Blocked: No proposal field entry\n- **Blocked since**: x\n")
        assert_denied(*run_hook(project, project["owned_file"]))

    def test_mixed_entries_still_deny_on_pending(self, project):
        set_blocked(
            project,
            "## Blocked: Approved one\n"
            "- **Proposal**: 20260101T000000-test-agent-to-human-spec-change-request\n"
            "## Blocked: Still pending\n"
            "- **Proposal**: 20260202T000000-test-agent-to-human-spec-change-request\n",
        )
        (project["acks"] / "20260101T000000-test-agent-to-human-spec-change-request.human.ack").write_text(
            "approved\n", encoding="utf-8"
        )
        rc, parsed = run_hook(project, project["owned_file"])
        assert_denied(rc, parsed)
        # Only the still-pending entry should be counted / named.
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "Still pending" in reason
        assert "Approved one" not in reason
        assert "1 pending" in reason

    def test_deny_reason_names_title_and_remedy(self, project):
        set_blocked(project, _ACTIVE_ENTRY)
        _, parsed = run_hook(project, project["owned_file"])
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "Feature X pending" in reason
        assert "otaman blocked --clear" in reason

    def test_deny_output_valid_json_with_quoted_title(self, project):
        set_blocked(
            project,
            '## Blocked: Title with "quotes" and \\ backslash\n'
            "- **Proposal**: 20260101T000000-test-agent-to-human-spec-change-request\n",
        )
        rc, parsed = run_hook(project, project["owned_file"])
        # json.loads in run_hook already succeeded → escaping is valid.
        assert_denied(rc, parsed)
