"""shared-logic-single-home 1.1 (conformance half) — otaman_check reports the
same blocked state as the CLI.

The defect: `otaman_check` carried its OWN inline regex that REQUIRED
`- **Proposal**:`, so an awaiting-dependency entry — keyed by `**Change**:`,
with no proposal at all — was SILENTLY DROPPED from the agent's own blocked
list over MCP while the CLI showed it. Measured on a two-entry fixture before
the fix: cli's parser saw both, otaman_check reported one.

Same class as the defect blocked-entry-lifecycle killed, except silently
incomplete rather than stale — and this surface is the one that tells an agent
"you are genuinely blocked", so omitting an entry is the failure that matters.

It was also a FIFTH parse site in bus_server.py (the four terminator regexes
being the others). My own survey counted four and missed it, which is the
argument for one parser rather than a carefully-maintained set — so these
tests assert PARITY WITH CORE rather than re-encoding the format locally.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from otaman_core.blocked_entries import parse_entries  # noqa: E402

from otaman_plugin.servers import bus_server  # noqa: E402
from otaman_plugin.servers.bus_server import (  # noqa: E402
    _blocked_entries,
    otaman_blocked,
    otaman_check,
)

APPROVAL = """
## Blocked: approval wait
- **Proposal**: 20260101T000000-plugin-agent-to-human-spec-change-request
- **Change**: appr
- **Blocked since**: 2026-01-01T00:00:00Z
"""

DEPENDENCY = """
## Blocked: dependency wait
- **Change**: some-dependency
- **Kind**: awaiting-dependency
- **Blocked since**: 2026-01-01T00:00:00Z
"""

MALFORMED = """
## Blocked:
- **Change**: malformed-one
- **Blocked since**: 2026-01-01T00:00:00Z
"""


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / "m"
    root.mkdir()
    (root / "platform.yaml").write_text(
        yaml.dump({"project": "t", "version": "1.0"}), encoding="utf-8"
    )
    (root / ".agents" / "blocked").mkdir(parents=True)
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / ".otaman").write_text("../m\nagent: plugin-agent\n", encoding="utf-8")
    return {"root": root, "repo": repo}


def _write(workspace, text: str) -> None:
    (workspace["root"] / ".agents" / "blocked" / "plugin-agent.md").write_text(
        text, encoding="utf-8"
    )


def _tasks(workspace) -> list[str]:
    return [b["task"] for b in otaman_check.fn(cwd=str(workspace["repo"]))["blocked_tasks"]]


class TestTheDefect:
    def test_dependency_entry_is_no_longer_dropped(self, workspace):
        """The regression this fix exists for."""
        _write(workspace, APPROVAL + DEPENDENCY)
        assert _tasks(workspace) == ["approval wait", "dependency wait"]

    def test_dependency_only_file_is_not_empty(self, workspace):
        """The worst shape of the old bug: an agent blocked ONLY on
        dependencies saw an empty blocked list and read it as "not blocked"."""
        _write(workspace, DEPENDENCY)
        assert _tasks(workspace) == ["dependency wait"]

    def test_kind_and_ref_are_reported(self, workspace):
        _write(workspace, APPROVAL + DEPENDENCY)
        got = otaman_check.fn(cwd=str(workspace["repo"]))["blocked_tasks"]
        assert [b["kind"] for b in got] == ["awaiting-approval", "awaiting-dependency"]
        assert got[1]["ref"] == "some-dependency", "a dependency entry's ref is its change"


class TestParityWithCore:
    """Assert agreement with core's parser rather than re-encoding the format
    here — a local expectation would be a sixth definition of the shape."""

    @pytest.mark.parametrize(
        "text",
        [APPROVAL, DEPENDENCY, MALFORMED, APPROVAL + DEPENDENCY, APPROVAL + DEPENDENCY + MALFORMED],
        ids=["approval", "dependency", "malformed", "two-kinds", "all-three"],
    )
    def test_mcp_matches_core(self, workspace, text):
        _write(workspace, text)
        assert _tasks(workspace) == [e.display_title for e in parse_entries(text)]

    def test_malformed_surfaces_not_silently_dropped(self, workspace):
        """spec-agent's ruling: a malformed entry is "never silently invisible
        in one transport". It shows as [malformed] rather than as a blank line
        or an absence."""
        _write(workspace, MALFORMED)
        assert _tasks(workspace) == ["[malformed]"]

    def test_tombstoned_entries_excluded(self, workspace):
        """A cleared entry is terminated — it must not resurface as a block."""
        _write(workspace, "<!-- " + APPROVAL.strip() + "\ncleared 2026-01-01 — approved -->\n")
        assert _tasks(workspace) == []


class TestConsumesCoreNotCli:
    def test_parser_comes_from_core(self):
        """plugin cannot import otaman_cli — cli declares otaman-plugin as a
        runtime dep, so the reverse is circular and absent from every tenant
        install."""
        mod = _blocked_entries()
        assert mod is not None
        assert mod.__name__.startswith("otaman_core."), mod.__name__

    def test_inline_regex_is_gone_from_the_check_surface(self):
        """The fifth parse site must not survive in otaman_check itself.

        Asserts on the REGEX, not the word "Proposal" — the field name
        legitimately appears in the explanatory comment, and an earlier
        version of this test failed on exactly that. The pattern may also
        still live in _legacy_blocked_entries (the laggard fallback), so this
        checks the function body rather than the file.
        """
        import inspect

        body = inspect.getsource(bus_server.otaman_check.fn)
        assert r"\*\*Proposal\*\*" not in body, "otaman_check still regex-parses the format"
        assert "re.finditer" not in body, "otaman_check still walks the file itself"
        assert "parse_entries" in body, "otaman_check must go through the shared parser"


class TestOtamanBlockedTool:
    """The SIXTH parse site, found by this file's own "no second parser" test.

    Milder than otaman_check's — it did not require Proposal, so dependency
    entries were listed — but still non-conformant: no kind, no ref, and its
    `## Blocked: (.+?)` required a non-empty title, so a malformed entry was
    invisible here while core surfaces it as [malformed].
    """

    def test_list_matches_core(self, workspace):
        _write(workspace, APPROVAL + DEPENDENCY + MALFORMED)
        got = otaman_blocked.fn(cwd=str(workspace["repo"]), action="list")
        assert [t["task"] for t in got["blocked_tasks"]] == [
            e.display_title for e in parse_entries(APPROVAL + DEPENDENCY + MALFORMED)
        ]

    def test_list_reports_kind_and_ref(self, workspace):
        _write(workspace, DEPENDENCY)
        got = otaman_blocked.fn(cwd=str(workspace["repo"]), action="list")
        assert got["blocked_tasks"][0]["kind"] == "awaiting-dependency"
        assert got["blocked_tasks"][0]["ref"] == "some-dependency"

    def test_malformed_entry_is_visible_here_too(self, workspace):
        """It was invisible before: the old regex required a non-empty title."""
        _write(workspace, MALFORMED)
        got = otaman_blocked.fn(cwd=str(workspace["repo"]), action="list")
        assert [t["task"] for t in got["blocked_tasks"]] == ["[malformed]"]

    def test_clear_tombstones_rather_than_deleting(self, workspace):
        """Canon: "clearing must never destroy the record of why". This used
        to re.sub the entry out of the file, which also diverged from cli.

        Held for one PR while core's tombstone() lost the entry separator
        (reported 20260921T151120, fixed in core #66); the guard below is
        what said it was safe to land.
        """
        _write(workspace, APPROVAL)
        otaman_blocked.fn(cwd=str(workspace["repo"]), action="clear", task_name="approval wait")
        text = (workspace["root"] / ".agents" / "blocked" / "plugin-agent.md").read_text()
        assert "approval wait" in text, "the record was destroyed, not tombstoned"
        assert "— manually-cleared -->" in text
        assert parse_entries(text) == [], "entry must no longer read as live"

    def test_clear_leaves_later_entries_live(self, workspace):
        """The exact shape of the core bug that held this back: tombstoning
        the FIRST entry must not hide the second."""
        _write(workspace, APPROVAL + DEPENDENCY)
        otaman_blocked.fn(cwd=str(workspace["repo"]), action="clear", task_name="approval wait")
        text = (workspace["root"] / ".agents" / "blocked" / "plugin-agent.md").read_text()
        assert [e.display_title for e in parse_entries(text)] == ["dependency wait"]

    def test_clear_refuses_an_unknown_title(self, workspace):
        """The old re.sub matched nothing and still reported success, so a
        typo looked like a successful clear."""
        _write(workspace, APPROVAL)
        got = otaman_blocked.fn(
            cwd=str(workspace["repo"]), action="clear", task_name="no such entry"
        )
        assert "error" in got
        assert got.get("cleared") is not True

    def test_clear_matches_cli_byte_for_byte(self, workspace):
        """Both transports write the same tombstone through the same helper,
        so an entry cleared either way must read identically."""
        from datetime import datetime, timezone

        from otaman_core.blocked_entries import tombstone

        _write(workspace, APPROVAL)
        path = workspace["root"] / ".agents" / "blocked" / "plugin-agent.md"
        before = path.read_text()
        otaman_blocked.fn(cwd=str(workspace["repo"]), action="clear", task_name="approval wait")
        via_mcp = path.read_text()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        via_core = tombstone(before, parse_entries(before), reason="manually-cleared", today=today)
        assert via_mcp == via_core


class TestLaggardBundleFallback:
    def test_degrades_when_core_lacks_the_module(self, monkeypatch):
        real_import = __import__

        def _fake(name, *a, **k):
            if name == "otaman_core":
                raise ImportError("simulated laggard bundle")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake)
        assert _blocked_entries() is None

    def test_refuses_rather_than_answering_incompletely(self, workspace, monkeypatch):
        """REFUSE, don't degrade — matching cli's blocked_gate.REMEDY.

        An earlier version of this fix fell back to the pre-fix regex,
        reasoning that some blocks beat none. That missed the third option:
        refuse and name the remedy. Degrading returns a silently-incomplete
        blocked list — the failure this change exists to remove — AND diverges
        the transports on the surface being made to agree, with cli refusing
        while MCP quietly answers wrong.
        """
        monkeypatch.setattr(bus_server, "_blocked_entries", lambda: None)
        _write(workspace, APPROVAL + DEPENDENCY)
        result = otaman_check.fn(cwd=str(workspace["repo"]))
        assert "error" in result
        assert "blocked_tasks" not in result, "must not hand back a partial list alongside an error"

    def test_refusal_names_the_remedy(self, workspace, monkeypatch):
        """A refusal the caller cannot act on is just a failure."""
        monkeypatch.setattr(bus_server, "_blocked_entries", lambda: None)
        _write(workspace, APPROVAL)
        err = otaman_check.fn(cwd=str(workspace["repo"]))["error"]
        assert "otaman-core" in err
        assert "otaman upgrade" in err

    def test_no_second_parser_survives_in_the_module(self):
        """With refusal there is no laggard path, so the pre-fix regex is dead
        code — and leaving it would restore the sixth parse site this change
        removed."""
        import inspect

        src = inspect.getsource(bus_server)
        assert "_legacy_blocked_entries" not in src
        assert src.count(r"\*\*Proposal\*\*") <= 1, (
            "more than one Proposal-field regex means the format is defined twice again"
        )
