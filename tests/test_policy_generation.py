"""policy-engine 2.2: the generator's half of git-pack policy materialization.

- `_render_git_policy_section` renders this repo's EFFECTIVE git policy
  (resolved through otaman-core's `effective_policy` — the composition
  algebra is never re-implemented here) into the always-loaded
  CLAUDE.local.md block.
- `install_policy_files` materializes `policy/index.yaml` and shipped
  `policy/<pack>/standard.yaml` files that are ABSENT — never overwrites
  an existing (possibly CTO-edited) policy file.

Tests against the REAL `otaman_core.policy` / `otaman_core.human_roster`
modules (sibling checkout) rather than mocking them, matching this repo's
convention (test_connection_inventory_block.py, test_launch_acting_lock.py).

Verified finding worth pinning: `otaman_core.policy.effective_policy` falls
back to the shipped `standard` policy for a pack even when `policy/` has
never been materialized on disk (absent selection defaults to
`DEFAULT_POLICY_NAME`, and a missing-on-disk default falls back to the
shipped standard) — so `_render_git_policy_section` renders real content
from day one, before `install_policy_files` (this module's own Piece B)
ever runs. The two pieces are independent, not sequenced.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen = importlib.import_module("otaman_plugin.generate_agent_config")

AGENT_REPO = {"name": "agent-repo", "path": "./agent-repo", "owner": "some-agent"}
HUMAN_REPO = {"name": "human-repo", "path": "./human-repo", "owner": "romanhuman"}

ROSTER_CONFIG = {
    "human-roster": [
        {"name": "romanhuman", "email": "roman@example.com", "roles": ["founder"]},
    ],
}


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "meta"
    root.mkdir()
    return root


class TestRenderGitPolicySection:
    def test_none_project_root_returns_empty(self):
        assert gen._render_git_policy_section(AGENT_REPO, ROSTER_CONFIG, None) == ""

    def test_agent_owned_repo_gets_self_merge_and_prohibition_lines(self, tmp_path):
        root = _root(tmp_path)
        block = gen._render_git_policy_section(AGENT_REPO, ROSTER_CONFIG, root)
        assert "### Branch & merge policy (git pack)" in block
        # both facts hold simultaneously for an agent: never merge into a
        # human-owned branch, AND self-merge on its own (agent-owned) repo.
        assert "NEVER merge into a branch owned by a human" in block
        assert "This repo is agent-owned (you)" in block
        assert "you admit your own merge yourself" in block

    def test_human_owned_repo_has_no_self_merge_line(self, tmp_path):
        root = _root(tmp_path)
        block = gen._render_git_policy_section(HUMAN_REPO, ROSTER_CONFIG, root)
        assert "### Branch & merge policy (git pack)" in block
        # the general prohibition still applies...
        assert "NEVER merge into a branch owned by a human" in block
        # ...but the self-merge-on-own-repo line must NOT appear for a
        # human-owned repo (there is no "agent admits its own PR" case here).
        assert "agent-owned (you)" not in block

    def test_force_push_and_status_check_lines_render(self, tmp_path):
        root = _root(tmp_path)
        block = gen._render_git_policy_section(AGENT_REPO, ROSTER_CONFIG, root)
        assert "Force-push is forbidden" in block
        assert "required CI check must pass" in block
        assert "<type>/<owner>/<topic>" in block

    def test_resolves_even_before_policy_dir_is_materialized(self, tmp_path):
        """Verified behavior: otaman_core.policy.effective_policy falls back to
        the shipped standard even when policy/ has never been written —
        Piece A does not depend on Piece B (install_policy_files) having run."""
        root = _root(tmp_path)
        assert not (root / "policy").exists()
        block = gen._render_git_policy_section(AGENT_REPO, ROSTER_CONFIG, root)
        assert "### Branch & merge policy (git pack)" in block

    def test_degrades_to_empty_on_resolution_error(self, tmp_path, monkeypatch):
        """A genuine resolution failure (simulates an older core / any
        exception) must degrade to "" — generation is never blocked."""
        root = _root(tmp_path)

        def _boom(*a, **k):
            raise RuntimeError("simulated older-core failure")

        import otaman_core.policy as core_policy

        monkeypatch.setattr(core_policy, "effective_policy", _boom)
        assert gen._render_git_policy_section(AGENT_REPO, ROSTER_CONFIG, root) == ""

    def test_real_repo_override_narrows_and_reflects_in_render(self, tmp_path):
        """A repo-level policy override that selects a DIFFERENT, present
        policy file changes what's rendered — proving this reads the real
        effective policy, not a hardcoded template."""
        root = _root(tmp_path)
        (root / "policy" / "git").mkdir(parents=True)
        (root / "policy" / "git" / "no-self-merge.yaml").write_text(
            "pack: git\n"
            "name: no-self-merge\n"
            "rules:\n"
            "  owner_admission_required: true\n"
            "  agents_merge_human_owned_branch_forbidden: true\n"
            "  agent_self_merge_on_owned_repo: false\n",
            encoding="utf-8",
        )
        config = {
            **ROSTER_CONFIG,
            "repos": [{"name": "agent-repo", "policies": {"git": "no-self-merge"}}],
        }
        block = gen._render_git_policy_section(AGENT_REPO, config, root)
        assert "NEVER merge into a branch owned by a human" in block
        assert "agent-owned (you)" not in block  # narrowed away by the override


class TestInstallPolicyFiles:
    def test_creates_index_and_standard_when_absent(self, tmp_path):
        root = _root(tmp_path)
        results = gen.install_policy_files(root, {})
        assert "Created: policy/index.yaml" in results
        assert "Created: policy/git/standard.yaml" in results
        assert (root / "policy" / "index.yaml").is_file()
        assert (root / "policy" / "git" / "standard.yaml").is_file()

    def test_index_yaml_round_trips_through_load_policy_index(self, tmp_path):
        root = _root(tmp_path)
        gen.install_policy_files(root, {})

        from otaman_core.policy import load_policy_index, shipped_index

        loaded = load_policy_index(root)
        shipped = shipped_index()
        assert loaded.schema_version == shipped.schema_version
        assert set(loaded.packs) == set(shipped.packs)
        assert loaded.packs["git"].narrow_only == shipped.packs["git"].narrow_only

    def test_standard_yaml_round_trips_through_load_policy(self, tmp_path):
        root = _root(tmp_path)
        gen.install_policy_files(root, {})

        from otaman_core.policy import load_policy, shipped_standard

        loaded = load_policy(root, "git", "standard")
        shipped = shipped_standard("git")
        assert loaded is not None
        assert loaded.pack == shipped.pack
        assert loaded.name == shipped.name
        # branching/environments/merge_policy are absorbed from
        # standards.git.* (or stay None absent that) — everything else
        # must match the shipped rules exactly.
        for key, value in shipped.rules.items():
            if key in ("branching", "environments", "merge_policy"):
                continue
            assert loaded.rules[key] == value

    def test_second_run_is_a_no_op(self, tmp_path):
        root = _root(tmp_path)
        first = gen.install_policy_files(root, {})
        assert first  # non-empty first time
        second = gen.install_policy_files(root, {})
        assert second == []

    def test_never_overwrites_a_cto_edited_standard_file(self, tmp_path):
        root = _root(tmp_path)
        gen.install_policy_files(root, {})
        standard_path = root / "policy" / "git" / "standard.yaml"
        edited = "pack: git\nname: standard\nrules:\n  force_push_forbidden: false\n"
        standard_path.write_text(edited, encoding="utf-8")

        results = gen.install_policy_files(root, {})

        assert standard_path.read_text(encoding="utf-8") == edited
        assert results == []

    def test_never_overwrites_an_existing_index_yaml(self, tmp_path):
        root = _root(tmp_path)
        (root / "policy").mkdir()
        custom_index = "schema_version: 1\npacks:\n  git:\n    narrow_only: []\n"
        (root / "policy" / "index.yaml").write_text(custom_index, encoding="utf-8")

        results = gen.install_policy_files(root, {})

        assert (root / "policy" / "index.yaml").read_text(encoding="utf-8") == custom_index
        # index untouched, but the (now-registered-with-no-narrow-only) git
        # pack still gets its shipped standard.yaml materialized since it
        # was absent.
        assert "Created: policy/git/standard.yaml" in results

    def test_absorbs_standards_git_content_into_the_written_standard(self, tmp_path):
        root = _root(tmp_path)
        config = {
            "standards": {
                "git": {
                    "branching": "trunk-based",
                    "environments": {"prod": "main"},
                    "merge_policy": "squash",
                }
            }
        }
        gen.install_policy_files(root, config)

        from otaman_core.policy import load_policy

        loaded = load_policy(root, "git", "standard")
        assert loaded.rules["branching"] == "trunk-based"
        assert loaded.rules["environments"] == {"prod": "main"}
        assert loaded.rules["merge_policy"] == "squash"

    def test_degrades_to_empty_on_older_core_without_policy_module(self, tmp_path, monkeypatch):
        root = _root(tmp_path)

        real_import = __import__

        def _fake_import(name, *a, **k):
            if name == "otaman_core.policy":
                raise ImportError("simulated older core")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake_import)
        assert gen.install_policy_files(root, {}) == []


@pytest.mark.skipif(not (Path(__file__).parent.parent / "src").exists(), reason="repo layout check")
def test_policy_section_is_wired_into_the_template():
    """Guard against a silent drop: {policy_section} must be interpolated
    into the CLAUDE.local.md template, and computed via the real render fn —
    same drop-guard convention as the other generated-rule sections."""
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "otaman_plugin"
        / "generate_agent_config.py"
    ).read_text(encoding="utf-8")
    assert "{policy_section}" in source
    assert "_render_git_policy_section(repo, config, project_root)" in source
