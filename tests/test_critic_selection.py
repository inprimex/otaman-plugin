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
from otaman_core.verification_gates import (
    VerificationGatesError,
    parse_verification_gates,
)

from otaman_plugin.critic_selection import (
    COULD_NOT_EVALUATE,
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


#: Every agent is a critic. core 1.4 refuses a hook whose pairing cannot
#: select for the self-owned single-repo shape, so a roles table and a
#: `role-based` arm are now the MINIMUM a parseable config carries — the
#: fixtures that omitted them were expressing a config no tenant can have.
ROLES = {"a-agent": ["critic"], "b-agent": ["critic"], "c-agent": ["critic"]}


def _config(primary="stakeholder-affected", clearances=None, fallback="role-based"):
    hook = {"primary": primary}
    if fallback is not None:
        hook["fallback"] = fallback
    if "role-based" in (primary, fallback):
        # csp 1.6: a role-based hook with no target-role is refused at parse,
        # same as one with no roles table. Both inputs live in the file now.
        hook["target-role"] = "critic"
    return parse_verification_gates(
        {
            "clearances": clearances or {},
            "roles": ROLES,
            "hooks": {"spec-proposal": hook},
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

    def test_the_proposer_is_PASSED_never_COMPARED(self):
        """A surviving local filter would make a sabotaged core look correct.

        `!= proposer` alone was too narrow a guard — cli hit the same thing on
        their surface and ruled the distinction that actually holds
        (20261003T040454): deriving the exclusion needs the proposer in a
        COMPARISON; delegating it only needs the proposer PASSED. So this bans
        every comparison and membership form rather than one spelling.

        Their phrasing is "passed, never bound", which is right for their
        surface and cannot be literal here: this module must take `proposer`
        as a parameter in order to hand it to core at all. The portable half
        of the rule is the comparison.
        """
        import ast
        import pathlib

        import otaman_plugin.critic_selection as m

        def _names(node):
            return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}

        tree = ast.parse(pathlib.Path(m.__file__).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            parts = [node.left, *node.comparators]
            if not any("proposer" in _names(part) for part in parts):
                continue
            # `proposer is not None` is a PRESENCE check — core cannot exclude
            # whom it is not told about, so asking whether there is one is the
            # delegating path, not a filter. Comparing it to anything else is
            # the filter.
            others = [
                part
                for part in parts
                if "proposer" not in _names(part)
                and not (isinstance(part, ast.Constant) and part.value is None)
            ]
            if others:
                offenders.append(f"line {node.lineno}: {ast.unparse(node)}")
        assert not offenders, (
            f"the proposer is COMPARED, not just passed — the D4 invariant has a "
            f"second home again: {offenders}"
        )

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
            {
                "roles": ROLES,
                "hooks": {
                    "spec-proposal-critique": {
                        "primary": primary,
                        "fallback": fallback,
                        "target-role": "critic",
                    }
                },
            }
        )

    def test_the_case_that_held_this_task_now_picks_an_independent_critic(self):
        """proposer owns the ONLY affected repo — the exact inversion.

        NOTE the `agent_roles`/`target_role` arguments: `role-based` reads them
        off the SELECTION CONTEXT, and no config file carries a roles table —
        not `verification-gates.yaml` (clearances + hooks only) and not
        `platform.yaml`. cli caught the same thing in their surface and had
        been reporting `role-based` as locally evaluated when it never was
        (20261003T040454).

        So this proves the PLUMBING works when a caller supplies roles. It does
        NOT prove a tenant can configure its way to this outcome, and the test
        name must not be read that way — see
        `test_NO_config_only_fallback_restores_a_self_owned_proposal`.
        """
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
            {
                "roles": ROLES,
                "hooks": {
                    "spec-proposal-critique": {
                        "primary": "stakeholder-affected",
                        "fallback": "role-based",
                        "target-role": "critic",
                    }
                },
            }
        )

    def test_no_config_is_not_no_eligible_critic(self):
        assert select_critic(PLATFORM, ("a",), proposer="x", config=None).reason == NO_CONFIG

    def test_an_unconfigured_hook_says_so(self):
        choice = select_critic(PLATFORM, ("a",), proposer="x", config=self._cfg(), hook="nope")
        assert choice.reason == HOOK_UNCONFIGURED

    def test_a_policy_that_selected_nobody_says_so(self):
        """The premise moved under csp 1.4: `affected_repos=()` used to select
        nobody, and now falls through to a `role-based` arm every parseable
        config must carry. So the genuine empty case is a roster whose only
        critic IS the proposer."""
        cfg = parse_verification_gates(
            {
                "roles": {"a-agent": ["critic"]},
                "hooks": {
                    "spec-proposal-critique": {
                        "primary": "role-based",
                        "target-role": "critic",
                    }
                },
            }
        )
        choice = select_critic(PLATFORM, ("a",), proposer="a-agent", config=cfg)
        assert choice.reason == NO_ELIGIBLE
        assert choice.policy == "role-based", "it still names what ran"
        assert choice.missing_inputs == (), "evaluated, and the answer was nobody"

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
            {
                "roles": ROLES,
                "hooks": {
                    "spec-proposal-critique": {
                        "primary": "stakeholder-affected",
                        "fallback": "role-based",
                        "target-role": "critic",
                    }
                },
            }
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


class TestTheGapIsClosedByConfigurationCompleteness:
    """csp 1.4 landed (core #122) and this class inverted.

    It used to measure the gap: all four policies as fallback, config-only
    inputs, every one yielding no critic for a self-owned proposal. That
    measurement is quoted in the requirement and was the evidence for the
    ruling (spec-agent 20261003T043726, option 2+3 over wording-only).

    core now (a) carries a `roles:` table so `role-based` resolves from
    configuration, (b) REFUSES at parse time a pairing that cannot select for
    that shape, and (c) reports `could_not_evaluate` distinctly. So the same
    inputs now produce a critic, and the tests that proved the gap become the
    tests that prove it is shut.

    I did not update them until core landed. The tripwires that said so both
    fired on this branch — the first signal was CI, where core is pulled from
    main and my sibling checkout was behind.
    """

    def _cfg(self, fallback="role-based", primary="stakeholder-affected"):
        return parse_verification_gates(
            {
                "roles": ROLES,
                "hooks": {
                    "spec-proposal-critique": {
                        "primary": primary,
                        "fallback": fallback,
                        **(
                            {"target-role": "critic"} if "role-based" in (primary, fallback) else {}
                        ),
                    }
                },
                "clearances": {"b-agent": ["internal"], "c-agent": ["internal"]},
            }
        )

    def test_a_self_owned_UNCLASSIFIED_proposal_now_gets_an_independent_critic(self):
        """Gate 2.1's clause, from config alone — no sensitivity, no
        caller-supplied roles, nothing the dispatcher had to invent."""
        choice = select_critic(PLATFORM, ("a",), proposer="a-agent", config=self._cfg())
        assert choice.critic == "b-agent", "the shape the whole ruling was about"
        assert choice.critic != "a-agent"
        assert choice.policy == "role-based"
        assert choice.fell_back is True
        assert choice.excluded_proposer is True

    def test_the_roles_table_comes_from_CONFIG_not_from_the_caller(self):
        """The distinction the correction turned on. Before 1.4 this worked
        only because I passed `agent_roles` myself, which no tenant can
        declare."""
        choice = select_critic(PLATFORM, ("a",), proposer="a-agent", config=self._cfg())
        from otaman_core.verification_gates import VerificationGatesConfig

        assert "roles" in VerificationGatesConfig.__dataclass_fields__, (
            "the table must live in the CONFIG; a caller-supplied one is what "
            "made my first recommendation wrong"
        )
        choice = select_critic(PLATFORM, ("a",), proposer="a-agent", config=self._cfg())
        assert choice.critic == "b-agent"
        assert choice.policy == "role-based"

    @pytest.mark.parametrize(
        "pairing",
        [
            ("stakeholder-affected", None),
            ("stakeholder-affected", "sensitivity-scoped"),
            ("consumer-chain", "sensitivity-scoped"),
        ],
    )
    def test_a_pairing_that_cannot_select_is_REFUSED_AT_PARSE(self, pairing):
        """Not "selects nobody at dispatch" — refused when the config is read.

        This is the half I could not have built: a tenant finds out when they
        write the file, not when a proposal goes unreviewed and nobody
        notices. My fixtures that omitted it were expressing a config no
        tenant can have.
        """
        primary, fallback = pairing
        with pytest.raises(VerificationGatesError, match="cannot select a critic"):
            self._cfg(primary=primary, fallback=fallback)

    def test_a_roleless_config_is_refused_too(self):
        """`role-based` in the pairing with no table behind it is the same
        hole wearing the right name."""
        with pytest.raises(VerificationGatesError, match="needs a roles table"):
            parse_verification_gates(
                {
                    "hooks": {
                        "h": {
                            "primary": "stakeholder-affected",
                            "fallback": "role-based",
                            "target-role": "critic",
                        }
                    }
                }
            )


class TestCouldNotEvaluateSurvivesButCannotBeREACHEDFromConfig:
    """The vacuity my own tripwire warned about, and it was right.

    csp 1.4 made `could_not_evaluate` distinct from no-eligible-critic, and I
    surfaced it as a fifth CriticChoice reason. csp 1.6 then put `target-role`
    in config and extended the parse-time refusal, so a role-based hook now
    needs BOTH a roles table and a target-role or the parse refuses it.

    `role-based` is the only policy that reports missing inputs, and its two
    inputs are now both parse-guaranteed. `ctx.target_role or hp.target_role`
    means a caller passing None gets the hook's configured value, so a caller
    cannot force the state either. From any PARSEABLE config, the
    could-not-evaluate path is unreachable.

    That is the right outcome — it is what configuration-completeness MEANS —
    but it leaves me with a reason code nothing can produce. Two honest
    options: delete it, or keep it as defence-in-depth against a core that
    reports a state I must not fold. Kept, because folding is precisely the
    defect csp 1.4 exists to prevent and core's field is still there for a
    future policy with declared inputs. What is NOT kept is a test pretending
    to drive it through a real config — that test would assert nothing.
    """

    def _cfg(self):
        return parse_verification_gates(
            {
                "roles": ROLES,
                "hooks": {
                    "spec-proposal-critique": {
                        "primary": "role-based",
                        "target-role": "critic",
                    }
                },
            }
        )

    def test_a_parseable_config_can_no_longer_produce_it(self):
        """The measurement behind this whole rewrite. Even asking for it
        explicitly does not get it: core falls back to the hook's value."""
        forced = select_critic(
            PLATFORM, ("a",), proposer="a-agent", config=self._cfg(), target_role=None
        )
        assert forced.reason != COULD_NOT_EVALUATE
        assert forced.critic == "b-agent", "the hook's configured role resolved it"

    def test_core_REFUSES_the_config_that_used_to_produce_it(self):
        """What used to be a runtime could-not-evaluate is now a parse error,
        which is strictly better: the tenant learns when they write the file."""
        with pytest.raises(VerificationGatesError, match="target.role|cannot select"):
            parse_verification_gates(
                {
                    "roles": ROLES,
                    "hooks": {"spec-proposal-critique": {"primary": "role-based"}},
                }
            )

    def test_the_mapping_STILL_WORKS_if_core_ever_reports_it(self, monkeypatch):
        """Defence-in-depth, driven by a stubbed result rather than a config
        that cannot exist. If a future policy gains a declared input, this is
        what stops me folding it into no-eligible-critic — the csp 1.4 defect,
        which I was one release away from shipping once already.
        """
        import otaman_core.verification_gates as vg

        real = vg.select_critics

        def _stub(config, hook, ctx):
            result = real(config, hook, ctx)
            return type(result)(
                hook=result.hook,
                policy=result.policy,
                critics=(),
                could_not_evaluate=("consumers",),
            )

        monkeypatch.setattr(vg, "select_critics", _stub)
        choice = select_critic(PLATFORM, ("a",), proposer="a-agent", config=self._cfg())
        assert choice.reason == COULD_NOT_EVALUATE, "folded into no-eligible-critic again"
        assert choice.missing_inputs == ("consumers",), "it must NAME what was missing"

    def test_an_evaluated_policy_that_chose_nobody_is_still_NO_ELIGIBLE(self):
        """The other side of the distinction — otherwise everything empty
        becomes "could not know" and the honest answer disappears instead."""
        cfg = parse_verification_gates(
            {
                "roles": {"a-agent": ["critic"]},
                "hooks": {
                    "spec-proposal-critique": {
                        "primary": "role-based",
                        "target-role": "critic",
                    }
                },
            }
        )
        choice = select_critic(PLATFORM, ("a",), proposer="a-agent", config=cfg)
        assert choice.critic is None, "a-agent is the proposer and the only critic"
        assert choice.reason == NO_ELIGIBLE
        assert choice.missing_inputs == ()


class TestCsp17TheConstantIsGone:
    """csp 1.7: the dispatcher-side target-role constant is deleted, not
    defaulted. core 1.6 resolves `ctx.target_role or hp.target_role`, so a
    surviving constant would SHADOW the configured value for every caller
    routing through here — a hook misconfigured in the file would keep working
    in this one place and nowhere else. Same single-home rule as route_id.
    """

    def test_the_constant_does_not_exist(self):
        import otaman_plugin.critic_selection as m

        assert not hasattr(m, "SPEC_CRITIQUE_ROLE"), "the constant is back"

    def test_no_role_string_is_hard_coded_in_the_module(self):
        """A literal "critic" reintroduced anywhere is the constant wearing a
        different name."""
        import ast
        import pathlib

        import otaman_plugin.critic_selection as m

        tree = ast.parse(pathlib.Path(m.__file__).read_text(encoding="utf-8"))
        literals = [
            n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == "critic"
        ]
        assert not literals, "a hard-coded role literal is back in the module"

    def test_build_context_leaves_target_role_UNSET_by_default(self):
        """Setting it unconditionally is how the file gets shadowed."""
        assert build_context(PLATFORM, proposer="a-agent").target_role is None

    def test_the_hooks_CONFIGURED_role_is_what_selects(self):
        cfg = parse_verification_gates(
            {
                "roles": {"b-agent": ["reviewer"], "c-agent": ["critic"]},
                "hooks": {
                    "spec-proposal-critique": {
                        "primary": "role-based",
                        "target-role": "reviewer",
                    }
                },
            }
        )
        choice = select_critic(PLATFORM, ("a",), proposer="a-agent", config=cfg)
        assert choice.critic == "b-agent", (
            "the hook asked for 'reviewer'; selecting c-agent would mean a "
            "hard-coded 'critic' won over the file"
        )

    def test_a_caller_may_still_override(self):
        """core supports `ctx.target_role or hp.target_role`, so the override
        is a real contract, not a leftover. Passing it through is not the
        same as defaulting it."""
        cfg = parse_verification_gates(
            {
                "roles": {"b-agent": ["reviewer"], "c-agent": ["critic"]},
                "hooks": {
                    "spec-proposal-critique": {
                        "primary": "role-based",
                        "target-role": "reviewer",
                    }
                },
            }
        )
        choice = select_critic(
            PLATFORM, ("a",), proposer="a-agent", config=cfg, target_role="critic"
        )
        assert choice.critic == "c-agent"
