"""The `otaman_cleanup` MCP tool must say it can destroy messages.

An MCP tool's docstring IS its safety surface: it is what an agent reads to
decide whether calling it is safe. This one said "Archive old bus messages
that are fully acknowledged" and never mentioned deletion.

deploy-agent lost 591 bus messages to the underlying verb on 2026-10-01
(20261001T215947) and recovered them only because otaman-meta happens to be a
git repo with the deletions uncommitted. The dry run reported "Archived",
listed the month buckets, and never said delete — they read it as "these will
be moved", said so, and were wrong.

This tool is a SECOND path to that operation. It is inert today only because
its helper script is not shipped, which is luck rather than design.
"""

from __future__ import annotations

import inspect

from otaman_plugin.servers import bus_server


def _doc() -> str:
    fn = bus_server.otaman_cleanup
    fn = getattr(fn, "fn", fn)  # FastMCP wraps the callable
    return inspect.getdoc(fn) or ""


class TestTheDocstringNamesTheDestruction:
    def test_it_says_messages_can_be_destroyed(self):
        doc = _doc().lower()
        assert "destroy" in doc or "delete" in doc

    def test_it_does_not_describe_itself_as_archive_only(self):
        """The exact framing that misled: 'archive' with no mention of loss."""
        doc = _doc()
        first_line = doc.splitlines()[0] if doc else ""
        assert "DESTROY" in first_line or "delete" in first_line.lower(), (
            f"the summary line still reads as archive-only: {first_line!r}"
        )

    def test_it_warns_that_dry_run_does_not_protect(self):
        """dry_run is the trap, not the safeguard — it reports 'Archived' for
        messages that will be purged."""
        doc = _doc().lower()
        assert "dry_run" in doc or "dry run" in doc
        assert "does not protect" in doc or "not the safeguard" in doc

    def test_the_dry_run_argument_itself_carries_the_warning(self):
        """An agent skimming Args: must not get the reassuring half alone."""
        doc = _doc()
        idx = doc.find("dry_run: Reports intent only")
        assert idx != -1, "the dry_run arg description was not updated"
        assert "not distinguish" in doc[idx : idx + 300].lower()

    def test_it_records_the_incident_so_the_reason_survives(self):
        """A warning without its evidence gets trimmed by the next editor who
        finds it verbose."""
        doc = _doc()
        assert "591" in doc
        assert "20261001T215947" in doc

    def test_it_states_the_tool_is_currently_inert(self):
        """Being inert is why this has not bitten here. Saying so keeps anyone
        from reading the warning and concluding the tool is dangerous NOW,
        or from restoring the helper without re-reading it."""
        assert "INERT" in _doc()


class TestTheToolStillRefusesSafely:
    def test_a_missing_helper_returns_an_error_not_a_traceback(self, tmp_path):
        """The inertness must be a clean refusal. If this ever starts doing
        something, the docstring above is the thing that was relied on."""
        fn = getattr(bus_server.otaman_cleanup, "fn", bus_server.otaman_cleanup)
        result = fn(cwd=str(tmp_path))
        assert isinstance(result, dict)
        assert "error" in result
