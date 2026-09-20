"""generated-artifact-quality 1.2 — the MCP side of the SCR standard.

Both MCP doors that can put a spec-change-request on the bus now consume the
ONE shared template (`otaman_core.scr_template`) and apply its refusal:

* `otaman_propose` renders from the template and REFUSES a body with unfilled
  sections. It previously hand-rolled three old headings and emitted literal
  "TODO:" text — it manufactured exactly the TODO theater the standard exists
  to refuse.
* `otaman_send(msg_type="spec-change-request")` is the SECOND entrance: it
  writes an arbitrary body and sailed past the propose-path refusal entirely.
  cli had the identical hole; closing one door per transport is how the two
  diverged in the first place.

Why otaman-CORE and not otaman-cli: otaman-cli declares otaman-plugin as a
runtime dependency, so a plugin->cli import is circular, and a tenant install
(wheel + otaman-core) has no otaman_cli at all. This repo's pytest pythonpath
DOES include ../otaman-cli/src, so that mistake would pass the whole suite and
CI and fail only on real installs — hence `test_consumes_core_not_cli`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from otaman_plugin.servers import bus_server  # noqa: E402
from otaman_plugin.servers.bus_server import (  # noqa: E402
    _scr_template,
    otaman_propose,
    otaman_send,
)

FILLED = {
    "problem": "Releases understate what shipped.",
    "evidence": "Measured across six repos on 2026-09-20.",
    "impact": "Every consumer reads an incomplete changelog.",
    "direction": "Aggregate fragments across the bundle.",
    "scope": "n/a because this does not change the publish trigger.",
    "routing": "otaman-deploy",
    "workaround": "n/a because none exists today.",
}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / "my-otaman"
    root.mkdir()
    (root / "platform.yaml").write_text(
        yaml.dump({"project": "test", "version": "1.0"}), encoding="utf-8"
    )
    (root / ".agents").mkdir()

    repo = tmp_path / "repo-plugin"
    repo.mkdir()
    (repo / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: plugin-agent\n", encoding="utf-8"
    )
    return {"root": root, "repo": repo}


def _bus_files(root: Path) -> list[Path]:
    return sorted((root / ".agents" / "bus" / "active").glob("*.md"))


def _body_of(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestSharedTemplateSource:
    def test_consumes_core_not_cli(self):
        """The dependency direction is load-bearing: otaman-cli depends on
        otaman-plugin, so importing otaman_cli here would be circular AND
        absent from every real install."""
        mod = _scr_template()
        assert mod is not None
        assert mod.__name__.startswith("otaman_core."), mod.__name__

    def test_no_second_template_copy_remains(self):
        """1.2 says the second copy is DELETED. The old hand-rolled headings
        and their literal TODO placeholders must be gone from the source."""
        src = (
            Path(bus_server.__file__).read_text(encoding="utf-8")
            if hasattr(bus_server, "__file__")
            else ""
        )
        assert "### What needs to change" not in src
        assert "TODO: Describe the proposed spec change." not in src
        assert "TODO: Which repos will need implementation changes." not in src

    def test_degrades_when_core_lacks_the_module(self, monkeypatch):
        """Release-lag safety: plugin and its bundled core version
        independently. A laggard bundle must lose the GATE, not the ability to
        write to the bus."""
        real_import = __import__

        def _fake(name, *a, **k):
            if name == "otaman_core":
                raise ImportError("simulated laggard bundle")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake)
        assert _scr_template() is None

    def test_degrades_when_module_is_missing_an_attribute(self, monkeypatch):
        """Attribute probe, not just an import guard — a core that has the
        module but predates `is_hollow` must also degrade."""
        mod = _scr_template()
        monkeypatch.delattr(mod, "is_hollow", raising=True)
        assert _scr_template() is None


class TestProposeRefusal:
    def test_refuses_when_sections_are_unfilled(self, workspace):
        result = otaman_propose.fn(
            cwd=str(workspace["repo"]),
            title="half an idea",
            problem="Something is wrong.",
        )
        assert "error" in result
        assert "decision-grade" in result["error"]
        assert not _bus_files(workspace["root"]), "a refused SCR must not reach the bus"

    def test_refusal_names_the_offending_sections(self, workspace):
        """ "Your SCR is incomplete" sends the author back to the template;
        naming the sections tells them what to type."""
        result = otaman_propose.fn(
            cwd=str(workspace["repo"]),
            title="half an idea",
            problem="Something is wrong.",
        )
        joined = " ".join(result["errors"])
        assert "Evidence" in joined and "Impact" in joined
        assert "n/a because" in joined

    def test_accepts_a_filled_scr_and_writes_the_template_body(self, workspace):
        result = otaman_propose.fn(cwd=str(workspace["repo"]), title="a real request", **FILLED)
        assert result.get("proposed") is True
        files = _bus_files(workspace["root"])
        assert len(files) == 1
        body = _body_of(files[0])
        for heading in ("Problem as observed", "Evidence", "Impact", "Proposed direction"):
            assert f"### {heading}" in body

    def test_na_because_satisfies_a_section(self, workspace):
        """The escape hatch is what makes the refusal fair — it forbids
        silence, it never forces invention."""
        result = otaman_propose.fn(cwd=str(workspace["repo"]), title="hatch", **FILLED)
        assert result.get("proposed") is True

    def test_bare_na_is_still_refused(self, workspace):
        """A trap cli already paid for: bare `n/a` must FAIL, or the hatch
        becomes a way to skip every section."""
        sections = {**FILLED, "scope": "n/a", "workaround": "none"}
        result = otaman_propose.fn(cwd=str(workspace["repo"]), title="bare na", **sections)
        assert "error" in result

    def test_evidence_level_is_validated(self, workspace):
        result = otaman_propose.fn(
            cwd=str(workspace["repo"]),
            title="bad level",
            evidence_level="vibes",
            **FILLED,
        )
        assert "error" in result

    def test_legacy_args_map_onto_sections_instead_of_being_dropped(self, workspace):
        """Legacy callers' text must survive into the right section — dropping
        what they already typed would be worse than refusing them."""
        result = otaman_propose.fn(
            cwd=str(workspace["repo"]),
            title="legacy caller",
            what_needs_to_change="Add the endpoint.",
            why_needed="It is missing.",
            affected_repos="otaman-core",
            evidence="Observed once.",
            impact="Blocks a task.",
            scope="n/a because it is additive.",
            workaround="n/a because none exists.",
        )
        assert result.get("proposed") is True
        body = _body_of(_bus_files(workspace["root"])[0])
        assert "Add the endpoint." in body
        assert "It is missing." in body
        assert "otaman-core" in body

    def test_explicit_section_wins_over_its_legacy_alias(self, workspace):
        otaman_propose.fn(
            cwd=str(workspace["repo"]),
            title="both given",
            what_needs_to_change="LEGACY TEXT",
            **FILLED,
        )
        body = _body_of(_bus_files(workspace["root"])[0])
        assert "Aggregate fragments across the bundle." in body
        assert "LEGACY TEXT" not in body


class TestSendSecondEntrance:
    def test_refuses_a_hollow_scr(self, workspace):
        """The hole this closes: otaman_send wrote an arbitrary SCR body with
        no check at all, so a TODO-bodied SCR landed with no complaint."""
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="human",
            subject="sneaking past propose",
            body="TODO\nTODO\n???",
            msg_type="spec-change-request",
        )
        assert "error" in result
        assert "hollow" in result["error"]
        assert not _bus_files(workspace["root"])

    def test_refusal_points_at_the_sections_and_at_propose(self, workspace):
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="human",
            subject="sneaking past propose",
            body="TODO",
            msg_type="spec-change-request",
        )
        assert "Problem as observed" in result["sections"].values()
        assert "otaman_propose" in result["hint"]

    def test_legacy_shaped_body_with_real_content_passes(self, workspace):
        """Deliberately narrower than the propose-path check. Every SCR filed
        before this template used the old headings; refusing those at a shared
        bus door would break senders over a FORMAT change, not over
        hollowness."""
        legacy = (
            "## Subject: Spec change request: old format\n\n"
            "### What needs to change\nAdd pagination to /users.\n\n"
            "### Why this is needed\nThe list response is unbounded.\n"
        )
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="human",
            subject="old format",
            body=legacy,
            msg_type="spec-change-request",
        )
        assert result.get("sent") is True

    def test_other_message_types_are_untouched(self, workspace):
        """The gate is scoped to spec-change-request — a terse `info` is not a
        quality violation."""
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="spec-agent",
            subject="fyi",
            body="TODO",
            msg_type="info",
        )
        assert result.get("sent") is True
