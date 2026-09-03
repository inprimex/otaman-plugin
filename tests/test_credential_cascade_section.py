"""agent-credential-access 1.4: "where each cascade layer's secrets file
lives" half of the requirement — the other half (external-resource ->
credential/Host map) is `_render_connection_inventory`, covered in
test_connection_inventory_block.py.

Tests against the REAL `otaman_core._secrets.credential_layer_paths` /
`credential_provenance` (agent-credential-access 1.1, otaman-core PR #42)
rather than mocking them, matching this repo's convention
(test_policy_generation.py, test_connection_inventory_block.py).

Values-free by contract (Q5): only layer names, file paths, and key
NAMES ever render — never a value.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen = importlib.import_module("otaman_plugin.generate_agent_config")


class TestInferOrgFromPath:
    def test_matches_orgs_programs_convention(self):
        path = Path("/home/otaman-dev/orgs/otaman-dev/programs/otaman-dev/otaman-meta")
        assert gen._infer_org_from_path(path) == "otaman-dev"

    def test_no_orgs_segment_returns_none(self):
        assert gen._infer_org_from_path(Path("/home/user/projects/myapp")) is None

    def test_orgs_as_final_segment_returns_none(self):
        assert gen._infer_org_from_path(Path("/home/user/orgs")) is None


class TestRenderCredentialCascadeSection:
    def test_none_project_root_returns_empty(self):
        assert gen._render_credential_cascade_section(None) == ""

    def test_renders_layer_paths_program_and_tenant(self, tmp_path, monkeypatch):
        # A non-fleet-standard path (no orgs/<org>/ segment) -> org layer
        # omitted, program + tenant still render.
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        root = tmp_path / "meta"
        root.mkdir()
        block = gen._render_credential_cascade_section(root)
        assert "### Credential cascade" in block
        assert "**program**:" in block
        assert "**tenant**:" in block
        assert "**org**:" not in block  # no orgs/<org>/ in this path
        assert str(root / ".otaman" / "secrets.env") in block

    def test_marks_existing_vs_absent_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        root = tmp_path / "meta"
        (root / ".otaman").mkdir(parents=True)
        (root / ".otaman" / "secrets.env").write_text("KEY=value\n", encoding="utf-8")
        block = gen._render_credential_cascade_section(root)
        program_line = [ln for ln in block.splitlines() if ln.startswith("- **program**")][0]
        assert "(exists)" in program_line
        tenant_line = [ln for ln in block.splitlines() if ln.startswith("- **tenant**")][0]
        assert "(absent)" in tenant_line

    def test_renders_org_layer_when_path_matches_fleet_convention(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        root = tmp_path / "orgs" / "acme" / "programs" / "prog1" / "otaman-meta"
        root.mkdir(parents=True)
        block = gen._render_credential_cascade_section(root)
        assert "**org**:" in block
        assert str(tmp_path / "orgs" / "acme" / "config" / "secrets.env") in block

    def test_renders_key_provenance_nearest_scope_wins(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        root = tmp_path / "meta"
        (root / ".otaman").mkdir(parents=True)
        (root / ".otaman" / "secrets.env").write_text("PROGRAM_KEY=x\n", encoding="utf-8")
        (tmp_path / "home" / ".otaman").mkdir(parents=True)
        (tmp_path / "home" / ".otaman" / "secrets.env").write_text(
            "PROGRAM_KEY=y\nTENANT_ONLY_KEY=z\n", encoding="utf-8"
        )
        block = gen._render_credential_cascade_section(root)
        assert "**program** wins: PROGRAM_KEY" in block
        assert "**tenant** wins: TENANT_ONLY_KEY" in block

    def test_never_renders_a_value(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        root = tmp_path / "meta"
        (root / ".otaman").mkdir(parents=True)
        (root / ".otaman" / "secrets.env").write_text(
            "GITHUB_TOKEN=ghp_SUPER_SECRET_VALUE\n", encoding="utf-8"
        )
        block = gen._render_credential_cascade_section(root)
        assert "GITHUB_TOKEN" in block  # key NAME is fine
        assert "ghp_SUPER_SECRET_VALUE" not in block  # value must never render

    def test_degrades_to_empty_on_older_core_without_secrets_module(self, tmp_path, monkeypatch):
        real_import = __import__

        def _fake_import(name, *a, **k):
            if name == "otaman_core._secrets":
                raise ImportError("simulated older core")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake_import)
        assert gen._render_credential_cascade_section(tmp_path) == ""


def test_credential_cascade_section_wired_into_the_template():
    """Drop-guard: {credential_cascade_section} must be interpolated into
    the CLAUDE.local.md template, computed via the real render fn — same
    convention as the other generated-rule sections."""
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "otaman_plugin"
        / "generate_agent_config.py"
    ).read_text(encoding="utf-8")
    assert "{credential_cascade_section}" in source
    assert "_render_credential_cascade_section(project_root)" in source
