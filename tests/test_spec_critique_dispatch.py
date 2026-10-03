"""spec-proposal-constitutional-gate 1.2: Stage-2 critic-session dispatch.

Tests against the REAL `otaman_core.spec_gate` and `otaman_core.owner_paths`
(otaman-core PR #48 / owner-paths, JTBD-48) rather than mocking them, matching
this repo's convention (test_spec_lifecycle_generation.py,
test_credential_cascade_section.py).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
scd = importlib.import_module("otaman_plugin.spec_critique_dispatch")

from otaman_core.owner_paths import PlatformConfig, RepoConfig  # noqa: E402
from otaman_core.spec_gate import LintFinding, LintResult, score_tier  # noqa: E402


def _lint_result(*, errors=0, warns=0) -> LintResult:
    findings = [LintFinding(f"e{i}", "error", "boom") for i in range(errors)]
    findings += [LintFinding(f"w{i}", "warn", "hmm") for i in range(warns)]
    score = max(0, 100 - errors * 25 - warns * 10)
    return LintResult(score=score, tier=score_tier(score), findings=tuple(findings))


def _platform() -> PlatformConfig:
    return PlatformConfig(
        repos=[
            RepoConfig(name="otaman-plugin", owner="plugin-agent"),
            RepoConfig(name="otaman-cli", owner="cli-agent"),
            RepoConfig(name="otaman-core", owner="core-agent"),
            RepoConfig(name="otaman-bridge", owner="bridge-agent"),
        ]
    )


class TestStage1Passed:
    def test_true_on_clean_result(self):
        assert scd.stage1_passed(_lint_result()) is True

    def test_true_on_warn_only_result(self):
        assert scd.stage1_passed(_lint_result(warns=2)) is True

    def test_false_when_any_error_finding(self):
        assert scd.stage1_passed(_lint_result(errors=1, warns=3)) is False


def _gates(primary="stakeholder-affected", fallback="role-based"):
    """The hook config the migrated picker now resolves through (csp 1.2)."""
    from otaman_core.verification_gates import parse_verification_gates

    return parse_verification_gates(
        {"hooks": {scd.SPEC_CRITIQUE_HOOK: {"primary": primary, "fallback": fallback}}}
    )


def _roles():
    return {r.owner: ("critic",) for r in _platform().repos}


class TestThePickerIsNoLongerHere:
    """csp 1.2 retired this module's local D4 rule onto core's declared
    policies. These tests moved with it (test_critic_selection.py); what stays
    here is the DISPATCHER's contract with the new picker."""

    def test_the_local_rule_is_gone(self):
        src = Path(scd.__file__).read_text(encoding="utf-8")
        assert "def select_critic(" not in src
        assert "sorted(candidates)[0]" not in src

    def test_without_gate_config_the_dispatcher_declines_rather_than_guessing(self):
        """The retired rule needed no config, so it ALWAYS produced a critic.
        The policy engine needs one. A tenant that has not written
        verification-gates.yaml gets no Stage 2 — and that is a stated reason,
        not a silent nothing, because the alternative is a dispatcher that
        quietly stopped looking like one that found nobody.
        """
        from otaman_plugin.critic_selection import NO_CONFIG, select_critic

        choice = select_critic(_platform(), ["otaman-cli"], proposer="cli-agent")
        assert choice.critic is None
        assert choice.reason == NO_CONFIG

        assert (
            scd.dispatch_critique(
                platform=_platform(),
                change="c",
                affected_repos=["otaman-cli"],
                proposer="cli-agent",
                lint_result=_lint_result(),
                proposal_summary="x",
            )
            is None
        )

    def test_a_CriticChoice_is_not_accidentally_truthy_against_a_name(self):
        """Guarding the trap this migration walked into: the old tests read
        `assert critic != "cli-agent"`, and a CriticChoice satisfies that for
        free. Two of them kept passing while selecting nobody at all."""
        from otaman_plugin.critic_selection import select_critic

        choice = select_critic(_platform(), ["otaman-cli"], proposer="cli-agent")
        assert choice != "cli-agent"  # true, and meaningless — hence .critic
        assert choice.critic is None
        assert choice.selected is False


class TestBuildCritiqueDispatch:
    def test_builds_envelope_with_registered_task_assignment_type(self):
        d = scd.build_critique_dispatch(
            change="spec-proposal-constitutional-gate",
            critic="core-agent",
            pass_index=1,
            proposal_summary="Two-stage gate...",
        )
        assert d.type == "task-assignment"
        assert d.to == "core-agent"
        assert "pass 1/2" in d.subject
        assert scd.CRITIC_SKILL_ID in d.body
        assert scd.CONSTITUTION_SKILL_ID in d.body

    def test_rejects_pass_index_below_one(self):
        try:
            scd.build_critique_dispatch(
                change="c", critic="core-agent", pass_index=0, proposal_summary="x"
            )
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_rejects_pass_index_above_cap(self):
        try:
            scd.build_critique_dispatch(
                change="c", critic="core-agent", pass_index=3, proposal_summary="x"
            )
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


class TestDeriveVerdict:
    def test_all_pass_is_pass(self):
        findings = [scd.CritiqueFinding(1, "pass", "ok"), scd.CritiqueFinding(2, "pass", "ok")]
        assert scd.derive_verdict(findings) == "pass"

    def test_any_comment_no_fail_is_has_comments(self):
        findings = [scd.CritiqueFinding(1, "pass", "ok"), scd.CritiqueFinding(2, "comment", "note")]
        assert scd.derive_verdict(findings) == "has-comments"

    def test_any_fail_is_fail_even_with_comments(self):
        findings = [
            scd.CritiqueFinding(1, "fail", "missing outcome"),
            scd.CritiqueFinding(2, "comment", "note"),
        ]
        assert scd.derive_verdict(findings) == "fail"


class TestBuildCritiqueResult:
    def test_uses_spec_mandated_message_type(self):
        result = scd.build_critique_result(
            change="c",
            proposer="cli-agent",
            critic="core-agent",
            pass_index=1,
            constitution_version="1.0.0",
            findings=[scd.CritiqueFinding(1, "pass", "ok")],
        )
        assert result.type == "spec-proposal-critique-result"
        assert result.type == scd.CRITIQUE_RESULT_TYPE

    def test_addressed_to_proposer_cc_spec_agent(self):
        result = scd.build_critique_result(
            change="c",
            proposer="cli-agent",
            critic="core-agent",
            pass_index=1,
            constitution_version="1.0.0",
            findings=[scd.CritiqueFinding(1, "pass", "ok")],
        )
        assert result.to == "cli-agent"
        assert "spec-agent" in result.cc

    def test_body_carries_verdict_version_and_findings(self):
        result = scd.build_critique_result(
            change="c",
            proposer="cli-agent",
            critic="core-agent",
            pass_index=2,
            constitution_version="1.0.0",
            findings=[scd.CritiqueFinding(3, "fail", "no affected_repos listed")],
        )
        assert "verdict: fail" in result.body
        assert "constitution_version: '1.0.0'" in result.body
        assert "pass_index: 2" in result.body
        assert "critic: 'core-agent'" in result.body
        assert "no affected_repos listed" in result.body


class TestDispatchCritique:
    def test_returns_none_on_stage1_failure(self):
        result = scd.dispatch_critique(
            platform=_platform(),
            change="c",
            affected_repos=["otaman-cli"],
            proposer="cli-agent",
            lint_result=_lint_result(errors=1),
            proposal_summary="x",
        )
        assert result is None

    def test_runs_on_stage1_pass_with_warns_only(self):
        result = scd.dispatch_critique(
            platform=_platform(),
            change="c",
            affected_repos=["otaman-cli"],
            proposer="cli-agent",
            lint_result=_lint_result(warns=1),
            proposal_summary="x",
            gates=_gates(),
            agent_roles=_roles(),
            target_role="critic",
        )
        assert result is not None
        assert result.to != "cli-agent"

    def test_returns_none_past_pass_cap(self):
        result = scd.dispatch_critique(
            platform=_platform(),
            change="c",
            affected_repos=["otaman-cli"],
            proposer="cli-agent",
            lint_result=_lint_result(),
            proposal_summary="x",
            pass_index=3,
            gates=_gates(),
            agent_roles=_roles(),
            target_role="critic",
        )
        assert result is None, "the D2 cap did not stop a 3rd pass"

    def test_returns_none_when_the_policy_selects_nobody(self):
        """NOT the old "every repo is affected" case — under
        stakeholder-affected that now selects every owner and yields a critic.
        The policy selects nobody when there is nothing to select OVER, and
        with no fallback configured there is nowhere else to go.
        """
        result = scd.dispatch_critique(
            platform=_platform(),
            change="c",
            affected_repos=[],
            proposer="cli-agent",
            lint_result=_lint_result(),
            proposal_summary="x",
            gates=_gates(fallback=None),
        )
        assert result is None

    def test_every_repo_affected_now_YIELDS_a_critic(self):
        """The behaviour change this migration makes, asserted rather than
        discovered later: D4 required an UNaffected repo, so a change touching
        everything had no critic. stakeholder-affected has the opposite shape —
        every owner is a stakeholder — and independence comes from the
        proposer exclusion instead.
        """
        platform = _platform()
        result = scd.dispatch_critique(
            platform=platform,
            change="c",
            affected_repos=[r.name for r in platform.repos],
            proposer="cli-agent",
            lint_result=_lint_result(),
            proposal_summary="x",
            gates=_gates(),
        )
        assert result is not None, "a fleet-wide change gets no review at all"
        assert result.to != "cli-agent"

    def test_second_pass_excludes_first_passs_critic(self):
        platform = _platform()
        first = scd.dispatch_critique(
            platform=platform,
            change="c",
            affected_repos=["otaman-cli"],
            proposer="cli-agent",
            lint_result=_lint_result(),
            proposal_summary="x",
            pass_index=1,
            gates=_gates(),
            agent_roles=_roles(),
            target_role="critic",
        )
        second = scd.dispatch_critique(
            platform=platform,
            change="c",
            affected_repos=["otaman-cli"],
            proposer="cli-agent",
            lint_result=_lint_result(),
            proposal_summary="x",
            pass_index=2,
            previous_critics=(first.to,),
            gates=_gates(),
            agent_roles=_roles(),
            target_role="critic",
        )
        assert second is not None
        assert second.to != first.to
