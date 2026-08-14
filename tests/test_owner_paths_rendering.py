"""Tests for monorepo-path-ownership tasks 3.1 + 3.2 — "Owned paths"
section rendering in the per-agent CLAUDE.md template.

Covers the four shapes the template needs to handle:

1. Full-repo owner (no ``owner-paths`` at all) — section omitted.
2. ``owner-paths`` declared but the current agent isn't in any glob —
   section omitted (they're the catch-all; rendering their owned paths as
   "everything not in the carve-outs" is out of scope for this MVP).
3. Agent appears in at least one ``owner-paths`` glob — section rendered
   with bullet list of their globs.
4. Both the YAML key (``owner-paths``) and the Python-normalized key
   (``owner_paths``) work — guards the transition window before
   otaman-core task 1.1 ships parser-side normalization.

These tests use the same `generate_repo_claude_md` entry point as the
existing `test_phase8.py::TestStandardsRendering` so behavior is verified
end-to-end through the public generator API.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen_config = importlib.import_module("otaman_plugin.generate_agent_config")


def _config(repo: dict) -> dict:
    """Build a minimal platform.yaml dict around a single repo entry."""
    return {
        "project": "monorepo-test",
        "repos": [repo],
        "communication": {"bus_path": ".agents/bus", "format": "markdown"},
    }


def _generate(tmp_path: Path, repo: dict) -> str:
    """Write the repo dir, generate, return the CLAUDE.md content."""
    repo_dir = tmp_path / repo["path"].lstrip("./")
    repo_dir.mkdir(parents=True, exist_ok=True)
    gen_config.generate_repo_claude_md(tmp_path, _config(repo))
    return (repo_dir / "CLAUDE.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Case 1 — full-repo owner: no owner-paths key
# ---------------------------------------------------------------------------


class TestFullRepoOwnerOmitsSection:
    def test_no_owner_paths_no_section(self, tmp_path):
        content = _generate(
            tmp_path,
            {"name": "web", "path": "./web", "owner": "frontend-agent"},
        )
        # The header should not appear at all
        assert "### Owned paths in" not in content
        # Sanity: the rest of the orchestration block is still rendered
        assert "You are `frontend-agent`" in content


# ---------------------------------------------------------------------------
# Case 2 — owner-paths declared but current agent not named
# ---------------------------------------------------------------------------


class TestCatchAllOwnerOmitsSection:
    def test_catch_all_not_in_globs_skips_section(self, tmp_path):
        # `root-agent` is the catch-all `owner:`. The owner-paths globs route
        # specific dirs to web-agent and api-agent — root-agent isn't named
        # in any of them, so they get no "Owned paths" section. Anything
        # outside the carve-outs implicitly belongs to root-agent via the
        # repo-level `owner:` field; rendering "everything except these"
        # is out of scope for the MVP.
        content = _generate(
            tmp_path,
            {
                "name": "mono",
                "path": "./mono",
                "owner": "root-agent",
                "owner-paths": {
                    "apps/web/**": "web-agent",
                    "apps/api/**": "api-agent",
                },
            },
        )
        assert "### Owned paths in" not in content


# ---------------------------------------------------------------------------
# Case 3 — agent named in owner-paths gets the section
# ---------------------------------------------------------------------------


class TestNamedOwnerGetsSection:
    def test_single_glob_renders(self, tmp_path):
        content = _generate(
            tmp_path,
            {
                "name": "mono",
                "path": "./mono",
                "owner": "web-agent",
                "owner-paths": {
                    "apps/web/**": "web-agent",
                },
            },
        )
        assert "### Owned paths in mono" in content
        assert "You own the following paths inside `mono`:" in content
        assert "- `apps/web/**`" in content
        assert "Changes outside these paths require coordination with the owning agent." in content

    def test_multiple_globs_render_as_bullet_list(self, tmp_path):
        content = _generate(
            tmp_path,
            {
                "name": "mono",
                "path": "./mono",
                "owner": "web-agent",
                "owner-paths": {
                    "apps/web/**": "web-agent",
                    "packages/ui/**": "web-agent",
                    "apps/api/**": "api-agent",  # not this agent — must not appear
                },
            },
        )
        assert "- `apps/web/**`" in content
        assert "- `packages/ui/**`" in content
        # api-agent's glob must not leak into web-agent's section
        assert "- `apps/api/**`" not in content


# ---------------------------------------------------------------------------
# Case 4 — both YAML key spellings work
# ---------------------------------------------------------------------------


class TestKeySpellings:
    """Guards the transition window: today the YAML round-trips as
    ``owner-paths`` (dashed); after otaman-core task 1.1 lands, the parser
    will normalize to ``owner_paths`` (snake). The template handles both.
    """

    def test_dashed_yaml_key_works(self, tmp_path):
        content = _generate(
            tmp_path,
            {
                "name": "mono",
                "path": "./mono",
                "owner": "web-agent",
                "owner-paths": {"apps/web/**": "web-agent"},
            },
        )
        assert "### Owned paths in mono" in content
        assert "- `apps/web/**`" in content

    def test_snake_python_key_works(self, tmp_path):
        content = _generate(
            tmp_path,
            {
                "name": "mono",
                "path": "./mono",
                "owner": "web-agent",
                "owner_paths": {"apps/web/**": "web-agent"},
            },
        )
        assert "### Owned paths in mono" in content
        assert "- `apps/web/**`" in content


# ---------------------------------------------------------------------------
# Edge cases — defensive shapes
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_owner_paths_dict_omits_section(self, tmp_path):
        content = _generate(
            tmp_path,
            {
                "name": "mono",
                "path": "./mono",
                "owner": "web-agent",
                "owner-paths": {},
            },
        )
        assert "### Owned paths in" not in content

    def test_owner_paths_none_omits_section(self, tmp_path):
        content = _generate(
            tmp_path,
            {
                "name": "mono",
                "path": "./mono",
                "owner": "web-agent",
                "owner-paths": None,
            },
        )
        assert "### Owned paths in" not in content

    def test_non_dict_owner_paths_omits_section(self, tmp_path):
        # Defensive: a list or string here is invalid per schema, but the
        # template should not blow up — it just skips the section.
        content = _generate(
            tmp_path,
            {
                "name": "mono",
                "path": "./mono",
                "owner": "web-agent",
                "owner-paths": ["apps/web/**", "packages/ui/**"],
            },
        )
        assert "### Owned paths in" not in content


# ---------------------------------------------------------------------------
# Multi-agent monorepo — each agent's CLAUDE.md sees only their globs
# ---------------------------------------------------------------------------


class TestMultiAgentMonorepo:
    def test_each_agent_sees_only_their_globs(self, tmp_path):
        # In a true monorepo with two agents sharing one repo, each agent
        # would have their own CLAUDE.md generated. Currently the generator
        # writes one CLAUDE.md per `repo` entry keyed on `owner:`. The
        # workaround tested here: declare each "logical agent" as its own
        # repo entry pointing at the same monorepo path but with a
        # different `owner:`. Each one's CLAUDE.md only sees its own globs.
        repo_dir = tmp_path / "mono"
        repo_dir.mkdir()
        config = {
            "project": "mono-test",
            "repos": [
                {
                    "name": "mono-web",
                    "path": "./mono",
                    "owner": "web-agent",
                    "owner-paths": {
                        "apps/web/**": "web-agent",
                        "apps/api/**": "api-agent",
                    },
                },
            ],
            "communication": {"bus_path": ".agents/bus", "format": "markdown"},
        }
        gen_config.generate_repo_claude_md(tmp_path, config)
        content = (repo_dir / "CLAUDE.md").read_text(encoding="utf-8")
        # web-agent sees apps/web/** but not apps/api/**
        assert "- `apps/web/**`" in content
        assert "- `apps/api/**`" not in content
