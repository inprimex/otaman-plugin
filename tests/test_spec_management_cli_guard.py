"""openspec-cli-adoption 3.1: the spec-management SKILL must carry the
C3/C4 guards so mere OpenSpec-CLI presence can never re-route spec ops for
non-spec agents, and `openspec init/update` can never run in a fleet repo.

Pins the load-bearing guard text into skills/spec-management/SKILL.md so a
future template/skill edit that silently drops it fails loudly in CI — same
pattern as test_spec_authoring_guard_template.py and
test_task_sequencing_guidance.py.

Contract source: otaman-specs change openspec-cli-adoption,
specs/spec-tooling/spec.md (conflicts C3, C4).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "skills" / "spec-management" / "SKILL.md"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert SKILL.is_file(), f"spec-management SKILL.md missing at {SKILL}"


def test_c3_guard_scopes_delegation_to_spec_agent_in_specs_repo():
    """C3: archive/materialization/authoring delegates ONLY for spec-agent
    operating in the specs repo."""
    txt = _skill_text()
    # Both halves of the AND-guard must be named.
    assert "spec-agent" in txt
    assert "specs repo" in txt
    # The guard must key on identity explicitly.
    assert "OTAMAN_AGENT=spec-agent" in txt


def test_c3_guard_leaves_other_agents_unchanged_regardless_of_cli():
    """C3: any other agent keeps the propose->task-assignment flow even with
    the CLI installed — presence must not change behavior."""
    txt = _skill_text()
    assert "regardless of whether the CLI is installed" in txt
    assert "/otaman:propose" in txt
    # The "mere presence never delegates" invariant must be stated.
    assert "Mere presence of the CLI" in txt
    assert "NEVER changes an agent's spec workflow" in txt


def test_c3_nonstandard_archives_stay_house_procedure():
    """Even spec-agent does NOT delegate nonstandard archives (decision
    records, superseded banners, correction preambles)."""
    txt = _skill_text()
    assert "nonstandard archives" in txt.lower()
    assert "house procedure" in txt.lower()


def test_c4_forbids_openspec_init_update_in_fleet_repos():
    """C4: init/update SHALL NOT run in fleet repos; harvest from a scratch
    directory instead."""
    txt = _skill_text()
    assert "`openspec init`" in txt and "update" in txt
    assert "SHALL NOT run in any fleet repo" in txt
    # The collision rationale and the scratch-dir alternative must be named.
    assert "CLAUDE.local.md" in txt
    assert "scratch directory" in txt
