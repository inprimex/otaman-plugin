"""ce-bootstrap-plugin-wiring 1.3: generated CLAUDE.local.md slash-command
claims must be TRUE — a Path-B runner-spawned session only gets `/otaman:*`
slash commands when `runner.agent_bootstrap.plugin_dir` is wired to a real,
existing otaman-plugin checkout (deploy root-cause 20260903T151951:
bootstrap vendored the plugin tree but historically left `plugin_dir`
unset, so every such session had MCP tools but silently no slash
commands, while templates claimed otherwise).

`_plugin_dir_wiring_note` states this precondition truthfully per
generation pass (D3: "state the precondition, or generate conditionally"
— this picks the former). Wired into both specs_section branches (with
and without `specs_dir` mapping) so the claim is never made
unconditionally.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen = importlib.import_module("otaman_plugin.generate_agent_config")


class TestPluginDirWiringNote:
    def test_no_runner_config_reports_not_wired(self):
        note = gen._plugin_dir_wiring_note({})
        assert "may NOT be available" in note
        assert "otaman propose" in note

    def test_plugin_dir_unset_reports_not_wired(self):
        note = gen._plugin_dir_wiring_note({"runner": {"agent_bootstrap": {}}})
        assert "may NOT be available" in note

    def test_plugin_dir_set_but_missing_on_disk_reports_not_wired(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        note = gen._plugin_dir_wiring_note(
            {"runner": {"agent_bootstrap": {"plugin_dir": str(missing)}}}
        )
        assert "may NOT be available" in note

    def test_plugin_dir_set_and_existing_reports_available(self, tmp_path):
        vendored = tmp_path / "otaman-plugin-tree"
        vendored.mkdir()
        note = gen._plugin_dir_wiring_note(
            {"runner": {"agent_bootstrap": {"plugin_dir": str(vendored)}}}
        )
        assert "are available" in note
        assert str(vendored) in note

    def test_expands_user_home_in_plugin_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "vendored").mkdir()
        note = gen._plugin_dir_wiring_note(
            {"runner": {"agent_bootstrap": {"plugin_dir": "~/vendored"}}}
        )
        assert "are available" in note

    def test_non_dict_runner_config_degrades_to_not_wired(self):
        # A malformed platform.yaml (runner: as a string, etc.) must not crash
        # generation — degrade to the safe (not-wired) claim.
        note = gen._plugin_dir_wiring_note({"runner": "not-a-dict"})
        assert "may NOT be available" in note


def test_wiring_note_referenced_in_both_specs_section_branches():
    """Drop-guard: {plugin_dir_note} must be interpolated into BOTH the
    openspec-format branch and the fallback-format branch of specs_section
    — a future edit to only one branch would silently reintroduce an
    unconditional claim in the other."""
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "otaman_plugin"
        / "generate_agent_config.py"
    ).read_text(encoding="utf-8")
    assert source.count("{plugin_dir_note}") >= 2
    assert "plugin_dir_note = _plugin_dir_wiring_note(config)" in source
