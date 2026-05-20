"""Tests for scripts/_secrets.py — tiered secret source resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from _secrets import (  # noqa: E402
    DotenvSource,
    EnvSource,
    KeyringSource,
    SecretRef,
    load_dotenv,
    register_source,
    resolve,
    resolve_or_fail,
)


@pytest.fixture
def maestro_root(tmp_path):
    """Create a maestro root with empty .maestro/ subdir."""
    root = tmp_path / "my-maestro"
    root.mkdir()
    (root / ".maestro").mkdir()
    return root


def _write_dotenv(root: Path, contents: str) -> None:
    (root / ".maestro" / "secrets.env").write_text(contents, encoding="utf-8")


class TestSecretRefFromConfig:
    def test_short_form_string(self):
        ref = SecretRef.from_config("MY_TOKEN")
        assert ref.sources == [{"type": "env", "name": "MY_TOKEN"}]

    def test_long_form_with_sources(self):
        cfg = {
            "sources": [
                {"type": "env", "name": "A"},
                {"type": "dotenv", "name": "B"},
            ]
        }
        ref = SecretRef.from_config(cfg)
        assert len(ref.sources) == 2
        assert ref.sources[0]["type"] == "env"
        assert ref.sources[1]["type"] == "dotenv"

    def test_single_source_dict(self):
        """Dict without 'sources' key treated as a single source."""
        ref = SecretRef.from_config({"type": "env", "name": "X"})
        assert ref.sources == [{"type": "env", "name": "X"}]

    def test_none_raises(self):
        with pytest.raises(ValueError):
            SecretRef.from_config(None)

    def test_bad_type_raises(self):
        with pytest.raises(ValueError):
            SecretRef.from_config(42)

    def test_sources_must_be_list(self):
        with pytest.raises(ValueError):
            SecretRef.from_config({"sources": "not a list"})


class TestEnvSource:
    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("FOO_TOKEN", "secret-value")
        ref = SecretRef.from_config("FOO_TOKEN")
        assert resolve(ref) == "secret-value"

    def test_missing_env_returns_none(self, monkeypatch):
        monkeypatch.delenv("FOO_TOKEN", raising=False)
        ref = SecretRef.from_config("FOO_TOKEN")
        assert resolve(ref) is None

    def test_empty_env_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv("FOO_TOKEN", "")
        ref = SecretRef.from_config("FOO_TOKEN")
        assert resolve(ref) is None

    def test_name_required(self):
        src = EnvSource()
        assert src.resolve({}, {}) is None


class TestDotenvSource:
    def test_reads_dotenv(self, maestro_root):
        _write_dotenv(maestro_root, "MY_KEY=dotenv-value\n")
        ref = SecretRef(sources=[{"type": "dotenv", "name": "MY_KEY"}])
        assert resolve(ref, maestro_root=maestro_root) == "dotenv-value"

    def test_comment_and_blank_lines_ignored(self, maestro_root):
        _write_dotenv(
            maestro_root,
            "# comment line\n\n   # indented comment\nMY_KEY=x\n",
        )
        ref = SecretRef(sources=[{"type": "dotenv", "name": "MY_KEY"}])
        assert resolve(ref, maestro_root=maestro_root) == "x"

    def test_double_quoted_value(self, maestro_root):
        _write_dotenv(maestro_root, 'MY_KEY="quoted value with spaces"\n')
        ref = SecretRef(sources=[{"type": "dotenv", "name": "MY_KEY"}])
        assert resolve(ref, maestro_root=maestro_root) == "quoted value with spaces"

    def test_single_quoted_value(self, maestro_root):
        _write_dotenv(maestro_root, "MY_KEY='single quoted'\n")
        ref = SecretRef(sources=[{"type": "dotenv", "name": "MY_KEY"}])
        assert resolve(ref, maestro_root=maestro_root) == "single quoted"

    def test_missing_key_returns_none(self, maestro_root):
        _write_dotenv(maestro_root, "OTHER=value\n")
        ref = SecretRef(sources=[{"type": "dotenv", "name": "MISSING"}])
        assert resolve(ref, maestro_root=maestro_root) is None

    def test_missing_file_returns_none(self, maestro_root):
        ref = SecretRef(sources=[{"type": "dotenv", "name": "X"}])
        assert resolve(ref, maestro_root=maestro_root) is None

    def test_no_maestro_root_returns_none(self):
        """DotenvSource needs a maestro_root in context."""
        src = DotenvSource()
        assert src.resolve({"name": "X"}, {}) is None

    def test_empty_value_treated_as_missing(self, maestro_root):
        _write_dotenv(maestro_root, "MY_KEY=\n")
        ref = SecretRef(sources=[{"type": "dotenv", "name": "MY_KEY"}])
        assert resolve(ref, maestro_root=maestro_root) is None


class TestSourceChain:
    def test_env_beats_dotenv(self, maestro_root, monkeypatch):
        """First non-empty value wins, in listed order."""
        monkeypatch.setenv("MY_KEY", "from-env")
        _write_dotenv(maestro_root, "MY_KEY=from-dotenv\n")
        ref = SecretRef(sources=[
            {"type": "env", "name": "MY_KEY"},
            {"type": "dotenv", "name": "MY_KEY"},
        ])
        assert resolve(ref, maestro_root=maestro_root) == "from-env"

    def test_fallback_to_dotenv_when_env_missing(self, maestro_root, monkeypatch):
        monkeypatch.delenv("MY_KEY", raising=False)
        _write_dotenv(maestro_root, "MY_KEY=from-dotenv\n")
        ref = SecretRef(sources=[
            {"type": "env", "name": "MY_KEY"},
            {"type": "dotenv", "name": "MY_KEY"},
        ])
        assert resolve(ref, maestro_root=maestro_root) == "from-dotenv"

    def test_unknown_source_type_skipped(self, maestro_root, monkeypatch):
        """Unknown types don't crash; chain continues."""
        monkeypatch.setenv("MY_KEY", "ok")
        ref = SecretRef(sources=[
            {"type": "vault", "path": "x"},   # unknown in v1
            {"type": "env", "name": "MY_KEY"},
        ])
        assert resolve(ref, maestro_root=maestro_root) == "ok"

    def test_all_sources_fail_returns_none(self, maestro_root, monkeypatch):
        monkeypatch.delenv("MY_KEY", raising=False)
        ref = SecretRef(sources=[
            {"type": "env", "name": "MY_KEY"},
            {"type": "dotenv", "name": "MY_KEY"},
        ])
        assert resolve(ref, maestro_root=maestro_root) is None


class TestResolveOrFail:
    def test_returns_value_when_found(self, monkeypatch):
        monkeypatch.setenv("X", "v")
        assert resolve_or_fail(SecretRef.from_config("X")) == "v"

    def test_raises_with_source_description(self, maestro_root, monkeypatch):
        monkeypatch.delenv("MISSING", raising=False)
        ref = SecretRef(sources=[
            {"type": "env", "name": "MISSING"},
            {"type": "dotenv", "name": "MISSING"},
            {"type": "keyring", "service": "maestro", "account": "x"},
        ])
        with pytest.raises(RuntimeError) as exc:
            resolve_or_fail(ref, maestro_root=maestro_root)
        msg = str(exc.value)
        assert "env:MISSING" in msg
        assert "dotenv:MISSING" in msg
        assert "keyring:maestro/x" in msg


class TestLoadDotenv:
    def test_returns_all_pairs(self, maestro_root):
        _write_dotenv(
            maestro_root,
            "# header\nA=1\nB=two\nC=\"with spaces\"\n",
        )
        result = load_dotenv(maestro_root)
        assert result == {"A": "1", "B": "two", "C": "with spaces"}

    def test_missing_file_returns_empty_dict(self, maestro_root):
        assert load_dotenv(maestro_root) == {}


class TestRegisterSource:
    def test_custom_source_plugs_in(self, monkeypatch):
        class StaticSource:
            type_name = "static-test"

            def resolve(self, spec, context):
                return spec.get("value")

        register_source(StaticSource())
        try:
            ref = SecretRef(sources=[{"type": "static-test", "value": "hello"}])
            assert resolve(ref) == "hello"
        finally:
            # Clean up registered source to avoid test pollution.
            from _secrets import _BUILTIN_SOURCES
            _BUILTIN_SOURCES.pop("static-test", None)


class TestKeyringSource:
    def test_missing_keyring_package_returns_none(self, monkeypatch):
        """If keyring isn't importable, source silently yields None."""
        # Force ImportError by hiding the module.
        import importlib
        monkeypatch.setitem(sys.modules, "keyring", None)
        src = KeyringSource()
        assert src.resolve({"account": "x"}, {}) is None
        # Restore so other tests that may use keyring aren't broken.
        monkeypatch.delitem(sys.modules, "keyring", raising=False)
        importlib.invalidate_caches()

    def test_account_required(self):
        src = KeyringSource()
        assert src.resolve({"service": "maestro"}, {}) is None
