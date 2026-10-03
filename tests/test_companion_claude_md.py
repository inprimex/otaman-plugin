"""CLAUDE.md templates for the program-companion repos (pcrs 2.1/2.2).

The template is DERIVED from the two live dogfood repos, not invented beside
them, and it renders the committed public guide only — the orchestration rules
stay in the gitignored CLAUDE.local.md the generator owns.
"""

from __future__ import annotations

import pathlib

import pytest

from otaman_plugin.companion_claude_md import (
    BUSINESS,
    KINDS,
    NO_SENSITIVITY_DECLARED,
    STRATEGY,
    VOLATILE_SKILL_PACK_NOTE,
    CompanionRepoSpec,
    CompanionTemplateError,
    SensitivePath,
    render,
    spec_from_platform,
)

REPO = pathlib.Path(__file__).resolve().parent.parent

PLATFORM = {
    "repos": [
        {"name": "acme-specs", "path": "../acme-specs", "owner": "spec-agent"},
        {
            "name": "acme-business",
            "path": "../acme-business",
            "owner": "cpo-agent",
            "description": "Pitch deck and GTM.",
        },
        {
            "name": "acme-strategy",
            "path": "../acme-strategy",
            "owner": "cofounder-agent",
            "sensitivity": {
                "financial-projections/": {
                    "audience": "cofounder-only",
                    "note": "Investor-sensitive models.",
                }
            },
        },
        {"name": "unrelated-core", "path": "../unrelated-core", "owner": "core-agent"},
    ],
    "program": {"registries": {"skill_pack": "../acme-specs/skills/"}},
}


def _spec(**over) -> CompanionRepoSpec:
    base = {"kind": BUSINESS, "repo": "acme-business", "owner": "cpo-agent", "program": "acme"}
    base.update(over)
    return CompanionRepoSpec(**base)


class TestItRendersTheCommittedGuideAndNothingElse:
    """The generator deliberately never puts orchestration rules in a committed
    file (external-audit remediation) — they go to the gitignored
    CLAUDE.local.md. This renders the other half and must not leak into it."""

    FORBIDDEN = (
        "otaman send",
        "otaman check",
        ".agents/bus",
        "task-assignment",
        "Task Queue",
        "secrets.env",
        "Credential cascade",
        "decision-required",
    )

    @pytest.mark.parametrize("kind", KINDS)
    def test_no_orchestration_rule_reaches_the_committed_file(self, kind):
        text = render(_spec(kind=kind, repo=f"acme-{kind}"))
        leaked = [token for token in self.FORBIDDEN if token in text]
        assert not leaked, f"private orchestration leaked into a COMMITTED file: {leaked}"

    @pytest.mark.parametrize("kind", KINDS)
    def test_it_says_where_the_private_rules_actually_are(self, kind):
        """Otherwise an owner reads a guide with no bus rules in it and
        concludes there are none."""
        text = render(_spec(kind=kind, repo=f"acme-{kind}"))
        assert "CLAUDE.local.md" in text
        assert "gitignored" in text

    @pytest.mark.parametrize("kind", KINDS)
    def test_the_owner_is_named(self, kind):
        assert "cpo-agent" in render(_spec(kind=kind, owner="cpo-agent"))


class TestTheSensitivitySectionIsNeverSilentlyEmpty:
    """nss clause 2. An absent section reads as "nothing here is sensitive";
    what it means is "nobody classified it". 2.2 asks for sensitive-data access
    patterns to be DOCUMENTED, and an empty section documents nothing while
    looking like it did."""

    def test_no_declarations_SAYS_SO_rather_than_omitting_the_section(self):
        text = render(_spec())
        assert "## Sensitivity" in text
        assert NO_SENSITIVITY_DECLARED in text
        assert "nobody has classified it yet" in text

    def test_a_declared_class_is_rendered_with_its_audience_and_reason(self):
        text = render(
            _spec(
                sensitivity=(
                    SensitivePath("fundraising/", "cofounder-only", "Investor lists, DD."),
                )
            )
        )
        assert "`fundraising/`" in text
        assert "cofounder-only" in text
        assert "Investor lists, DD." in text
        assert NO_SENSITIVITY_DECLARED not in text

    #: Words that would make an unclassified path look resolved. The default
    #: must not be any of them — "nobody said" is not a clearance level.
    REASSURING = ("internal", "public", "cleared", "open", "team", "none")

    def test_a_path_with_no_audience_is_UNCLASSIFIED_not_quietly_safe(self):
        """Declared sensitive and then never given a reader is its own state.

        Asserted against the LITERAL word, not against the module's own
        constant: `UNCLASSIFIED in text` compares the constant to itself, so it
        stays green when someone renames it to "internal" — which is precisely
        the change this test exists to stop. Caught by sabotage, after it
        scored a clean 30/30.
        """
        text = render(_spec(sensitivity=(SensitivePath("drafts/"),)))
        assert "unclassified" in text
        assert "unclassified, not cleared" in text

    def test_the_default_audience_is_not_a_reassuring_word(self):
        rendered = SensitivePath("drafts/").render().lower()
        assert "unclassified" in rendered
        for word in self.REASSURING:
            assert f"**{word}**" not in rendered, (
                f"an unclassified path renders as {word!r} — nobody said is not a clearance"
            )

    def test_classified_and_unclassified_paths_are_told_apart_in_one_repo(self):
        text = render(
            _spec(
                sensitivity=(
                    SensitivePath("fundraising/", "cofounder-only"),
                    SensitivePath("drafts/"),
                )
            )
        )
        # The caveat must name ONLY the unclassified path. Naming the
        # classified one too would tell the reader their cofounder-only
        # directory is also unresolved.
        caveat = text.split("Paths listed with no audience")[1].split("\n\n")[0]
        assert "unclassified, not cleared" in caveat
        assert "`drafts/`" in caveat
        assert "fundraising" not in caveat
        assert "cofounder-only" in text


class TestItReadsPlatformConfig:
    def test_kind_is_inferred_from_the_name_suffix(self):
        assert spec_from_platform(PLATFORM, "acme-business").kind == BUSINESS
        assert spec_from_platform(PLATFORM, "acme-strategy").kind == STRATEGY

    def test_the_program_name_is_derived_not_assumed(self):
        assert spec_from_platform(PLATFORM, "acme-strategy").program == "acme"

    def test_only_the_programs_OWN_companions_are_listed_as_siblings(self):
        """A sibling list that includes every repo in the fleet is noise, and
        in a multi-program tenant it is a cross-program leak."""
        siblings = spec_from_platform(PLATFORM, "acme-business").siblings
        assert set(siblings) == {"acme-specs", "acme-strategy"}
        assert "unrelated-core" not in siblings

    def test_declared_sensitivity_survives_the_round_trip(self):
        spec = spec_from_platform(PLATFORM, "acme-strategy")
        assert spec.sensitivity[0].path == "financial-projections/"
        assert spec.sensitivity[0].audience == "cofounder-only"
        assert "cofounder-only" in render(spec)

    def test_a_list_shaped_declaration_works_too(self):
        cfg = {
            "repos": [
                {
                    "name": "acme-business",
                    "owner": "cpo-agent",
                    "sensitivity": [{"path": "fundraising/", "audience": "cofounder-only"}],
                }
            ]
        }
        assert spec_from_platform(cfg, "acme-business").sensitivity[0].audience == "cofounder-only"


class TestItRefusesRatherThanGuessing:
    """A scaffold that renders the WRONG kind's guide is worse than one that
    refuses: the guide is what the owner trusts on arrival."""

    def test_an_undeclared_repo_is_refused(self):
        with pytest.raises(CompanionTemplateError, match="not declared"):
            spec_from_platform(PLATFORM, "acme-ghost")

    def test_a_name_that_names_no_kind_is_refused(self):
        with pytest.raises(CompanionTemplateError, match="cannot tell which"):
            spec_from_platform(PLATFORM, "unrelated-core")

    def test_an_explicit_kind_overrides_a_misleading_suffix(self):
        cfg = {"repos": [{"name": "acme-strategy-archive", "owner": "x"}]}
        assert spec_from_platform(cfg, "acme-strategy-archive", kind=STRATEGY).kind == STRATEGY

    def test_an_ownerless_companion_is_refused(self):
        cfg = {"repos": [{"name": "acme-business", "owner": ""}]}
        with pytest.raises(CompanionTemplateError, match="no owner"):
            spec_from_platform(cfg, "acme-business")

    def test_an_unknown_kind_cannot_be_rendered(self):
        with pytest.raises(CompanionTemplateError, match="unknown companion kind"):
            render(_spec(kind="marketing"))


class TestTheVolatileSkillPackPathIsFlagged:
    """Both live dogfood repos point their skill pack into an OpenSpec CHANGE
    directory, which dies when that change archives. A template that bakes one
    ships the same time-bomb into every scaffolded program."""

    def test_a_changes_path_carries_the_warning(self):
        text = render(
            _spec(skill_pack="../acme-specs/openspec/changes/tech-startup-skill-pack/research/")
        )
        assert VOLATILE_SKILL_PACK_NOTE in text

    def test_a_stable_path_does_not(self):
        text = render(_spec(skill_pack="../acme-specs/skills/"))
        assert "`../acme-specs/skills/`" in text
        assert VOLATILE_SKILL_PACK_NOTE not in text

    def test_no_skill_pack_renders_no_line_at_all(self):
        """Absent and volatile are different; neither is a broken link."""
        text = render(_spec())
        assert "Skill pack" not in text


class TestTheTwoKindsAreActuallyDifferent:
    """Otherwise one template is being rendered twice under two names, and the
    direction of work between the repos — the thing that makes them two repos —
    is not stated anywhere."""

    def test_the_bodies_differ(self):
        assert render(_spec(kind=BUSINESS)) != render(_spec(kind=STRATEGY, repo="acme-strategy"))

    def test_strategy_flows_outward_and_business_inward(self):
        assert "OUTWARD" in render(_spec(kind=STRATEGY, repo="acme-strategy"))
        assert "INWARD" in render(_spec(kind=BUSINESS))

    @pytest.mark.parametrize("kind", KINDS)
    def test_both_carry_the_one_artifact_one_home_rule(self, kind):
        """The rule the live strategy repo learned the hard way (the 2026-09-20
        SOM-reconciliation split) — a model forked into both repos."""
        assert "One artifact, one home" in render(_spec(kind=kind, repo=f"acme-{kind}"))


class TestItDoesNotShipOtamansOwnContent:
    """A template is rendered into customer programs. Otaman's pipeline, skill
    filenames and people do not belong in it."""

    OTAMAN_SPECIFIC = ("Roman", "otaman-meta/.agents", "pitch-deck-composer", "JTBD")

    @pytest.mark.parametrize("kind", KINDS)
    def test_no_otaman_specific_content_in_a_rendered_customer_guide(self, kind):
        text = render(_spec(kind=kind, repo=f"acme-{kind}"))
        leaked = [token for token in self.OTAMAN_SPECIFIC if token in text]
        assert not leaked, f"Otaman's own content would ship to every program: {leaked}"

    def test_the_template_source_bakes_no_hardcoded_program_name(self):
        """`acme-business` must never render the string `otaman-business`."""
        text = render(_spec(kind=BUSINESS))
        assert "otaman-business" not in text
        assert "acme-business" in text
