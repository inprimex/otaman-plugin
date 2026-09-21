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
    _legacy_blocked_entries,
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


class TestLaggardBundleFallback:
    def test_degrades_when_core_lacks_the_module(self, monkeypatch):
        real_import = __import__

        def _fake(name, *a, **k):
            if name == "otaman_core":
                raise ImportError("simulated laggard bundle")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake)
        assert _blocked_entries() is None

    def test_fallback_reports_some_blocks_rather_than_none(self, workspace, monkeypatch):
        """On a laggard bundle the pre-fix behaviour is retained deliberately:
        losing the dependency-entry fix is recoverable, but reporting NO blocks
        would be strictly worse than the defect being fixed."""
        monkeypatch.setattr(bus_server, "_blocked_entries", lambda: None)
        _write(workspace, APPROVAL + DEPENDENCY)
        assert _tasks(workspace) == ["approval wait"]

    def test_legacy_helper_shape_matches_the_new_one(self):
        """Both paths feed the same downstream dict-merge, so the keys must
        line up or the fallback would KeyError where the fixed path works."""
        entries = _legacy_blocked_entries(APPROVAL)
        assert entries
        assert set(entries[0]) == {
            "task",
            "proposal",
            "change",
            "ref",
            "kind",
            "blocked_since",
        }
