"""Tests for install_secrets_infra — gitignore + .example stub generation.

These tests exercise the part of ``scripts/generate_agent_config.py`` that
sets up the maestro folder's secrets infrastructure during ``maestro init``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_install_secrets_infra():
    """install_secrets_infra is now a package symbol."""
    from otaman_plugin.generate_agent_config import install_secrets_infra
    return install_secrets_infra


install_secrets_infra = _load_install_secrets_infra()


@pytest.fixture
def maestro_folder(tmp_path):
    """Create a minimal maestro folder (has platform.yaml + .agents)."""
    root = tmp_path / "my-maestro"
    root.mkdir()
    (root / "platform.yaml").write_text("project: test\nversion: '1.0'\nrepos: []\n")
    (root / ".agents").mkdir()
    return root


class TestRuntimeDirAndExample:
    def test_creates_runtime_dir(self, maestro_folder):
        install_secrets_infra(maestro_folder, {})
        assert (maestro_folder / ".otaman").is_dir()

    def test_creates_example_stub(self, maestro_folder):
        install_secrets_infra(maestro_folder, {})
        stub = maestro_folder / ".otaman" / "secrets.env.example"
        assert stub.is_file()
        content = stub.read_text(encoding="utf-8")
        # Stub should document expected keys, not contain values.
        assert "OTAMAN_TG_BOT_PERSONAL=" in content
        assert "NEVER commit" in content

    def test_does_not_overwrite_existing_example(self, maestro_folder):
        """User may have customized .example with project-specific keys."""
        runtime = maestro_folder / ".otaman"
        runtime.mkdir()
        custom = "CUSTOM_KEY=\n"
        (runtime / "secrets.env.example").write_text(custom, encoding="utf-8")
        install_secrets_infra(maestro_folder, {})
        assert (runtime / "secrets.env.example").read_text(encoding="utf-8") == custom

    def test_idempotent(self, maestro_folder):
        """Running twice is safe and yields same state."""
        r1 = install_secrets_infra(maestro_folder, {})
        r2 = install_secrets_infra(maestro_folder, {})
        # First run creates things; second run finds them already present.
        assert r1  # non-empty
        assert r2 == []  # nothing to do


class TestGitignoreEntries:
    def test_creates_gitignore_when_absent(self, maestro_folder):
        install_secrets_infra(maestro_folder, {})
        gi = maestro_folder / ".gitignore"
        assert gi.is_file()
        content = gi.read_text(encoding="utf-8")
        assert ".otaman/secrets.env" in content
        assert ".otaman/bridge-*.endpoint" in content
        assert ".otaman/afk" in content

    def test_appends_to_existing_gitignore(self, maestro_folder):
        gi = maestro_folder / ".gitignore"
        gi.write_text("# Existing\n.agents/bus/\n", encoding="utf-8")
        install_secrets_infra(maestro_folder, {})
        content = gi.read_text(encoding="utf-8")
        # Keeps existing entries
        assert ".agents/bus/" in content
        # Adds new ones
        assert ".otaman/secrets.env" in content

    def test_does_not_duplicate_existing_entries(self, maestro_folder):
        gi = maestro_folder / ".gitignore"
        gi.write_text(
            "# Existing\n"
            ".otaman/secrets.env\n"
            ".otaman/bridge-*.endpoint\n"
            ".otaman/afk\n",
            encoding="utf-8",
        )
        install_secrets_infra(maestro_folder, {})
        content = gi.read_text(encoding="utf-8")
        # Count appearances — should be exactly 1 each
        assert content.count(".otaman/secrets.env") == 1
        assert content.count(".otaman/bridge-*.endpoint") == 1
        assert content.count(".otaman/afk") == 1

    def test_appends_only_missing_entries(self, maestro_folder):
        """If gitignore has some but not all entries, append only the missing ones."""
        gi = maestro_folder / ".gitignore"
        gi.write_text(".otaman/secrets.env\n", encoding="utf-8")
        install_secrets_infra(maestro_folder, {})
        content = gi.read_text(encoding="utf-8")
        assert content.count(".otaman/secrets.env") == 1
        assert ".otaman/bridge-*.endpoint" in content
        assert ".otaman/afk" in content

    def test_ensures_trailing_newline_before_append(self, maestro_folder):
        """If existing gitignore lacks trailing newline, append cleanly."""
        gi = maestro_folder / ".gitignore"
        gi.write_text(".agents/bus/", encoding="utf-8")  # no newline
        install_secrets_infra(maestro_folder, {})
        content = gi.read_text(encoding="utf-8")
        # Existing entry should still be intact (not glued to new entries)
        lines = content.splitlines()
        assert ".agents/bus/" in lines
        assert ".otaman/secrets.env" in lines


class TestSecretsEnvPermissions:
    @pytest.mark.skipif(
        sys.platform == "win32", reason="chmod 0600 only meaningful on POSIX"
    )
    def test_chmods_existing_secrets_env_to_0600(self, maestro_folder):
        import os
        import stat
        runtime = maestro_folder / ".otaman"
        runtime.mkdir()
        secrets = runtime / "secrets.env"
        secrets.write_text("FOO=bar\n", encoding="utf-8")
        os.chmod(secrets, 0o644)
        install_secrets_infra(maestro_folder, {})
        mode = stat.S_IMODE(secrets.stat().st_mode)
        assert mode == 0o600

    def test_does_not_create_secrets_env(self, maestro_folder):
        """install_secrets_infra must never create secrets.env itself."""
        install_secrets_infra(maestro_folder, {})
        assert not (maestro_folder / ".otaman" / "secrets.env").exists()
