"""delivery-authorization-envelope 1.3 — generated instructions must make
emitting `decision-required` a duty, discharged BEFORE blocking.

The defect: a session waiting on an unanswered interactive prompt is alive and
still claims `working`. It cannot time out, cannot resolve itself, and cannot
be reached by a bus message — so it is found only when a human reads its pane.

Measured, not hypothetical. 2026-09-25: three halts, ~11h of fleet delivery,
all on already-approved work. 2026-09-26: an agent frozen 62 hours holding
verification gate srf 2.1, invisible until someone looked.

The pairing matters and the instruction has to state it honestly. srf 1.5's
HALTED verdict catches a session that blocked WITHOUT emitting — it is a net,
not a plan. An instruction that presented the backstop as equivalent would
licence exactly the silence this requirement removes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

GENERATOR = (
    Path(__file__).resolve().parent.parent / "src" / "otaman_plugin" / "generate_agent_config.py"
)


@pytest.fixture(scope="module")
def source() -> str:
    return GENERATOR.read_text(encoding="utf-8")


class TestTheDutyIsStated:
    def test_the_section_exists(self, source):
        assert "Never block silently" in source

    def test_it_says_emit_BEFORE_blocking(self, source):
        """'before or at the moment of blocking' is the requirement's wording.
        An instruction that merely mentions the message without the ordering
        leaves the agent free to emit after someone finds the frozen pane,
        which is no improvement at all."""
        assert "emit before you block" in source.lower()

    def test_all_four_fields_are_named(self, source):
        """The delta names four pieces: the agent (`from`), the decision, what
        it blocks, and the unblock condition. An agent cannot emit a valid
        message from a description that omits the frontmatter keys — core's
        validator enforces the latter three."""
        for key in ("decision:", "blocks:", "unblock-condition:"):
            assert key in source, f"frontmatter key {key!r} not named in the instruction"

    def test_the_send_form_is_concrete(self, source):
        assert "--type decision-required" in source


class TestTheBackstopIsNotOfferedAsAnAlternative:
    def test_halted_is_described_as_a_net_not_a_plan(self, source):
        """If the instruction presented HALTED as an equivalent path, an agent
        under time pressure would reasonably skip emitting — reintroducing the
        invisible halt through the text meant to prevent it."""
        assert "net, not a plan" in source
        assert "still your job" in source

    def test_it_says_a_halted_row_means_you_did_not_emit(self, source):
        assert "evidence you did not" in source


class TestTheReasonTravelsWithTheRule:
    def test_the_incident_is_attached(self, source):
        """A bare prohibition gets rationalised around under deadline; a rule
        carrying its incident survives contact with one. Same reasoning as the
        check-otaman-first guard."""
        assert "62 hours" in source
        assert "eleven hours" in source

    def test_the_defining_property_is_stated(self, source):
        """Why a bus message cannot rescue a halted session is the fact that
        makes the duty make sense — without it 'emit first' reads as
        bureaucracy."""
        assert "cannot be reached by a bus message" in source

    def test_the_uncertainty_case_is_resolved_toward_emitting(self, source):
        """An agent unsure whether something is a genuine decision point must
        not default to silence. The costs are asymmetric and the instruction
        says so."""
        assert "If you are unsure" in source
