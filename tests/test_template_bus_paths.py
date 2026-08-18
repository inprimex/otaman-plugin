"""Template regression fixes from the 2026-08-16 bus-path incident.

Fleet evidence (core-agent 20260816T214916, landing-agent 20260816T215216,
fswatch-agent 20260816T220226): the scaffold template — not the repos —
was the regression source. Re-syncs re-emitted bare/`../../` bus paths,
dropped the step-0 identity line, and the marker rewrite destroyed the
`agent:` field.

Pins:
1. No bare ``.agents/`` refs — every doc path is prefixed with the
   computed otaman path.
2. The bus-resolution rules block (trust the CLI; verify marker content)
   is part of the template.
3. The step-0 identity-set checklist line is part of the template.
4. ``install_maestro_markers`` preserves an existing ``agent:`` field.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen_config = importlib.import_module("otaman_plugin.generate_agent_config")


def _config(repo: dict) -> dict:
    return {
        "project": "template-test",
        "repos": [repo],
        "communication": {"bus_path": ".agents/bus", "format": "markdown"},
    }


def _generate(tmp_path: Path, repo: dict) -> str:
    repo_dir = tmp_path / repo["path"].lstrip("./")
    repo_dir.mkdir(parents=True, exist_ok=True)
    gen_config.generate_repo_claude_md(tmp_path, _config(repo))
    return (repo_dir / "CLAUDE.local.md").read_text(encoding="utf-8")


_REPO = {"name": "backend", "path": "./backend", "owner": "dev-agent"}


class TestBusPathPrefixing:
    def test_no_bare_agents_refs(self, tmp_path):
        """core-agent finding 1: the Communication section carried bare
        `.agents/queue` / `.agents/blocked` refs — a literal `ls` from the
        repo root finds nothing and the agent concludes the bus is gone."""
        content = _generate(tmp_path, _REPO)
        assert "Read `.agents/" not in content
        assert "Read `../.agents/queue/dev-agent.md` directly" in content
        assert "Read `../.agents/blocked/dev-agent.md` directly" in content

    def test_queue_and_checklist_paths_share_the_computed_prefix(self, tmp_path):
        content = _generate(tmp_path, _REPO)
        assert "Otaman folder: `../`" in content
        assert "Read `../.agents/queue/dev-agent.md` — see your active" in content
        assert "`../.agents/knowledge/`" in content


class TestBusResolutionRules:
    def test_trust_the_cli_rule_present(self, tmp_path):
        content = _generate(tmp_path, _REPO)
        assert "**Trust the CLI over doc paths**" in content
        assert 'Never conclude "the bus is gone" from a failed `ls`' in content

    def test_marker_content_rule_names_the_computed_path(self, tmp_path):
        content = _generate(tmp_path, _REPO)
        assert ".otaman` marker must contain `..`" in content


class TestIdentityChecklistLine:
    def test_step_zero_identity_set_present(self, tmp_path):
        """fswatch finding: re-sync dropped the step-0 identity-set line."""
        content = _generate(tmp_path, _REPO)
        expected = '0. **Set identity for hooks**: `echo "dev-agent" > ../.agents/current-agent`'
        assert expected in content


class TestMarkerFirstPathDerivation:
    """cli-agent 20260816T223250: prefer the repo's `.otaman` marker as the
    source of truth for the otaman-folder path — a relpath baked at
    generation time can't survive layout migrations; the marker is kept
    current by init."""

    def test_valid_marker_wins_over_relpath(self, tmp_path):
        # Real otaman root at a location the relpath computation would
        # never produce; the marker points there.
        real_root = tmp_path / "real-meta"
        (real_root / ".agents").mkdir(parents=True)
        (real_root / "platform.yaml").write_text("project: t\n")
        repo_dir = tmp_path / "backend"
        repo_dir.mkdir()
        (repo_dir / ".otaman").write_text("# marker\n../real-meta\nagent: dev-agent\n")
        content = _generate(tmp_path, _REPO)
        assert "Otaman folder: `../real-meta/`" in content
        assert "Read `../real-meta/.agents/queue/dev-agent.md` — see your active" in content

    def test_maestro_root_key_variant_works(self, tmp_path):
        real_root = tmp_path / "real-meta"
        (real_root / ".agents").mkdir(parents=True)
        repo_dir = tmp_path / "backend"
        repo_dir.mkdir()
        (repo_dir / ".otaman").write_text("maestro_root: ../real-meta\n")
        content = _generate(tmp_path, _REPO)
        assert "Otaman folder: `../real-meta/`" in content

    def test_stale_marker_falls_back_to_relpath(self, tmp_path):
        repo_dir = tmp_path / "backend"
        repo_dir.mkdir()
        (repo_dir / ".otaman").write_text("../does-not-exist\n")
        content = _generate(tmp_path, _REPO)
        assert "Otaman folder: `../`" in content  # relpath fallback

    def test_no_marker_uses_relpath(self, tmp_path):
        content = _generate(tmp_path, _REPO)
        assert "Otaman folder: `../`" in content


class TestMarkerAgentFieldPreserved:
    def test_rewrite_preserves_agent_line(self, tmp_path):
        """landing finding 4: marker rewrite dropped `agent: <name>`."""
        repo_dir = tmp_path / "backend"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".otaman").write_text(
            "# Path to otaman folder\n..\nagent: dev-agent\n", encoding="utf-8"
        )
        gen_config.install_maestro_markers(tmp_path, _config(_REPO))
        marker = (repo_dir / ".otaman").read_text(encoding="utf-8")
        assert "agent: dev-agent" in marker
        assert "\n..\n" in marker  # path still written

    def test_fresh_marker_has_no_spurious_agent_line(self, tmp_path):
        repo_dir = tmp_path / "backend"
        repo_dir.mkdir(parents=True)
        gen_config.install_maestro_markers(tmp_path, _config(_REPO))
        marker = (repo_dir / ".otaman").read_text(encoding="utf-8")
        assert "agent:" not in marker
