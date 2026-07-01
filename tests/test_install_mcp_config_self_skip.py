"""Regression test for install_mcp_config's plugin-repo self-skip.

`install_mcp_config` must never overwrite otaman-plugin's own canonical
.mcp.json (it ships ${CLAUDE_PLUGIN_ROOT} paths, loaded natively by Claude
Code as a plugin). The original self-skip check compared
``Path(__file__).resolve().parent.parent.parent`` against each repo's
directory — that breaks whenever the executing otaman_plugin install (e.g.
a pipx venv) lives at a different path than the dev git checkout being
configured, which silently let the plugin's own .mcp.json get clobbered.
The fix identifies the plugin repo via its on-disk
.claude-plugin/plugin.json marker instead, independent of where the running
code was imported from.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen_config = importlib.import_module("otaman_plugin.generate_agent_config")


def _make_plugin_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    plugin_dir = repo_dir / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(json.dumps({"name": "otaman"}), encoding="utf-8")
    # Canonical .mcp.json this repo ships and must not lose.
    (repo_dir / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"otaman-bus": {"command": "bash"}}}), encoding="utf-8"
    )


class TestIsPluginRepo:
    def test_detects_plugin_repo_by_marker(self, tmp_path):
        repo_dir = tmp_path / "otaman-plugin"
        _make_plugin_repo(repo_dir)
        assert gen_config._is_plugin_repo(repo_dir) is True

    def test_detection_independent_of_checkout_location(self, tmp_path):
        # The bug this guards: the old check compared __file__-derived paths,
        # which fails when the dev checkout lives somewhere other than
        # wherever the currently-executing otaman_plugin package was
        # imported from (e.g. a pipx venv). The marker-based check must
        # succeed regardless of where the repo directory sits on disk.
        repo_dir = tmp_path / "some" / "unusual" / "nested" / "path" / "otaman-plugin-checkout"
        _make_plugin_repo(repo_dir)
        assert gen_config._is_plugin_repo(repo_dir) is True

    def test_rejects_repo_without_marker(self, tmp_path):
        repo_dir = tmp_path / "otaman-cli"
        repo_dir.mkdir()
        assert gen_config._is_plugin_repo(repo_dir) is False

    def test_rejects_plugin_json_with_different_name(self, tmp_path):
        repo_dir = tmp_path / "some-other-plugin"
        repo_dir.mkdir()
        plugin_dir = repo_dir / ".claude-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "not-otaman"}), encoding="utf-8"
        )
        assert gen_config._is_plugin_repo(repo_dir) is False

    def test_rejects_malformed_plugin_json(self, tmp_path):
        repo_dir = tmp_path / "otaman-plugin"
        plugin_dir = repo_dir / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text("{not valid json", encoding="utf-8")
        assert gen_config._is_plugin_repo(repo_dir) is False


class TestInstallMcpConfigSkipsPluginRepo:
    def test_plugin_repo_mcp_json_untouched(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

        project_root = tmp_path
        plugin_repo_dir = project_root / "otaman-plugin"
        _make_plugin_repo(plugin_repo_dir)
        original_mcp_json = (plugin_repo_dir / ".mcp.json").read_text(encoding="utf-8")

        other_repo_dir = project_root / "otaman-cli"
        other_repo_dir.mkdir()

        config = {
            "repos": [
                {"name": "otaman-plugin", "path": "otaman-plugin", "owner": "plugin-agent"},
                {"name": "otaman-cli", "path": "otaman-cli", "owner": "cli-agent"},
            ]
        }

        results = gen_config.install_mcp_config(project_root, config)

        # Plugin repo's canonical .mcp.json must survive byte-for-byte.
        assert (plugin_repo_dir / ".mcp.json").read_text(encoding="utf-8") == original_mcp_json
        assert any("otaman-plugin" in r and "skipped" in r for r in results)

        # The other repo does get a generated .mcp.json.
        assert (other_repo_dir / ".mcp.json").exists()
