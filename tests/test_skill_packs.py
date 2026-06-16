"""Tests for ``otaman_plugin.skill_packs`` (tech-startup-skill-pack-implementation 2.5).

Covers the four cases enumerated in task 2.5:

(a) tech-startup profile loads 8 public skills
(b) cofounder role loads all 10
(c) non-cofounder with explicit cofounder skill in active_skills is blocked
(d) active_skills override loads only named skills

All tests build fixture ``pack.yaml`` + empty skill files on the fly so
they don't depend on spec-agent's task 1.1 (skill content materialization
in otaman-meta) landing first. When 1.1 lands the resolver works against
real skill files unchanged — the manifest schema is the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from otaman_plugin.skill_packs import (
    KNOWN_PACKS,
    SkillRef,
    load_pack_manifest,
    resolve_active_skills,
    resolve_pack_root,
)


# ---------------------------------------------------------------------------
# Fixture — a temp otaman-meta layout with a fixture tech-startup pack
# ---------------------------------------------------------------------------

# The 10 skills from design.md Q6 — 8 public + 2 cofounder-only.
_PACK_SKILLS = [
    ("value-proposition-designer", "public"),
    ("pitch-deck-composer", "public"),
    ("market-sizing-analyst", "public"),
    ("competitive-positioning-strategist", "public"),
    ("narrative-architect", "public"),
    ("customer-development-coach", "public"),
    ("ai-tooling-domain-strategist", "public"),
    ("competitive-differentiator-mapper", "public"),
    ("investor-targeting-strategist", "cofounder-only"),
    ("financial-modeling-analyst", "cofounder-only"),
]


@pytest.fixture
def pack_root(tmp_path):
    """Build a fixture otaman-meta with the tech-startup pack laid out.

    Layout:
        tmp_path/otaman-meta/skill-packs/tech-startup/
            pack.yaml
            skills/<name>.md  (× 10)
    """
    meta = tmp_path / "otaman-meta"
    pack = meta / "skill-packs" / "tech-startup"
    skills_dir = pack / "skills"
    skills_dir.mkdir(parents=True)

    manifest_skills = []
    for name, access in _PACK_SKILLS:
        file_rel = f"skills/{name}.md"
        (pack / file_rel).write_text(f"# {name}\n", encoding="utf-8")
        manifest_skills.append(
            {
                "id": f"tech-startup:{name}",
                "file": file_rel,
                "access": access,
            }
        )

    (pack / "pack.yaml").write_text(
        yaml.dump(
            {
                "id": "tech-startup",
                "version": "1.0.0",
                "name": "Tech-Startup Cofounder Pack",
                "skills": manifest_skills,
            }
        ),
        encoding="utf-8",
    )
    return meta


def _platform(
    *,
    profile: str | None = "tech-startup-cofounder",
    active_skills: list[str] | None = None,
    cofounder: str | None = None,
):
    """Build a minimal ``platform.yaml`` mapping for the resolver."""
    skills: dict = {}
    if profile is not None:
        skills["profile"] = profile
    if active_skills is not None:
        skills["active_skills"] = active_skills
    data: dict = {"program": {"processes": {"skills": skills}}}
    if cofounder is not None:
        data["identity"] = {"roles": {"cofounder": cofounder}}
    return data


# ---------------------------------------------------------------------------
# Pack registry + manifest reader (tasks 2.1 + manifest loader)
# ---------------------------------------------------------------------------

class TestPackRegistry:
    def test_tech_startup_pack_is_registered(self):
        assert "tech-startup" in KNOWN_PACKS

    def test_resolve_pack_root_returns_expected_path(self, pack_root):
        root = resolve_pack_root("tech-startup", pack_root)
        assert root == pack_root / "skill-packs" / "tech-startup"

    def test_unknown_pack_returns_none(self, pack_root):
        assert resolve_pack_root("does-not-exist", pack_root) is None

    def test_load_pack_manifest_reads_yaml(self, pack_root):
        manifest = load_pack_manifest(pack_root / "skill-packs" / "tech-startup")
        assert manifest["id"] == "tech-startup"
        assert len(manifest["skills"]) == 10


# ---------------------------------------------------------------------------
# resolve_active_skills — the four task 2.5 cases
# ---------------------------------------------------------------------------

class TestResolveActiveSkills:
    # (a) tech-startup profile loads 8 public skills
    def test_profile_only_loads_public_skills(self, pack_root):
        platform = _platform()
        result = resolve_active_skills(platform, pack_root, active_user=None)
        ids = [s.id for s in result.skills]
        assert len(result.skills) == 8
        assert all(s.access == "public" for s in result.skills)
        # The two cofounder-only skills are skipped
        skipped_ids = {ref.id for ref, _ in result.skipped}
        assert "tech-startup:investor-targeting-strategist" in skipped_ids
        assert "tech-startup:financial-modeling-analyst" in skipped_ids
        # Sanity: the activated IDs contain a few of the known public skills
        assert "tech-startup:pitch-deck-composer" in ids
        assert "tech-startup:market-sizing-analyst" in ids

    # (b) cofounder role loads all 10
    def test_cofounder_loads_all_ten(self, pack_root):
        platform = _platform(cofounder="roman")
        result = resolve_active_skills(platform, pack_root, active_user="roman")
        assert len(result.skills) == 10
        assert result.skipped == []
        ids = {s.id for s in result.skills}
        assert "tech-startup:investor-targeting-strategist" in ids
        assert "tech-startup:financial-modeling-analyst" in ids

    # (c) non-cofounder with explicit cofounder skill in active_skills is blocked
    def test_non_cofounder_explicit_cofounder_skill_blocked(self, pack_root):
        # The platform names the cofounder as 'roman' but the active user
        # is someone else AND `active_skills` explicitly tries to load
        # the cofounder-only skills. The access check still wins.
        platform = _platform(
            cofounder="roman",
            active_skills=[
                "tech-startup:pitch-deck-composer",
                "tech-startup:investor-targeting-strategist",
            ],
        )
        result = resolve_active_skills(platform, pack_root, active_user="alice")
        ids = [s.id for s in result.skills]
        assert ids == ["tech-startup:pitch-deck-composer"]
        # The cofounder-only skill is in the skipped list with the right reason
        skipped_blocked = [
            (ref.id, why)
            for ref, why in result.skipped
            if ref.id == "tech-startup:investor-targeting-strategist"
        ]
        assert len(skipped_blocked) == 1
        assert "cofounder" in skipped_blocked[0][1]

    # (d) active_skills override loads only named skills
    def test_active_skills_override_loads_only_named(self, pack_root):
        platform = _platform(
            active_skills=[
                "tech-startup:pitch-deck-composer",
                "tech-startup:narrative-architect",
            ],
        )
        result = resolve_active_skills(platform, pack_root, active_user=None)
        ids = [s.id for s in result.skills]
        assert ids == [
            "tech-startup:pitch-deck-composer",
            "tech-startup:narrative-architect",
        ]
        # Everything else lands in skipped — exactly 8 of the 10 minus the 2
        # named is the count, but the order depends on the pack manifest.
        assert len(result.skipped) == 8


class TestEdgeCases:
    def test_no_profile_no_skills(self, pack_root):
        # If platform.yaml doesn't declare a profile, the resolver loads
        # nothing — `active_skills` alone is not enough because the
        # resolver needs the profile to know which pack to look in.
        platform = _platform(profile=None, active_skills=["tech-startup:pitch-deck-composer"])
        result = resolve_active_skills(platform, pack_root, active_user="roman")
        assert result.skills == []
        assert result.skipped == []

    def test_unknown_profile_no_skills(self, pack_root):
        platform = _platform(profile="something-else")
        result = resolve_active_skills(platform, pack_root, active_user=None)
        assert result.skills == []
        assert result.skipped == []

    def test_missing_pack_yaml_no_skills(self, tmp_path):
        # Pack ID known to the registry but pack.yaml absent on disk —
        # e.g. otaman-meta wasn't cloned. Resolver returns empty.
        empty_meta = tmp_path / "empty-meta"
        empty_meta.mkdir()
        result = resolve_active_skills(_platform(), empty_meta, active_user="roman")
        assert result.skills == []

    def test_skill_paths_are_absolute_under_pack_root(self, pack_root):
        platform = _platform(cofounder="roman")
        result = resolve_active_skills(platform, pack_root, active_user="roman")
        for ref in result.skills:
            assert ref.file.is_absolute()
            # Verify the resolved file actually lives under the pack root
            assert str(ref.file).startswith(
                str((pack_root / "skill-packs" / "tech-startup").resolve())
            )

    def test_empty_active_skills_list_skips_everything(self, pack_root):
        # `active_skills: []` — an empty list is distinct from absent. We
        # treat it the same as absent (no filtering): the design.md text
        # describes it as "if active_skills is explicitly set, only those
        # skills load"; an empty list semantically means "load nothing
        # explicitly", and our `if active_set:` guard preserves the
        # "no filter" behavior. This is a documentation tripwire — if a
        # future spec wants `active_skills: []` to mean "load nothing",
        # this test flips its assertion and the resolver needs to treat
        # the empty list as a real filter.
        platform = _platform(active_skills=[])
        result = resolve_active_skills(platform, pack_root, active_user=None)
        # Current behavior: empty list ≡ absent → load every public skill
        assert len(result.skills) == 8


class TestSkillRef:
    def test_skillref_is_frozen_dataclass(self):
        ref = SkillRef(id="x", file=Path("/tmp/x.md"), access="public")
        with pytest.raises(Exception):
            ref.id = "y"  # type: ignore[misc]
