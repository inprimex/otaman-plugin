"""agent-credential-access 1.4: "where each cascade layer's secrets file
lives" half of the requirement — the other half (external-resource ->
credential/Host map) is `_render_connection_inventory`, covered in
test_connection_inventory_block.py.

Tests against the REAL `otaman_core._secrets.credential_layer_paths` /
`credential_provenance` (agent-credential-access 1.1, otaman-core PR #42;
org auto-discovery via `resolve_org_root()` added in PR #43) rather than
mocking them, matching this repo's convention (test_policy_generation.py,
test_connection_inventory_block.py).

Values-free by contract (Q5): only layer names, file paths, and key
NAMES ever render — never a value.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen = importlib.import_module("otaman_plugin.generate_agent_config")


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


class _FakeWindowsPath:
    """Duck-typed stand-in for a real ``WindowsPath`` (can't be instantiated
    on a POSIX test runner — ``pathlib.WindowsPath(...)`` raises
    ``NotImplementedError`` there). ``str()`` uses backslashes, matching a
    real Windows path's native rendering; ``as_posix()`` uses forward
    slashes. Proves the renderer converts to posix before embedding a path
    into text that later reaches ``re.sub`` as a REPLACEMENT string —
    otherwise Windows path fragments like ``\\Users``/``\\AppData``/
    ``\\Local`` are interpreted as invalid regex escapes ("bad escape \\U"),
    exactly the live bug cli-agent reported (20260903T200442) after this
    section shipped without the conversion."""

    def __init__(self, posix_str: str):
        self._posix = posix_str

    def as_posix(self) -> str:
        return self._posix

    def is_file(self) -> bool:
        return False

    def __str__(self) -> str:  # pragma: no cover - tripwire, must never be used
        return self._posix.replace("/", "\\")


def test_windows_style_path_never_reaches_output_with_backslashes(monkeypatch):
    """Regression for the live Windows crash: a raw (non-posix) path
    reaching re.sub as a REPLACEMENT string crashes with 'bad escape \\U'
    on segments like Users/AppData/Local. This section must always call
    as_posix() before embedding a path, never rely on implicit str()."""
    win_path = _FakeWindowsPath("C:/Users/runneradmin/AppData/Local/.otaman/secrets.env")

    def _fake_layer_paths(*, maestro_root=None, org=None, home=None):
        return {"program": win_path}

    def _fake_provenance(*, maestro_root=None, org=None, home=None):
        return {}

    monkeypatch.setattr(
        "otaman_core._secrets.credential_layer_paths", _fake_layer_paths, raising=False
    )
    monkeypatch.setattr(
        "otaman_core._secrets.credential_provenance", _fake_provenance, raising=False
    )

    block = gen._render_credential_cascade_section(Path("/some/root"))

    assert "\\" not in block
    assert "C:/Users/runneradmin/AppData/Local/.otaman/secrets.env" in block

    # The exact failure mode: this text becomes a re.sub REPLACEMENT
    # string elsewhere in the generator (generate_repo_claude_md). Prove
    # it survives that call without raising re.error.
    import re

    re.sub(r"managed-block", block, "managed-block", flags=re.DOTALL)


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
