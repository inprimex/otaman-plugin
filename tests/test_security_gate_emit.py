"""The plugin emits Hook C's security-gate-report (sghc 1.7, plugin half).

core #93 owns the schema and — critically — the blocking derivation
(`is_blocked`), stated there as existing "so the emitter (plugin) and the
renderer (cli) cannot disagree on whether a report blocks". This module's job
is to assemble the record and derive D3 disagreements, NOT to decide blocking.

The surface is Hook C's own, not JTBD-57's spec-proposal critique (ruling
20260930T210003). Two pipelines sharing the word "critique" is the conflation
class, and the ruling exists because my task wording invited exactly that.
"""

from __future__ import annotations

from otaman_core.security_gate_report import (
    LayerVerdict,
    SecurityGateReport,
    Suppression,
    is_blocked,
    report_from_dict,
)

from otaman_plugin.security_gate_emit import (
    REPORT_TYPE,
    build_report,
    render_summary,
    report_body,
)


def _fail(layer="ci-medium", *findings):
    return LayerVerdict(layer=layer, verdict="fail", findings=tuple(findings))


def _ok(layer="ci-fast"):
    return LayerVerdict(layer=layer, verdict="pass")


class TestDisagreementDerivation:
    def test_observer_clearing_a_failed_finding_is_recorded(self):
        """D3: the tool verdict stands and blocks; the dissent is recorded for
        a human rather than silently reconciled."""
        r = build_report(
            "otaman-plugin",
            [_fail("ci-medium", "taint: req.body -> exec")],
            observer_cleared=("taint: req.body -> exec",),
        )
        assert len(r.disagreements) == 1
        d = r.disagreements[0]
        assert d.deterministic == "vulnerable" and d.observer == "safe"
        assert d.layer == "ci-medium"

    def test_the_dissent_does_not_rescue_the_pr(self):
        """The whole point of D3: recording the disagreement must not soften
        the verdict."""
        r = build_report(
            "otaman-plugin",
            [_fail("ci-medium", "taint")],
            observer_cleared=("taint",),
        )
        assert is_blocked(r) is True

    def test_a_cleared_finding_nobody_failed_on_is_not_a_disagreement(self):
        """Manufacturing agreements-as-disagreements buries the real ones."""
        r = build_report("x", [_ok()], observer_cleared=("something nobody flagged",))
        assert r.disagreements == ()

    def test_observer_layer_failures_are_never_disagreements_with_themselves(self):
        """A disagreement is deterministic-vs-judgment. The observer's own
        findings are judgment on BOTH sides, so there is nothing to adjudicate.

        Uses verdict="fail" deliberately. An earlier version of this test used
        "advisory", which the `verdict != "fail"` clause rejects on its own —
        so the layer guard could be deleted with every test still green. A
        sabotage run scored 34/34 against exactly that deletion. The observer
        should never emit "fail" by design; this asserts the guard holds if
        something constructs one anyway.
        """
        r = build_report(
            "x",
            [LayerVerdict(layer="llm-observer", verdict="fail", findings=("maybe",))],
            observer_cleared=("maybe",),
        )
        assert r.disagreements == ()

    def test_multiple_dissents_are_each_recorded(self):
        r = build_report(
            "x",
            [_fail("ci-fast", "a"), _fail("ci-medium", "b", "c")],
            observer_cleared=("a", "c"),
        )
        assert {d.finding for d in r.disagreements} == {"a", "c"}


class TestBlockingIsNotDecidedHere:
    """The single-home boundary. core states is_blocked exists so emitter and
    renderer cannot disagree; a local rule would recreate the drift."""

    def test_module_defines_no_blocking_rule(self):
        import pathlib

        import otaman_plugin.security_gate_emit as m

        src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
        assert "def is_blocked" not in src
        assert "BLOCKING_VERDICT" not in src, "the blocking constant was re-derived locally"

    def test_summary_verdict_tracks_cores_rule(self):
        blocked = build_report("x", [_fail("ci-medium", "boom")])
        clean = build_report("x", [_ok()])
        assert "BLOCKED" in render_summary(blocked)
        assert "passed" in render_summary(clean)

    def test_an_unjustified_suppression_blocks_without_any_layer_failing(self):
        """core's rule has two limbs. Reimplementing only the layer limb here
        would pass every test that used a failing layer."""
        r = build_report(
            "x",
            [_ok()],
            suppressions=[Suppression(marker="# nosemgrep", location="a.py:4", justified=False)],
        )
        assert is_blocked(r) is True
        assert "BLOCKED" in render_summary(r)

    def test_a_justified_suppression_does_not_block(self):
        r = build_report(
            "x",
            [_ok()],
            suppressions=[
                Suppression(
                    marker="# nosemgrep",
                    location="a.py:4",
                    justified=True,
                    justification="false positive: constant input",
                )
            ],
        )
        assert is_blocked(r) is False


class TestSerialisation:
    def test_body_round_trips_through_cores_schema(self):
        """Serialising here instead of via core would let a core schema change
        leave the plugin emitting a shape the renderer no longer reads."""
        r = build_report(
            "otaman-plugin",
            [_fail("ci-medium", "taint")],
            pr="97",
            observer_cleared=("taint",),
            suppressions=[Suppression(marker="# nosemgrep", location="a.py:4", justified=False)],
        )
        back = report_from_dict(report_body(r))
        assert back.repo == r.repo and back.pr == r.pr
        assert len(back.disagreements) == 1
        assert len(back.unjustified_suppressions) == 1
        assert is_blocked(back) == is_blocked(r)

    def test_the_registered_type_is_used(self):
        assert REPORT_TYPE == "security-gate-report"

    def test_it_is_not_the_spec_proposal_critique_type(self):
        """The ruling's whole point — two pipelines, two surfaces."""
        from otaman_plugin.spec_critique_dispatch import CRITIQUE_RESULT_TYPE

        assert REPORT_TYPE != CRITIQUE_RESULT_TYPE


class TestSummaryIsActionable:
    def test_failing_layers_are_named(self):
        r = build_report("x", [_fail("ci-medium", "boom"), _ok("ci-fast")])
        assert "ci-medium" in render_summary(r)

    def test_unjustified_suppressions_are_named_individually(self):
        """'2 unjustified suppressions' sends someone hunting; the locations
        are the actionable part."""
        r = build_report(
            "x",
            [_ok()],
            suppressions=[
                Suppression(marker="# nosemgrep", location="a.py:4", justified=False),
                Suppression(marker="# noqa", location="b.py:9", justified=False),
            ],
        )
        out = render_summary(r)
        assert "a.py:4" in out and "b.py:9" in out

    def test_a_dissent_says_the_deterministic_verdict_stands(self):
        """Otherwise a reader may take the flag as doubt about the block."""
        r = build_report("x", [_fail("ci-medium", "t")], observer_cleared=("t",))
        assert "deterministic verdict stands" in render_summary(r)

    def test_a_clean_report_claims_nothing_extra(self):
        out = render_summary(SecurityGateReport(repo="x", layers=(_ok(),)))
        assert "passed" in out
        assert "dissent" not in out and "suppression" not in out
