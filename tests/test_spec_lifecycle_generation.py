"""spec-lifecycle-enforcement 3.1: CI gate template for spec repos
(validate stage/approved_by on PR, research-stage exempt) + generated
CLAUDE.local.md rule text stating the lifecycle, the three gates, and
that self-waive is ALWAYS visible.

Tests against the REAL `otaman_core.spec_lifecycle` (spec-lifecycle-
enforcement 1.1-1.4, otaman-core PR #46) rather than mocking it, matching
this repo's convention (test_policy_generation.py,
test_credential_cascade_section.py).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen = importlib.import_module("otaman_plugin.generate_agent_config")


class TestRenderSpecLifecycleNote:
    def test_states_all_nine_stages_in_order(self):
        from otaman_core.spec_lifecycle import STAGES

        note = gen._render_spec_lifecycle_note({})
        assert "### Spec lifecycle" in note
        # every stage name appears, in the real STAGES order
        positions = [note.index(s) for s in STAGES]
        assert positions == sorted(positions)

    def test_states_the_three_gates(self):
        note = gen._render_spec_lifecycle_note({})
        assert "merge" in note and "dispatch" in note and "archive" in note
        assert "approved_by" in note
        assert "spec-approved" in note

    def test_default_enforcement_is_warn(self):
        # otaman-core's SpecPolicy default (tenant default, D2)
        note = gen._render_spec_lifecycle_note({})
        assert "**warn**" in note

    def test_program_block_overrides_enforcement(self):
        note = gen._render_spec_lifecycle_note({"spec_policy": {"enforcement": "block"}})
        assert "**block**" in note
        assert "refuses the operation outright" in note

    def test_self_waive_visibility_rule_always_stated(self):
        note = gen._render_spec_lifecycle_note({})
        assert "self-waive" in note
        assert "never implicit" in note

    def test_ratify_mentioned_as_human_only_exception(self):
        note = gen._render_spec_lifecycle_note({})
        assert "otaman ratify" in note
        assert "human-only" in note

    def test_authored_stage_stated_as_undispatchable(self):
        """interactive-human-console 2.3: one lifecycle paragraph, one
        source of truth — the un-dispatchable rule extends this note
        rather than living in a second block."""
        note = gen._render_spec_lifecycle_note({})
        assert "UN-DISPATCHABLE" in note
        assert "authored" in note
        assert "spec-approved" in note

    def test_degrades_to_empty_on_older_core_without_module(self, monkeypatch):
        real_import = __import__

        def _fake_import(name, *a, **k):
            if name == "otaman_core.spec_lifecycle":
                raise ImportError("simulated older core")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake_import)
        assert gen._render_spec_lifecycle_note({}) == ""


def test_spec_lifecycle_note_wired_into_both_specs_section_branches():
    """Drop-guard: {spec_lifecycle_note} must be interpolated into BOTH
    the openspec-format and fallback-format specs_section branches — a
    future edit to only one would silently drop it in the other."""
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "otaman_plugin"
        / "generate_agent_config.py"
    ).read_text(encoding="utf-8")
    assert source.count("{spec_lifecycle_note}") >= 2
    assert "spec_lifecycle_note = _render_spec_lifecycle_note(config)" in source


class TestInstallSpecLifecycleCiGate:
    def _config(self, tmp_path, *, spec_policy=None):
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        core_dir = tmp_path / "otaman-core"
        core_dir.mkdir()
        config = {
            "specs": {"path": "specs"},
            "repos": [
                {"name": "specs", "path": "specs"},
                {
                    "name": "otaman-core",
                    "path": "otaman-core",
                    "remote": "git@github.com:inprimex/otaman-core.git",
                },
            ],
        }
        if spec_policy is not None:
            config["spec_policy"] = spec_policy
        return tmp_path, config

    def test_creates_gate_in_specs_repo_only(self, tmp_path):
        root, config = self._config(tmp_path)
        results = gen.install_spec_lifecycle_ci_gate(root, config)
        assert results == ["Created: specs/.github/workflows/otaman-spec-lifecycle-gate.yml"]
        gate = root / "specs" / ".github" / "workflows" / "otaman-spec-lifecycle-gate.yml"
        assert gate.is_file()
        core_gate = (
            root / "otaman-core" / ".github" / "workflows" / "otaman-spec-lifecycle-gate.yml"
        )
        assert not core_gate.exists()

    def test_generated_workflow_is_valid_yaml_with_expected_shape(self, tmp_path):
        root, config = self._config(tmp_path)
        gen.install_spec_lifecycle_ci_gate(root, config)
        gate = root / "specs" / ".github" / "workflows" / "otaman-spec-lifecycle-gate.yml"
        doc = yaml.safe_load(gate.read_text(encoding="utf-8"))
        assert doc["jobs"]["spec-lifecycle-gate"]["runs-on"] == "ubuntu-latest"
        checkout_steps = [s for s in doc["jobs"]["spec-lifecycle-gate"]["steps"] if "uses" in s]
        assert any("otaman-core" in s.get("with", {}).get("repository", "") for s in checkout_steps)

    def test_bakes_resolved_enforcement_mode(self, tmp_path):
        root, config = self._config(tmp_path, spec_policy={"enforcement": "block"})
        gen.install_spec_lifecycle_ci_gate(root, config)
        gate = root / "specs" / ".github" / "workflows" / "otaman-spec-lifecycle-gate.yml"
        text = gate.read_text(encoding="utf-8")
        assert 'ENFORCEMENT_MODE: "block"' in text

    def test_defaults_to_warn_when_no_spec_policy_configured(self, tmp_path):
        root, config = self._config(tmp_path)
        gen.install_spec_lifecycle_ci_gate(root, config)
        gate = root / "specs" / ".github" / "workflows" / "otaman-spec-lifecycle-gate.yml"
        text = gate.read_text(encoding="utf-8")
        assert 'ENFORCEMENT_MODE: "warn"' in text

    def test_never_overwrites_an_existing_gate_file(self, tmp_path):
        root, config = self._config(tmp_path)
        gate_dir = root / "specs" / ".github" / "workflows"
        gate_dir.mkdir(parents=True)
        existing = gate_dir / "otaman-spec-lifecycle-gate.yml"
        existing.write_text("custom: true\n", encoding="utf-8")
        results = gen.install_spec_lifecycle_ci_gate(root, config)
        assert results == []
        assert existing.read_text(encoding="utf-8") == "custom: true\n"

    def test_no_op_when_specs_not_configured(self, tmp_path):
        root, config = self._config(tmp_path)
        del config["specs"]
        assert gen.install_spec_lifecycle_ci_gate(root, config) == []

    def test_no_op_when_otaman_core_not_registered(self, tmp_path):
        root, config = self._config(tmp_path)
        config["repos"] = [r for r in config["repos"] if r["name"] != "otaman-core"]
        assert gen.install_spec_lifecycle_ci_gate(root, config) == []

    def test_no_op_when_otaman_core_has_no_remote(self, tmp_path):
        root, config = self._config(tmp_path)
        for r in config["repos"]:
            if r["name"] == "otaman-core":
                del r["remote"]
        assert gen.install_spec_lifecycle_ci_gate(root, config) == []

    def test_degrades_to_empty_on_older_core_without_module(self, tmp_path, monkeypatch):
        root, config = self._config(tmp_path)

        real_import = __import__

        def _fake_import(name, *a, **k):
            if name == "otaman_core.spec_lifecycle":
                raise ImportError("simulated older core")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake_import)
        assert gen.install_spec_lifecycle_ci_gate(root, config) == []


def test_spec_lifecycle_gate_wired_into_main():
    """Drop-guard: install_spec_lifecycle_ci_gate must actually be called
    from main(), not just defined."""
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "otaman_plugin"
        / "generate_agent_config.py"
    ).read_text(encoding="utf-8")
    assert "install_spec_lifecycle_ci_gate(project_root, config)" in source
