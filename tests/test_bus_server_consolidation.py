"""shared-logic-single-home 1.2/1.3 — bus_server holds no parser of its own.

This module carried SIX local definitions of formats the whole fleet shares:
a frontmatter line-splitter, a bespoke `cc:` recovery (needed only because
that splitter threw away YAML's types), four blocked-entry regexes, plus
hand-built bus filenames. Every one is now otaman-core's.

These tests assert the ABSENCE of local parsing as much as the presence of
the shared calls, because the failure mode being prevented is someone adding
a seventh "just for this one case".
"""

from __future__ import annotations

import inspect
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from otaman_core.bus_stem import build_filename, slugify  # noqa: E402
from otaman_core.frontmatter import parse  # noqa: E402

from otaman_plugin.servers import bus_server  # noqa: E402

SRC = Path(bus_server.__file__).read_text(encoding="utf-8")


class TestNoLocalParsers:
    def test_no_frontmatter_fence_regex(self):
        assert r'r"^---' not in SRC, "a local frontmatter parser is back"

    def test_parse_cc_field_is_gone(self):
        """It existed only to recover list semantics YAML already has."""
        assert not hasattr(bus_server, "_parse_cc_field")

    def test_no_blocked_entry_regexes(self):
        for name in (
            "_BLOCKED_ENTRY_RE",
            "_PROPOSAL_FIELD_RE",
            "_CHANGE_FIELD_RE",
            "_BLOCKED_TITLE_RE",
        ):
            assert not hasattr(bus_server, name), f"{name} is back"

    def test_no_hand_built_bus_filenames(self):
        """The convention is written here and parsed fleet-wide; one writer."""
        assert not re.search(r'f"\{ts\}-\{agent\}-to-', SRC)
        assert not re.search(r'f"\{now_ts\}-\{agent\}-to-', SRC)

    def test_consumes_core_for_each_format(self):
        assert "from otaman_core import frontmatter" in SRC
        assert "from otaman_core.bus_stem import" in SRC
        assert "from otaman_core import blocked_entries" in SRC


class TestTypedFrontmatter:
    MSG = (
        "---\n"
        "id: 20260921T000000-x\n"
        "from: plugin-agent\n"
        "to: spec-agent\n"
        "type: info\n"
        "timestamp: 2026-09-21T00:00:00Z\n"
        "cc: [core-agent, cli-agent]\n"
        "x-cc: true\n"
        "---\n\nbody\n"
    )

    def test_values_come_back_typed(self):
        fm = bus_server._frontmatter(self.MSG)
        assert fm["cc"] == ["core-agent", "cli-agent"]
        assert fm["x-cc"] is True
        assert isinstance(fm["timestamp"], datetime)

    def test_fm_text_renders_any_type_as_text(self):
        """Several callers `.strip()` what they read; a bool or datetime
        would raise. `_fm_text` is the boundary that keeps them safe."""
        fm = bus_server._frontmatter(self.MSG)
        assert bus_server._fm_text(fm, "x-cc") == "true"
        assert bus_server._fm_text(fm, "timestamp") == "2026-09-21T00:00:00Z"
        assert bus_server._fm_text(fm, "absent", "fallback") == "fallback"

    def test_timestamps_normalise_to_z(self):
        """Deliberate: 93 of 2800 scalar fields on the live bus were written
        with `+00:00`. Both are valid ISO-8601 UTC and every writer here emits
        `Z`, so old messages now display consistently with new ones."""
        msg = self.MSG.replace("2026-09-21T00:00:00Z", "2026-09-21T00:00:00+00:00")
        fm = bus_server._frontmatter(msg)
        assert bus_server._fm_text(fm, "timestamp").endswith("Z")

    @pytest.mark.parametrize("raw,expected", [("true", True), ("True", True), ("no", False)])
    def test_flag_accepts_typed_and_legacy_strings(self, raw, expected):
        """A strict `is True` would stop honouring every message already on
        the bus, and every caller that hands in a hand-built dict."""
        assert bus_server._fm_flag({"k": raw}, "k") is expected
        assert bus_server._fm_flag({"k": expected}, "k") is expected


class TestFilenamesUnchanged:
    def test_primary_filename_matches_the_retired_hand_built_form(self):
        """Byte-compatibility matters: these names are parsed fleet-wide and
        the bus already holds thousands of them."""
        ts, agent, to = "20260921T120000", "plugin-agent", "spec-agent"
        subject = "Re: 1.2 — the dep IS wrong-way: otaman-cli"
        legacy_slug = re.sub(r"[^a-z0-9]+", "-", subject.lower())[:40].strip("-")
        legacy = f"{ts}-{agent}-to-{to}-{legacy_slug}.md"
        assert (
            build_filename(
                timestamp=ts, sender=agent, recipient=to, slug=slugify(subject, max_len=40)
            )
            == legacy
        )

    def test_cc_copy_keeps_its_recipient_segment(self):
        """The `-cc-<rcpt>-` segment is this module's convention layered on
        the shared slug, so copies never collide with the primary."""
        ts, agent, to, rcpt = "20260921T120000", "plugin-agent", "spec-agent", "core-agent"
        name = build_filename(timestamp=ts, sender=agent, recipient=to, slug=f"cc-{rcpt}-note")
        assert name == f"{ts}-{agent}-to-{to}-cc-{rcpt}-note.md"


class TestTerminatorUsesParsedEntries:
    def test_predicate_receives_an_entry_not_raw_text(self):
        """Callers match on `.proposal` / `.change` rather than re-deriving
        them from a text block — that re-derivation was the duplication."""
        src = inspect.getsource(bus_server._tombstone_entries_matching)
        assert "parse_entries" in src
        assert "tombstone(" in src
        assert "finditer" not in src

    def test_reports_display_title_so_malformed_shows_everywhere(self):
        src = inspect.getsource(bus_server._tombstone_entries_matching)
        assert "display_title" in src


class TestBodyComesFromTheSharedParser:
    def test_read_message_does_not_re_split_the_fence(self):
        src = inspect.getsource(bus_server.otaman_read_message.fn)
        assert "body_match" not in src
        assert "_core_frontmatter.parse" in src

    def test_body_matches_cores_split(self):
        msg = "---\nfrom: a\nto: b\n---\n\nhello body\n"
        _, body = parse(msg)
        assert body.strip() == "hello body"
