"""Every shipped skill's frontmatter is a contract (ufbpr 3.1 / ppsm 2.4).

Nothing validated this before. Ten SKILL.md files ship from this repo and the
only thing standing between a malformed one and a session that silently never
matches it was whoever last read the file.

WHY THE FRONTMATTER SPECIFICALLY. `description` is what trigger-matching reads
(ppsm: "Skills NOT activated SHALL NOT have their descriptions loaded into
agent system prompts" — the description IS the activation surface). A skill
with a missing or empty description does not fail; it ships, loads, and never
fires. That is the silent-success shape, in the one place where the symptom is
indistinguishable from "the user never asked for it".

WHAT THIS DOES NOT DECIDE. ppsm's spec example writes `id: example:my-skill`
and a `triggers: - keywords: [...]` mapping; all ten shipped skills write
`name:` and a flat string list, which is what Claude Code actually reads. One
of those is wrong and it is NOT this test's call — ppsm 2.4 is spec-agent's
task. So this pins the shape the fleet ACTUALLY ships, consistently, and the
divergence is reported rather than silently resolved in either direction.
Picking a side here would make the wrong one canon by being first.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

SKILLS_DIR = pathlib.Path(__file__).resolve().parent.parent / "skills"

#: The key every shipped skill uses to name itself. ppsm's example says `id:`;
#: Claude Code reads `name:`. Pinned to what ships, pending ppsm 2.4.
NAME_KEY = "name"

#: Keys a skill may declare. An unknown key is usually a typo for one of
#: these, and a typo'd `descriptionn:` is a skill that never matches.
KNOWN_KEYS = frozenset({"name", "description", "triggers", "version", "allowed-tools"})


def _skills() -> list[pathlib.Path]:
    return sorted(p for p in SKILLS_DIR.glob("*/SKILL.md"))


def _frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path.parent.name}: no YAML frontmatter block")
    _, block, _ = text.split("---\n", 2)
    return yaml.safe_load(block) or {}


IDS = [p.parent.name for p in _skills()]


def test_there_are_skills_to_check():
    """Otherwise every parametrised test below passes by collecting nothing —
    a green suite proving the directory is empty."""
    assert len(_skills()) >= 5, f"only found {len(_skills())} SKILL.md files"


@pytest.mark.parametrize("path", _skills(), ids=IDS)
class TestEveryShippedSkill:
    def test_has_parseable_frontmatter(self, path):
        assert isinstance(_frontmatter(path), dict)

    def test_names_itself_after_its_directory(self, path):
        """A skill whose `name` disagrees with its directory is addressed by
        one and found by the other."""
        fm = _frontmatter(path)
        assert fm.get(NAME_KEY) == path.parent.name

    def test_has_a_NON_EMPTY_description(self, path):
        """The description is the activation surface. Absent or blank, the
        skill ships, loads, and never fires — and nothing reports that,
        because "never matched" looks exactly like "never asked for"."""
        desc = _frontmatter(path).get("description")
        assert isinstance(desc, str), f"{path.parent.name}: description is {type(desc).__name__}"
        assert desc.strip(), f"{path.parent.name}: description is blank"
        assert len(desc.strip()) >= 40, (
            f"{path.parent.name}: description is {len(desc.strip())} chars — too thin to "
            "match on; it is the only text the matcher sees"
        )

    def test_declares_no_unknown_frontmatter_key(self, path):
        """A typo'd key is silently ignored by the runtime, so `descriptionn:`
        is a skill with no description that looks like it has one."""
        unknown = set(_frontmatter(path)) - KNOWN_KEYS
        assert not unknown, f"{path.parent.name}: unknown frontmatter key(s) {sorted(unknown)}"

    def test_triggers_if_present_are_a_flat_list_of_nonempty_strings(self, path):
        triggers = _frontmatter(path).get("triggers")
        if triggers is None:
            return
        assert isinstance(triggers, list), f"{path.parent.name}: triggers is not a list"
        for t in triggers:
            assert isinstance(t, str) and t.strip(), f"{path.parent.name}: bad trigger {t!r}"

    def test_has_a_body_below_the_frontmatter(self, path):
        """Frontmatter alone activates a skill that then instructs nothing."""
        body = path.read_text(encoding="utf-8").split("---\n", 2)[2]
        assert len(body.strip()) > 200, f"{path.parent.name}: body is {len(body.strip())} chars"


def test_the_fleet_is_CONSISTENT_about_the_name_key():
    """Whichever key is right, ten skills must not use two.

    ppsm 2.4 decides between `name:` (what Claude Code reads, what all ten
    ship) and `id:` (what ppsm's spec example writes). This asserts only that
    the answer is uniform — a split fleet is wrong under either ruling.
    """
    keys = {p.parent.name: set(_frontmatter(p)) & {"name", "id"} for p in _skills()}
    distinct = {frozenset(v) for v in keys.values()}
    assert len(distinct) == 1, f"skills disagree on how they name themselves: {keys}"


class TestBaSkill:
    """ufbpr 3.1's deliverable. It predates the task (PR #14, 2026-07-08), so
    it is checked against 3.1's four requirements rather than assumed to meet
    them for having existed first."""

    @pytest.fixture
    def text(self):
        return (SKILLS_DIR / "ba-skill" / "SKILL.md").read_text(encoding="utf-8")

    def test_it_states_a_mandate(self, text):
        assert "Authority model" in text
        assert "NEVER autonomously commit" in text

    def test_the_tool_surface_is_read_only_on_live_registries(self, text):
        assert "Read-only on live registries" in text
        assert "_draft/" in text, "no draft staging named"

    def test_it_defines_the_HITL_handoff(self, text):
        assert "HITL handoff" in text
        assert "ready-for-review" in text

    def test_it_does_cross_artifact_lookup(self, text):
        assert "Cross-artifact lookup" in text

    def test_it_refuses_to_scaffold_a_disabled_capability(self, text):
        """Scaffolding into a capability the program never enabled produces
        artifacts nothing will ever read."""
        assert "If a registry is not enabled" in text

    def test_it_asserts_a_schema_THAT_IS_NOT_SPECIFIED_YET(self, text):
        """NOT a failure — a pinned measurement, and a tripwire.

        The skill names concrete flow/process fields and hands the BA YAML
        templates to copy. ufbpr 1.1 and 1.2 — the tasks that actually SPECIFY
        those schemas — are both still open, and the skill was written three
        months before them. If 1.1/1.2 land different names, this skill
        silently instructs the BA to author invalid YAML.

        This test exists so that lands as a red test rather than as a BA's
        confusing afternoon. When the schemas are specified, reconcile this
        list against them and update both together.
        """
        asserted = (
            "outcome-id",
            "triggers-process",
            "data-contract",
            "components",
            "actors",
            "domain",
        )
        present = [f for f in asserted if f"`{f}`" in text]
        assert present == list(asserted), (
            "the skill's asserted field set changed — reconcile it against ufbpr "
            f"1.1/1.2 before updating this list. missing: {set(asserted) - set(present)}"
        )
