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
    HOOK_UNCONFIGURED,
    INVARIANT_UNENFORCEABLE,
    NO_CONFIG,
    NO_ELIGIBLE,
    NOT_RUN,
    RAN,
    STACK_LAYERS,
    build_context,
    cofounder_stack,
    invariant_enforced,
    select_critic,
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

    def test_the_proposer_is_HANDED_TO_CORE_not_filtered_here(self):
        """The filter used to live here, and it only half-worked.

        Trimming `candidates` protects `sensitivity-scoped` and NOTHING else:
        `stakeholder-affected` reads `repo_owners`/`affected_repos` and never
        looks at `candidates`. That is the inversion I measured. core #104 owns
        the invariant now, so the proposer travels in the context and the
        candidate list is the full roster.
        """
        ctx = build_context(PLATFORM, proposer="a-agent")
        assert ctx.proposer == "a-agent", "core cannot exclude whom it is not told about"
        assert set(ctx.candidates) == {"a-agent", "b-agent", "c-agent"}

    def test_the_old_local_filter_is_gone_from_the_source(self):
        """A surviving local filter would make a sabotaged core look correct."""
        import pathlib

        import otaman_plugin.critic_selection as m

        src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
        assert "!= proposer" not in src, "the second home of the D4 invariant is back"

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

    def test_the_picker_has_exactly_one_home(self):
        """It migrated here (csp 1.2) and is NOT re-exported from the
        dispatcher — a re-export is how the retired local rule would survive as
        something to edit."""
        import pathlib

        import otaman_plugin.critic_selection as cs
        import otaman_plugin.spec_critique_dispatch as d

        dispatch_src = pathlib.Path(d.__file__).read_text(encoding="utf-8")
        assert "def select_critic(" not in dispatch_src, "the local picker is back"
        assert "sorted(candidates)[0]" not in dispatch_src, "the old D4 rule is back"
        assert d.select_critic is cs.select_critic
        assert "select_critic" not in d.__all__


def test_the_d4_inversion_is_now_CLOSED_by_core_not_by_me():
    """The measurement that held this migration, re-run after the ruling.

    `stakeholder-affected` still selects the owner of an affected repo — that
    is the policy working as designed, and the reason the proposer kept
    appearing. What changed is that the exclusion now runs OVER the policy
    (core #104), so the same inputs that used to yield the proposer now yield
    nobody from that policy and fall through.

    Both halves are asserted. If the first stops holding, the policy itself
    changed and the whole ruling wants re-reading.
    """
    from otaman_core.verification_gates import SelectionContext, select_critics

    cfg = _config()
    raw = SelectionContext(
        candidates=("a-agent", "b-agent", "c-agent"),
        affected_repos=("a",),
        repo_owners={"a": "a-agent", "b": "b-agent", "c": "c-agent"},
    )
    assert "a-agent" in select_critics(cfg, "spec-proposal", raw).critics, (
        "stakeholder-affected no longer selects the affected owner — re-check the ruling"
    )

    guarded = build_context(PLATFORM, affected_repos=("a",), proposer="a-agent")
    result = select_critics(cfg, "spec-proposal", guarded)
    assert "a-agent" not in result.critics, "the proposer is reviewing its own proposal"
    assert result.excluded_proposer is True


@pytest.mark.parametrize("layer", STACK_LAYERS)
def test_every_declared_layer_is_produced(layer):
    result = cofounder_stack(_config(), build_context(PLATFORM), hook="spec-proposal")
    assert any(la.layer == layer for la in result.layers)


class TestThePickerMigrated:
    """csp 1.2: JTBD-57's picker resolves through core's declared policies.

    It was HELD until spec-agent ruled, because taken literally the migration
    selects the proposer to review their own proposal. The ruling made
    independence an invariant OVER policies (csp shared-contracts, 20261001,
    citing this measurement) and core #104 implemented it, so the migration is
    no longer an inversion.
    """

    def _cfg(self, primary="stakeholder-affected", fallback="role-based"):
        return parse_verification_gates(
            {"hooks": {"spec-proposal-critique": {"primary": primary, "fallback": fallback}}}
        )

    def test_the_case_that_held_this_task_now_picks_an_independent_critic(self):
        """proposer owns the ONLY affected repo — the exact inversion."""
        choice = select_critic(
            PLATFORM,
            ("a",),
            proposer="a-agent",
            config=self._cfg(),
            agent_roles={a: ("critic",) for a in ("a-agent", "b-agent", "c-agent")},
            target_role="critic",
        )
        assert choice.critic != "a-agent", "the proposer is critiquing its own proposal"
        assert choice.critic == "b-agent"
        assert choice.excluded_proposer is True
        assert choice.fell_back is True, "the primary emptied, so the fallback is what ran"

    def test_the_policy_that_fired_is_recorded(self):
        choice = select_critic(PLATFORM, ("a", "b"), proposer="a-agent", config=self._cfg())
        assert choice.critic == "b-agent"
        assert choice.policy == "stakeholder-affected"
        assert choice.fell_back is False

    def test_prior_passes_critics_are_not_re_asked(self):
        """The D2 two-pass cap is the DISPATCHER's knowledge, not core's."""
        cfg = self._cfg()
        first = select_critic(PLATFORM, ("b", "c"), proposer="a-agent", config=cfg)
        second = select_critic(
            PLATFORM, ("b", "c"), proposer="a-agent", config=cfg, exclude={first.critic}
        )
        assert first.critic == "b-agent"
        assert second.critic == "c-agent"

    def test_selection_is_deterministic(self):
        cfg = self._cfg()
        picks = {
            select_critic(PLATFORM, ("b", "c"), proposer="a-agent", config=cfg).critic
            for _ in range(5)
        }
        assert picks == {"b-agent"}


class TestTheFourEmptyOutcomesAreDistinct:
    """nss clause 1. "No gate config", "this hook has no policy", "the engine
    cannot enforce D4" and "the policy selected nobody" are four situations; a
    bare None makes a dispatcher that silently stopped look like one that
    correctly found nothing."""

    def _cfg(self):
        return parse_verification_gates(
            {"hooks": {"spec-proposal-critique": {"primary": "stakeholder-affected"}}}
        )

    def test_no_config_is_not_no_eligible_critic(self):
        assert select_critic(PLATFORM, ("a",), proposer="x", config=None).reason == NO_CONFIG

    def test_an_unconfigured_hook_says_so(self):
        choice = select_critic(PLATFORM, ("a",), proposer="x", config=self._cfg(), hook="nope")
        assert choice.reason == HOOK_UNCONFIGURED

    def test_a_policy_that_selected_nobody_says_so(self):
        choice = select_critic(PLATFORM, (), proposer="a-agent", config=self._cfg())
        assert choice.reason == NO_ELIGIBLE
        assert choice.policy == "stakeholder-affected", "it still names what ran"

    def test_all_four_reasons_are_different_strings(self):
        reasons = {NO_CONFIG, HOOK_UNCONFIGURED, INVARIANT_UNENFORCEABLE, NO_ELIGIBLE}
        assert len(reasons) == 4


class TestItFailsClosedOnAnEngineThatCannotEnforceD4:
    """Merged is not installed. A bundle predating core #104 applies no
    exclusion at all, so `stakeholder-affected` hands the proposal back to its
    author. Declining to dispatch is not blocking the proposal (D1) — Stage 1's
    result still reaches the human on its own."""

    def _cfg(self):
        return parse_verification_gates(
            {"hooks": {"spec-proposal-critique": {"primary": "stakeholder-affected"}}}
        )

    def test_a_pre_104_engine_dispatches_NOBODY_rather_than_the_proposer(self, monkeypatch):
        import otaman_plugin.critic_selection as m

        monkeypatch.setattr(m, "invariant_enforced", lambda: False)
        choice = select_critic(PLATFORM, ("a",), proposer="a-agent", config=self._cfg())
        assert choice.critic is None, "it dispatched under an engine that cannot exclude"
        assert choice.reason == INVARIANT_UNENFORCEABLE

    def test_the_probe_reads_cores_recorded_fact_not_a_version(self):
        """`excluded_proposer` exists because core records the exclusion as a
        fact, so its presence is the engine's own statement that it applies."""
        from otaman_core.verification_gates import SelectionResult

        assert invariant_enforced() is True
        assert "excluded_proposer" in SelectionResult.__dataclass_fields__

    def test_the_probe_goes_FALSE_when_the_field_is_gone(self, monkeypatch):
        """Otherwise the fail-closed branch is unreachable and untested."""
        import otaman_core.verification_gates as vg

        class NoMarker:
            __dataclass_fields__ = {"hook": None, "policy": None, "critics": None}

        monkeypatch.setattr(vg, "SelectionResult", NoMarker)
        assert invariant_enforced() is False
