"""Tests for bus-cc-routing task 2.3 — ``otaman_check`` cc_messages split.

After the 2.3 change, ``otaman_check`` returns CC copies in a new
``cc_messages: list`` key (separate from the primary ``messages`` list):

- Files with ``x-cc: true`` and a ``-cc-<agent>-`` filename suffix are
  routed to the targeted recipient's ``cc_messages`` list only.
- The primary message's filename has no ``-cc-`` suffix; it lands in
  ``messages`` as before.
- Each ``cc_messages`` entry carries the original ``to`` field plus the
  ``cc`` list (so the recipient can see who else got copies).
- ``counts`` remains tied to the primary ``messages`` list for back-compat.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "servers"))

from bus_server import (  # noqa: E402
    _extract_cc_recipient_from_stem,
    otaman_check,
    otaman_send,
)


# ---------------------------------------------------------------------------
# Helper — workspace fixture with routing rules
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Sibling layout with a platform.yaml that fans out to:human → cc:[spec-agent,cpo-agent]
    on urgent priority, and a sender repo identified as runner-agent.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    otaman = tmp_path / "my-otaman"
    otaman.mkdir()
    (otaman / ".agents").mkdir()
    platform_data = {
        "project": "test",
        "version": "1.0",
        "bus": {
            "routing_rules": [
                {"when": {"to": "human"}, "cc": ["spec-agent"]},
                {
                    "when": {"to": "human", "priority": ["high", "urgent"]},
                    "cc": ["cpo-agent"],
                },
            ]
        },
    }
    (otaman / "platform.yaml").write_text(yaml.dump(platform_data), encoding="utf-8")

    sender_repo = tmp_path / "repo-runner"
    sender_repo.mkdir()
    (sender_repo / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: runner-agent\n", encoding="utf-8"
    )

    # Reader repos for spec-agent + cpo-agent + an uninvolved agent
    spec_repo = tmp_path / "repo-spec"
    spec_repo.mkdir()
    (spec_repo / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: spec-agent\n", encoding="utf-8"
    )
    cpo_repo = tmp_path / "repo-cpo"
    cpo_repo.mkdir()
    (cpo_repo / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: cpo-agent\n", encoding="utf-8"
    )
    other_repo = tmp_path / "repo-other"
    other_repo.mkdir()
    (other_repo / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: deploy-agent\n", encoding="utf-8"
    )

    return {
        "root": tmp_path,
        "otaman": otaman,
        "sender": sender_repo,
        "spec": spec_repo,
        "cpo": cpo_repo,
        "other": other_repo,
    }


# ---------------------------------------------------------------------------
# Unit tests — _extract_cc_recipient_from_stem
# ---------------------------------------------------------------------------

class TestExtractCcRecipientFromStem:
    def test_cc_copy_stem_returns_recipient(self):
        stem = "20260609T120000-runner-agent-to-human-cc-spec-agent-thing"
        # cc list is the disambiguator — agent names contain hyphens
        assert (
            _extract_cc_recipient_from_stem(stem, ["spec-agent", "cpo-agent"])
            == "spec-agent"
        )

    def test_primary_stem_returns_none(self):
        stem = "20260609T120000-runner-agent-to-human-thing"
        assert _extract_cc_recipient_from_stem(stem, ["spec-agent"]) is None

    def test_slug_with_dashes_picks_right_recipient(self):
        # The slug starts with a hyphen — without the cc list, naive regex
        # would greedily eat into the slug; the cc-list lookup avoids that.
        stem = "20260609T120000-runner-agent-to-human-cc-spec-agent-some-urgent-thing"
        assert (
            _extract_cc_recipient_from_stem(stem, ["spec-agent", "cpo-agent"])
            == "spec-agent"
        )

    def test_no_cc_list_returns_none(self):
        # Without the cc list as a name dictionary, the helper has no
        # reliable way to disambiguate agent-vs-slug boundary.
        stem = "20260609T120000-runner-agent-to-human-cc-spec-agent-thing"
        assert _extract_cc_recipient_from_stem(stem, []) is None

    def test_no_dashes_around_cc_returns_none(self):
        # `-ccfoo-` shouldn't match (no separator after `cc`)
        stem = "20260609T120000-runner-agent-to-human-ccfoo-bar"
        assert _extract_cc_recipient_from_stem(stem, ["foo"]) is None


# ---------------------------------------------------------------------------
# Integration — fan-out + check
# ---------------------------------------------------------------------------

def _send_urgent_to_human(workspace) -> dict:
    return otaman_send.fn(
        cwd=str(workspace["sender"]),
        to="human",
        subject="urgent thing",
        body="see me",
        priority="urgent",
    )


class TestCcMessagesSplit:
    def test_spec_agent_sees_their_cc_copy_in_cc_messages(self, workspace):
        _send_urgent_to_human(workspace)

        # spec-agent checks their inbox
        spec_view = otaman_check.fn(
            cwd=str(workspace["spec"]), status_filter="pending"
        )
        # CC copy is in cc_messages, not in messages
        assert len(spec_view["messages"]) == 0
        assert len(spec_view["cc_messages"]) == 1
        entry = spec_view["cc_messages"][0]
        assert entry["from"] == "runner-agent"
        assert entry["to"] == "human"
        assert "spec-agent" in entry["cc"]
        assert "cpo-agent" in entry["cc"]
        assert entry["subject"] == "urgent thing"

    def test_cpo_agent_sees_only_their_own_copy(self, workspace):
        _send_urgent_to_human(workspace)

        cpo_view = otaman_check.fn(cwd=str(workspace["cpo"]), status_filter="pending")
        assert len(cpo_view["cc_messages"]) == 1
        # Their copy is for them — the filename embeds cpo-agent
        stem = cpo_view["cc_messages"][0]["stem"]
        assert "-cc-cpo-agent-" in stem

    def test_other_agent_sees_no_cc_copies(self, workspace):
        _send_urgent_to_human(workspace)

        other_view = otaman_check.fn(
            cwd=str(workspace["other"]), status_filter="pending"
        )
        # deploy-agent is not in the routing rules' cc lists; they see nothing
        assert other_view["messages"] == []
        assert other_view["cc_messages"] == []

    def test_primary_message_to_self_lands_in_messages_not_cc(self, workspace, monkeypatch):
        """A message addressed directly to the agent (no x-cc) must stay in
        the primary `messages` list, regardless of the CC routing change."""
        # Send a direct task-assignment to spec-agent (no routing rule on this `to`).
        otaman_send.fn(
            cwd=str(workspace["sender"]),
            to="spec-agent",
            subject="directly to you",
            body="hi",
            priority="normal",
        )

        view = otaman_check.fn(cwd=str(workspace["spec"]), status_filter="pending")
        assert len(view["messages"]) == 1
        assert view["messages"][0]["subject"] == "directly to you"
        assert view["cc_messages"] == []

    def test_cc_messages_field_always_present(self, workspace):
        """`cc_messages` is always in the response (empty list when no CC),
        so consumers can rely on the key existing."""
        view = otaman_check.fn(cwd=str(workspace["other"]), status_filter="pending")
        assert "cc_messages" in view
        assert view["cc_messages"] == []

    def test_counts_unchanged_by_cc_split(self, workspace):
        """`counts` totals primary messages only — preserves back-compat
        for downstream consumers that look at pending/read/resolved counts."""
        # One direct + a CC fan-out for spec-agent
        otaman_send.fn(
            cwd=str(workspace["sender"]),
            to="spec-agent",
            subject="direct",
            body=".",
            priority="normal",
        )
        otaman_send.fn(
            cwd=str(workspace["sender"]),
            to="human",
            subject="urgent",
            body=".",
            priority="urgent",
        )

        view = otaman_check.fn(cwd=str(workspace["spec"]), status_filter="pending")
        # 1 primary + 1 CC copy in spec-agent's view
        assert len(view["messages"]) == 1
        assert len(view["cc_messages"]) == 1
        # Counts only reflect the primary
        assert view["counts"]["pending"] == 1

    def test_cc_messages_sorted_by_priority_and_timestamp(self, workspace):
        # Two CC copies for spec-agent at different priorities
        otaman_send.fn(
            cwd=str(workspace["sender"]),
            to="human",
            subject="normal-msg",
            body=".",
            priority="normal",  # rule 1 (no priority gate) fires → spec-agent
        )
        otaman_send.fn(
            cwd=str(workspace["sender"]),
            to="human",
            subject="urgent-msg",
            body=".",
            priority="urgent",  # rules 1 + 2 fire → spec-agent + cpo-agent
        )

        view = otaman_check.fn(cwd=str(workspace["spec"]), status_filter="pending")
        assert len(view["cc_messages"]) == 2
        # urgent before normal
        assert view["cc_messages"][0]["subject"] == "urgent-msg"
        assert view["cc_messages"][1]["subject"] == "normal-msg"
