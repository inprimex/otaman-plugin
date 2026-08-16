"""Tests for scripts/launch-resolve.py — bash launcher state resolver."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


def _load_module():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(
        "launch_resolve", scripts_dir / "launch-resolve.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lr = _load_module()


@pytest.fixture
def maestro_root(tmp_path):
    """Minimal maestro folder: .agents + platform.yaml + launch-settings.yaml."""
    root = tmp_path / "my-maestro"
    root.mkdir()
    (root / ".agents").mkdir()
    return root


def _write_platform(root, repos):
    (root / "platform.yaml").write_text(
        yaml.dump({"project": "test", "version": "1.0", "repos": repos}),
        encoding="utf-8",
    )


def _write_settings(root, settings):
    (root / "launch-settings.yaml").write_text(yaml.dump(settings), encoding="utf-8")


class TestResolve:
    def test_minimal_no_settings(self, maestro_root):
        _write_platform(maestro_root, [])
        state = lr.resolve(maestro_root, None, "bash")
        assert state["connection_name"] == ""
        assert state["account_name"] == ""
        assert state["config_dir_expanded"] == ""
        assert state["secrets"] == {}
        assert state["repos"] == []

    def test_active_connection_from_settings(self, maestro_root):
        _write_platform(maestro_root, [])
        _write_settings(
            maestro_root,
            {
                "active_connection": "local",
                "accounts": {"personal": {"config_dir": "~/.claude-personal"}},
                "connections": {"local": {"type": "local", "account": "personal"}},
            },
        )
        state = lr.resolve(maestro_root, None, "bash")
        assert state["connection_name"] == "local"
        assert state["account_name"] == "personal"
        assert state["connection_type"] == "local"
        assert "personal" in state["config_dir_expanded"]

    def test_explicit_connection_overrides_active(self, maestro_root):
        _write_platform(maestro_root, [])
        _write_settings(
            maestro_root,
            {
                "active_connection": "local",
                "accounts": {
                    "personal": {"config_dir": "~/.claude-personal"},
                    "clientco": {"config_dir": "~/.claude-clientco"},
                },
                "connections": {
                    "local": {"type": "local", "account": "personal"},
                    "lan": {"type": "ssh", "account": "clientco"},
                },
            },
        )
        state = lr.resolve(maestro_root, "lan", "bash")
        assert state["connection_name"] == "lan"
        assert state["account_name"] == "clientco"
        assert state["connection_type"] == "ssh"

    def test_extends_chain(self, maestro_root):
        _write_settings(
            maestro_root,
            {
                "accounts": {"personal": {"config_dir": "~/.claude-personal"}},
                "connections": {
                    "lan": {
                        "type": "ssh",
                        "account": "personal",
                        "ssh_default_host": "user@host",
                    },
                    "mesh": {"extends": "lan", "ssh_default_host": "user@mesh"},
                },
            },
        )
        state = lr.resolve(maestro_root, "mesh", "bash")
        assert state["connection_type"] == "ssh"
        assert state["account_name"] == "personal"

    def test_unknown_connection_warns(self, maestro_root):
        _write_settings(
            maestro_root,
            {
                "connections": {"local": {"type": "local"}},
            },
        )
        state = lr.resolve(maestro_root, "ghost", "bash")
        assert state["connection_name"] == ""
        assert any("ghost" in w for w in state["warnings"])

    def test_unknown_account_warns(self, maestro_root):
        _write_settings(
            maestro_root,
            {
                "accounts": {"personal": {"config_dir": "~/.claude-personal"}},
                "connections": {"local": {"type": "local", "account": "missing"}},
            },
        )
        state = lr.resolve(maestro_root, "local", "bash")
        assert state["account_name"] == "missing"
        assert state["config_dir_expanded"] == ""
        assert any("missing" in w for w in state["warnings"])

    def test_secrets_loaded(self, maestro_root):
        _write_platform(maestro_root, [])
        (maestro_root / ".maestro").mkdir(exist_ok=True)
        (maestro_root / ".maestro" / "secrets.env").write_text(
            'MY_VAR=hello\nQUOTED="with space"\n',
            encoding="utf-8",
        )
        state = lr.resolve(maestro_root, None, "bash")
        assert state["secrets"] == {"MY_VAR": "hello", "QUOTED": "with space"}

    def test_repos_from_platform(self, maestro_root):
        _write_platform(
            maestro_root,
            [
                {"name": "auth", "path": "../auth", "owner": "a"},
                {"name": "web", "path": "../web", "owner": "b"},
                {"name": "archived", "path": "../arch", "owner": "c", "disabled": True},
            ],
        )
        state = lr.resolve(maestro_root, None, "bash")
        assert state["repos"] == ["auth", "web"]

    def test_ssh_defers_path_expansion(self, maestro_root):
        _write_settings(
            maestro_root,
            {
                "accounts": {"personal": {"config_dir": "~/.claude-personal"}},
                "connections": {"lan": {"type": "ssh", "account": "personal"}},
            },
        )
        state = lr.resolve(maestro_root, "lan", "ssh")
        # SSH target: ~ stays unexpanded
        assert state["config_dir_expanded"] == "~/.claude-personal"


class TestEmitExports:
    def test_shell_safe_quoting(self, maestro_root):
        """Values with single quotes are emitted using bash-safe escaping."""
        _write_settings(
            maestro_root,
            {
                "accounts": {"personal": {"config_dir": "~/.claude-personal"}},
                "connections": {"local": {"type": "local", "account": "personal"}},
            },
        )
        (maestro_root / ".maestro").mkdir()
        (maestro_root / ".maestro" / "secrets.env").write_text(
            "TRICKY=it's tricky\n",
            encoding="utf-8",
        )
        state = lr.resolve(maestro_root, "local", "bash")
        out = lr.emit_exports(state)
        # POSIX idiom: 'it'\''s tricky' ends the first quoted chunk, inserts
        # an escaped literal apostrophe, then reopens quoting.
        assert "'it'\\''s tricky'" in out

    def test_always_exports_maestro_vars(self, maestro_root):
        state = lr.resolve(maestro_root, None, "bash")
        out = lr.emit_exports(state)
        assert "export MAESTRO_ACTIVE_CONNECTION=" in out
        assert "export MAESTRO_ACTIVE_ACCOUNT=" in out
        assert "export MAESTRO_CONNECTION_TYPE=" in out

    def test_repos_comment_emitted(self, maestro_root):
        _write_platform(maestro_root, [{"name": "a", "path": "../a", "owner": "x"}])
        state = lr.resolve(maestro_root, None, "bash")
        out = lr.emit_exports(state)
        assert "# repos: a" in out

    def test_no_config_dir_no_export(self, maestro_root):
        """When no account is resolved, CLAUDE_CONFIG_DIR isn't exported."""
        state = lr.resolve(maestro_root, None, "bash")
        out = lr.emit_exports(state)
        assert "CLAUDE_CONFIG_DIR" not in out


class TestModelEffortInjection:
    """ANTHROPIC_MODEL + CLAUDE_CODE_EFFORT_LEVEL injection via the
    platform.yaml models: chain."""

    def test_project_default_exported(self, maestro_root):
        (maestro_root / "platform.yaml").write_text(
            yaml.dump(
                {
                    "project": "test",
                    "version": "1.0",
                    "repos": [],
                    "models": {"default": "sonnet", "default_effort": "medium"},
                }
            ),
            encoding="utf-8",
        )
        state = lr.resolve(maestro_root, None, "bash")
        assert state["model"] == "sonnet"
        assert state["effort"] == "medium"
        out = lr.emit_exports(state)
        assert "export ANTHROPIC_MODEL='sonnet'" in out
        assert "export CLAUDE_CODE_EFFORT_LEVEL='medium'" in out

    def test_no_models_block_no_export(self, maestro_root):
        """No models: block → env vars stay unset; Claude Code's own default applies."""
        _write_platform(maestro_root, [])
        state = lr.resolve(maestro_root, None, "bash")
        out = lr.emit_exports(state)
        assert "ANTHROPIC_MODEL" not in out
        assert "CLAUDE_CODE_EFFORT_LEVEL" not in out

    def test_per_repo_via_helper(self, maestro_root):
        """resolve_for_repo walks the chain with (repo, agent) context."""
        (maestro_root / "platform.yaml").write_text(
            yaml.dump(
                {
                    "project": "test",
                    "version": "1.0",
                    "repos": [
                        {"name": "train", "path": "../train", "owner": "train-agent"},
                    ],
                    "models": {
                        "default": "sonnet",
                        "by_repo": {
                            "train": {"model": "opus", "effort": "high"},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        tier = lr.resolve_for_repo(maestro_root, repo="train")
        assert tier["model"] == "opus"
        assert tier["effort"] == "high"
        assert tier["model_source"] == "by_repo"
