"""Critic selection at the dispatch seam (critic-selection-policy 1.2).

core #97 owns the four policies and the clearance gate. This module owns what
only the dispatcher knows — building a SelectionContext from platform config,
and composing the cofounder 4-layer stack from the policies core provides.

NOT-RUN IS A RENDERED LAYER. A four-layer stack showing three layers reads as a
four-layer review that found nothing in the fourth. Every layer reports RAN or
NOT-RUN with a reason.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from otaman_core.verification_gates import parse_verification_gates

from otaman_plugin.critic_selection import (
    NOT_RUN,
    RAN,
    STACK_LAYERS,
    build_context,
    cofounder_stack,
)


@dataclass
class _Repo:
    name: str
    owner: str


@dataclass
class _Platform:
    repos: list


PLATFORM = _Platform([_Repo("a", "a-agent"), _Repo("b", "b-agent"), _Repo("c", "c-agent")])


def _config(primary="stakeholder-affected", clearances=None):
    return parse_verification_gates(
        {
            "clearances": clearances or {},
            "hooks": {"spec-proposal": {"primary": primary}},
        }
    )


def _layer(result, name):
    return next(la for la in result.layers if la.layer == name)


class TestContextBuilding:
    def test_repo_owners_are_derived_from_platform(self):
        ctx = build_context(PLATFORM)
        assert ctx.repo_owners == {"a": "a-agent", "b": "b-agent", "c": "c-agent"}

    def test_the_proposer_is_excluded_from_candidates(self):
        """Structural independence is a property of the DISPATCH, not of any one
        policy, so it is applied here where every policy inherits it."""
        ctx = build_context(PLATFORM, proposer="a-agent")
        assert "a-agent" not in ctx.candidates
        assert set(ctx.candidates) == {"b-agent", "c-agent"}

    def test_candidates_are_deterministic(self):
        """Same inputs, same order — a selection that varies run to run cannot
        be audited."""
        assert build_context(PLATFORM).candidates == build_context(PLATFORM).candidates
        assert list(build_context(PLATFORM).candidates) == sorted(
            build_context(PLATFORM).candidates
        )

    def test_sensitivity_is_carried_through(self):
        assert build_context(PLATFORM, sensitivity="secret").sensitivity == "secret"


class TestTheStackAccountsForEveryLayer:
    def test_all_four_layers_are_always_present(self):
        """Even when one cannot run. An omitted layer is indistinguishable from
        a layer that passed."""
        result = cofounder_stack(_config(), build_context(PLATFORM), hook="spec-proposal")
        assert tuple(la.layer for la in result.layers) == STACK_LAYERS

    def test_deterministic_always_runs(self):
        result = cofounder_stack(_config(), build_context(PLATFORM), hook="spec-proposal")
        assert _layer(result, "deterministic").state == RAN

    def test_self_critique_without_an_agent_is_not_run_with_a_reason(self):
        result = cofounder_stack(_config(), build_context(PLATFORM), hook="spec-proposal")
        layer = _layer(result, "self-critique")
        assert layer.state == NOT_RUN
        assert "nobody to self-critique" in layer.reason

    def test_self_critique_runs_when_an_agent_is_named(self):
        result = cofounder_stack(
            _config(), build_context(PLATFORM), hook="spec-proposal", self_critique_agent="a-agent"
        )
        assert _layer(result, "self-critique").critics == ("a-agent",)

    def test_human_is_always_a_reachable_layer(self):
        """Its availability is the point, not whether one has looked yet."""
        result = cofounder_stack(_config(), build_context(PLATFORM), hook="spec-proposal")
        assert _layer(result, "human").state == RAN


class TestTheClearanceGateRendersNotRun:
    """core's invariant: content with a sensitivity class reaches only critics
    declaring matching clearance, and `dropped_uncleared` records who was
    removed. This asserts the plugin RENDERS that rather than showing an empty
    layer."""

    def test_uncleared_candidates_make_the_peer_layer_not_run(self):
        cfg = _config(clearances={"b-agent": ["secret"]})
        ctx = build_context(PLATFORM, affected_repos=("a",), sensitivity="secret")
        layer = _layer(cofounder_stack(cfg, ctx, hook="spec-proposal"), "cleared-peer")
        assert layer.state == NOT_RUN

    def test_it_NAMES_who_was_dropped_and_why(self):
        """'No peer available' sends the reader hunting; the names do not."""
        cfg = _config(clearances={"b-agent": ["secret"]})
        ctx = build_context(PLATFORM, affected_repos=("a",), sensitivity="secret")
        layer = _layer(cofounder_stack(cfg, ctx, hook="spec-proposal"), "cleared-peer")
        assert "a-agent" in layer.reason
        assert "clearance" in layer.reason and "secret" in layer.reason

    def test_dropped_uncleared_is_carried_on_the_result(self):
        cfg = _config(clearances={"b-agent": ["secret"]})
        ctx = build_context(PLATFORM, affected_repos=("a",), sensitivity="secret")
        assert "a-agent" in cofounder_stack(cfg, ctx, hook="spec-proposal").dropped_uncleared

    def test_a_stack_with_a_not_run_layer_is_not_complete(self):
        """The property a caller must check before presenting a full review."""
        cfg = _config(clearances={"b-agent": ["secret"]})
        ctx = build_context(PLATFORM, affected_repos=("a",), sensitivity="secret")
        assert cofounder_stack(cfg, ctx, hook="spec-proposal").complete is False

    def test_a_fully_satisfied_stack_is_complete(self):
        ctx = build_context(PLATFORM, affected_repos=("a",))
        result = cofounder_stack(
            _config(), ctx, hook="spec-proposal", self_critique_agent="a-agent"
        )
        assert result.complete is True


class TestThePolicyIsRecorded:
    def test_the_firing_policy_is_named(self):
        """core names the policy on every selection; a gate result that does
        not say which rule chose its critic cannot be audited later."""
        ctx = build_context(PLATFORM, affected_repos=("a",))
        assert cofounder_stack(_config(), ctx, hook="spec-proposal").policy == (
            "stakeholder-affected"
        )

    def test_an_unconfigured_hook_renders_not_run_rather_than_raising(self):
        """core raises for an unconfigured hook (never empty critics). The stack
        must surface that as a rendered layer, not propagate an exception that
        loses the other three layers."""
        result = cofounder_stack(_config(), build_context(PLATFORM), hook="no-such-hook")
        layer = _layer(result, "cleared-peer")
        assert layer.state == NOT_RUN
        assert "refused" in layer.reason
        assert len(result.layers) == len(STACK_LAYERS)


class TestNoPolicyIsReimplemented:
    def test_the_module_does_not_reimplement_a_policy(self):
        """core owns the rules. A local copy is the drift this fleet has paid
        for repeatedly."""
        import pathlib

        import otaman_plugin.critic_selection as m

        src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
        assert "def select_critics" not in src
        assert src.count("select_critics(") >= 1, "it must CALL core's selector"

    def test_jtbd57_picker_is_deliberately_not_migrated(self):
        """Migrating it onto stakeholder-affected would invert D4 — see the
        module comment and the measurement in test_d4_inversion below."""
        import pathlib

        import otaman_plugin.critic_selection as m

        src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
        assert "def select_critic(" not in src
        assert "inverts D4" in src


def test_d4_inversion_is_real_not_assumed():
    """The measurement behind holding the picker migration.

    `stakeholder-affected` selects owners of AFFECTED repos; D4 selects an owner
    whose repo is NOT affected. With proposer a-agent and affected ("a",), the
    policy selects a-agent — the proposer reviewing its own proposal.
    """
    from otaman_core.verification_gates import select_critics

    cfg = _config()
    ctx = build_context(PLATFORM, affected_repos=("a",), proposer="a-agent")
    result = select_critics(cfg, "spec-proposal", ctx)
    assert "a-agent" in result.critics, (
        "if this stops holding, stakeholder-affected no longer selects the "
        "affected owner and the D4 concern may be resolved — re-check the ruling"
    )


@pytest.mark.parametrize("layer", STACK_LAYERS)
def test_every_declared_layer_is_produced(layer):
    result = cofounder_stack(_config(), build_context(PLATFORM), hook="spec-proposal")
    assert any(la.layer == layer for la in result.layers)
