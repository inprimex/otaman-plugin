"""Tests for response-contract badges in bus_server.

Per inter-agent-request-response-contract tasks 3.2 + 3.3:
- ``awaiting-response`` when ``expects-response: true`` and no outbound
  ``reply-to: <id>`` from the calling agent.
- ``deadline-approaching`` when ``response-deadline`` is within the next 2 hours.
- ``deadline-passed`` when ``response-deadline`` has elapsed.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers"))

from bus_server import (
    _collect_outbound_reply_ids,
    _compute_response_badges,
    _parse_iso8601,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bus_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bus"
    d.mkdir()
    return d


def _write_msg(bus: Path, name: str, frontmatter: dict[str, str]) -> Path:
    """Write a minimal bus message file with the given frontmatter values."""
    lines = ["---"]
    for k, v in frontmatter.items():
        lines.append(f"{k}: {v}")
    lines.extend(["---", "", "## Subject: test", ""])
    path = bus / f"{name}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


NOW = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _parse_iso8601
# ---------------------------------------------------------------------------

class TestParseIso8601:
    def test_z_suffix_is_accepted(self):
        dt = _parse_iso8601("2026-06-04T12:00:00Z")
        assert dt is not None
        assert dt.tzinfo is timezone.utc or dt.utcoffset() == timedelta(0)

    def test_offset_suffix_is_accepted(self):
        dt = _parse_iso8601("2026-06-04T12:00:00+02:00")
        assert dt is not None
        assert dt.utcoffset() == timedelta(hours=2)

    def test_naive_string_rejected(self):
        # spec mandates timezone-aware deadlines
        assert _parse_iso8601("2026-06-04T12:00:00") is None

    def test_empty_string_returns_none(self):
        assert _parse_iso8601("") is None

    def test_garbage_returns_none(self):
        assert _parse_iso8601("not-a-date") is None


# ---------------------------------------------------------------------------
# _collect_outbound_reply_ids
# ---------------------------------------------------------------------------

class TestCollectOutboundReplyIds:
    def test_empty_dir_returns_empty_set(self, tmp_path: Path):
        # bus dir doesn't exist
        assert _collect_outbound_reply_ids("plugin-agent", tmp_path / "missing") == set()

    def test_returns_reply_to_targets_for_agent(self, bus_dir: Path):
        _write_msg(bus_dir, "20260604T120000-plugin-agent-reply-a", {
            "id": "20260604T120000-reply-a",
            "from": "plugin-agent",
            "to": "cli-agent",
            "reply-to": "20260603T140000-orig-a",
        })
        _write_msg(bus_dir, "20260604T120001-plugin-agent-reply-b", {
            "id": "20260604T120001-reply-b",
            "from": "plugin-agent",
            "to": "spec-agent",
            "reply-to": "20260603T140100-orig-b",
        })
        # Different agent — should not contribute
        _write_msg(bus_dir, "20260604T120002-other-agent-reply", {
            "id": "20260604T120002-reply-c",
            "from": "other-agent",
            "to": "plugin-agent",
            "reply-to": "20260603T140200-orig-c",
        })
        # No reply-to at all — should not contribute
        _write_msg(bus_dir, "20260604T120003-plugin-agent-original", {
            "id": "20260604T120003-orig-d",
            "from": "plugin-agent",
            "to": "spec-agent",
        })
        ids = _collect_outbound_reply_ids("plugin-agent", bus_dir)
        assert ids == {"20260603T140000-orig-a", "20260603T140100-orig-b"}


# ---------------------------------------------------------------------------
# _compute_response_badges — awaiting-response
# ---------------------------------------------------------------------------

class TestAwaitingResponseBadge:
    def test_expects_response_true_no_reply_gets_badge(self):
        fm = {"id": "20260604T080000-orig", "expects-response": "true"}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "awaiting-response" in badges

    def test_expects_response_true_with_reply_no_badge(self):
        fm = {"id": "20260604T080000-orig", "expects-response": "true"}
        reply_ids = {"20260604T080000-orig"}
        badges = _compute_response_badges(fm, outbound_reply_ids=reply_ids, now=NOW)
        assert "awaiting-response" not in badges

    def test_expects_response_false_no_badge(self):
        fm = {"id": "20260604T080000-orig", "expects-response": "false"}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "awaiting-response" not in badges

    def test_expects_response_absent_no_badge(self):
        fm = {"id": "20260604T080000-orig"}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "awaiting-response" not in badges

    def test_expects_response_true_no_id_still_flags(self):
        # Conservative default: surface the contract gap when we can't match
        # by id (older message format without id field).
        fm = {"expects-response": "true"}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "awaiting-response" in badges

    def test_expects_response_case_insensitive(self):
        fm = {"id": "x", "expects-response": "True"}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "awaiting-response" in badges


# ---------------------------------------------------------------------------
# _compute_response_badges — deadline badges
# ---------------------------------------------------------------------------

class TestDeadlineBadges:
    def test_deadline_within_2h_is_approaching(self):
        fm = {"response-deadline": (NOW + timedelta(hours=1)).isoformat()}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "deadline-approaching" in badges
        assert "deadline-passed" not in badges

    def test_deadline_far_future_no_badge(self):
        fm = {"response-deadline": (NOW + timedelta(hours=3)).isoformat()}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "deadline-approaching" not in badges
        assert "deadline-passed" not in badges

    def test_deadline_past_is_passed(self):
        fm = {"response-deadline": (NOW - timedelta(minutes=5)).isoformat()}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "deadline-passed" in badges
        assert "deadline-approaching" not in badges

    def test_deadline_far_past_is_passed(self):
        fm = {"response-deadline": (NOW - timedelta(days=2)).isoformat()}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "deadline-passed" in badges

    def test_deadline_exactly_at_2h_boundary_is_approaching(self):
        # Boundary: delta == 7200s → still "approaching" (inclusive)
        fm = {"response-deadline": (NOW + timedelta(seconds=7200)).isoformat()}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "deadline-approaching" in badges

    def test_malformed_deadline_silently_skipped(self):
        fm = {"response-deadline": "tomorrow-please"}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "deadline-approaching" not in badges
        assert "deadline-passed" not in badges

    def test_naive_deadline_rejected(self):
        # No timezone offset → spec violation → silently skipped
        fm = {"response-deadline": "2026-06-04T12:00:00"}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert badges == []

    def test_no_deadline_field_no_badge(self):
        fm = {"id": "x"}
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "deadline-approaching" not in badges
        assert "deadline-passed" not in badges


# ---------------------------------------------------------------------------
# _compute_response_badges — combinations
# ---------------------------------------------------------------------------

class TestBadgeCombinations:
    def test_expects_response_plus_deadline_passed_both_badges(self):
        fm = {
            "id": "20260604T080000-orig",
            "expects-response": "true",
            "response-deadline": (NOW - timedelta(hours=1)).isoformat(),
        }
        badges = _compute_response_badges(fm, outbound_reply_ids=set(), now=NOW)
        assert "awaiting-response" in badges
        assert "deadline-passed" in badges

    def test_no_response_fields_returns_empty_list(self):
        badges = _compute_response_badges({}, outbound_reply_ids=set(), now=NOW)
        assert badges == []
