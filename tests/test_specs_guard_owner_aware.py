"""specs-guard-owner-aware 1.1/1.2: the specs_section builder must not tell
the specs repo's own owner that their repo is READ-ONLY for them.

Found live 2026-09-10 (Roman's pmeets-specs transcript): generating
spec-agent's own CLAUDE.local.md produced both "this repo is YOURS" and
"this repo is READ-ONLY for you — spec-agent authors everything" — the
confused spec-agent then offered an informal sign-off shortcut around
/otaman:propose for a founding architectural decision, the exact HITL
bypass the guard exists to prevent.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen_config = importlib.import_module("otaman_plugin.generate_agent_config")

SPECS_REPO = {"name": "acme-specs", "path": "acme-specs", "owner": "spec-agent"}
CODE_REPO = {"name": "api", "path": "api", "owner": "backend-agent"}


def _config(*, specs_format="openspec"):
    return {
        "project": "acme",
        "repos": [SPECS_REPO, CODE_REPO],
        "specs": {"path": "acme-specs", "format": specs_format},
        "communication": {"bus_path": ".agents/bus", "format": "markdown"},
    }


def _generate_both(tmp_path: Path, *, specs_format="openspec") -> tuple[str, str]:
    (tmp_path / SPECS_REPO["path"]).mkdir(parents=True, exist_ok=True)
    (tmp_path / CODE_REPO["path"]).mkdir(parents=True, exist_ok=True)
    config = _config(specs_format=specs_format)
    gen_config.generate_repo_claude_md(tmp_path, config)
    specs_content = (tmp_path / SPECS_REPO["path"] / "CLAUDE.local.md").read_text(encoding="utf-8")
    code_content = (tmp_path / CODE_REPO["path"] / "CLAUDE.local.md").read_text(encoding="utf-8")
    return specs_content, code_content


_BUGGY_OPENSPEC_LINE = f"Specs repo: `{SPECS_REPO['path']}` (READ-ONLY)"
_BUGGY_FALLBACK_LINE = f"Specs location: `{SPECS_REPO['path']}` (READ-ONLY)"


class TestSpecsRepoOwnerGetsAuthorSideFraming:
    def test_no_read_only_claim_about_its_own_repo(self, tmp_path):
        specs_content, _ = _generate_both(tmp_path)
        assert _BUGGY_OPENSPEC_LINE not in specs_content
        assert "READ-ONLY for you" not in specs_content

    def test_no_propose_self_referral(self, tmp_path):
        specs_content, _ = _generate_both(tmp_path)
        assert "Your only spec action is `/otaman:propose`" not in specs_content
        assert "NOT your job" not in specs_content

    def test_states_it_is_the_owners_job(self, tmp_path):
        specs_content, _ = _generate_both(tmp_path)
        assert "THIS IS your job" in specs_content
        assert "YOURS, not READ-ONLY" in specs_content

    def test_no_self_contradiction_yours_and_read_only(self, tmp_path):
        """Never assert both writable-ownership and read-only status of the
        same repo (the exact bug: header says YOURS, guard says READ-ONLY
        about acme-specs specifically — other repos legitimately stay
        READ-ONLY in the same file, so this checks the specs-repo line, not
        the whole document)."""
        specs_content, _ = _generate_both(tmp_path)
        assert f"**You are `spec-agent`**. You own this repository: **{SPECS_REPO['name']}**" in (
            specs_content
        )
        assert _BUGGY_OPENSPEC_LINE not in specs_content
        assert _BUGGY_FALLBACK_LINE not in specs_content

    def test_fallback_format_also_owner_aware(self, tmp_path):
        specs_content, _ = _generate_both(tmp_path, specs_format="fallback")
        assert _BUGGY_FALLBACK_LINE not in specs_content
        assert "THIS IS your job" in specs_content


class TestOtherRepoUnchanged:
    def test_code_repo_keeps_requester_side_guard(self, tmp_path):
        _, code_content = _generate_both(tmp_path)
        assert "(READ-ONLY)" in code_content
        assert "NOT your job" in code_content
        assert "Your only spec action is `/otaman:propose`" in code_content

    def test_code_repo_keeps_spec_change_rules(self, tmp_path):
        _, code_content = _generate_both(tmp_path)
        assert "### Spec Change Rules (CRITICAL)" in code_content
        assert "Resume the blocked task only after you see BOTH" in code_content
