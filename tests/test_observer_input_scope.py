"""The observer sees only the residual (security-gates-hook-c 1.5, design D2).

Hook C's layer 5 is the LLM security observer: advisory, and the expensive one.
Its input is STRICTLY needs-judgment findings from layers 1-4, diff hunks no
rule matched, and optionally an impact summary. The spec calls a full diff
reaching the observer "a conformance defect enforced at input assembly".

CLAUSE 3 IS THE POINT OF THIS FILE: restore the full diff and these fail. The
restriction has to be structural, because as a sentence in the agent's prompt
it is advisory — nothing fails when a model ignores it, and nothing tells you
it did.
"""

from __future__ import annotations

from otaman_plugin.observer_input import (
    DEFAULT_COST_CAP_CHARS,
    NEEDS_JUDGMENT,
    Finding,
    Hunk,
    ObserverInput,
    assemble,
    render,
    resolve_disagreement,
)

SECRET = "AKIAIOSFODNN7EXAMPLE"


def _hunk(path, body, matched_by=None):
    return Hunk(path=path, body=body, matched_by=matched_by)


def _finding(disposition=NEEDS_JUDGMENT, **kw):
    base = dict(layer="ci-medium", rule="semgrep.taint", path="a.py", message="tainted sink")
    base.update(kw)
    return Finding(disposition=disposition, **base)


class TestOnlyTheResidualIsAssembled:
    def test_matched_hunks_are_dropped(self):
        """A rule already ruled on it. Re-showing it is the cost AND an
        invitation to relitigate reproducible evidence (D3)."""
        out = assemble(
            [],
            [_hunk("a.py", "+ danger", matched_by="semgrep.taint"), _hunk("b.py", "+ residual")],
        )
        assert [h.path for h in out.hunks] == ["b.py"]

    def test_fully_covered_diff_reaches_the_observer_as_nothing(self):
        """The spec's first scenario: cost ~zero for a fully-covered PR."""
        out = assemble(
            [_finding(disposition="resolved")],
            [_hunk("a.py", "+ x", matched_by="gitleaks"), _hunk("b.py", "+ y", matched_by="trivy")],
        )
        assert out.is_empty
        assert render(out) == ""

    def test_only_needs_judgment_findings_are_forwarded(self):
        out = assemble(
            [
                _finding(disposition="resolved", path="settled.py"),
                _finding(disposition=NEEDS_JUDGMENT, path="unsure.py"),
                _finding(disposition="suppressed", path="waived.py"),
            ],
            [],
        )
        assert [f.path for f in out.findings] == ["unsure.py"]

    def test_the_struct_has_nowhere_to_put_a_full_diff(self):
        """CLAUSE 3, structural half.

        A field carrying the whole diff plus a flag saying "don't read it"
        would put the restriction back in the prompt, which is exactly what
        D2 forbids. The absence IS the enforcement.
        """
        assert not hasattr(ObserverInput(), "full_diff")
        assert not hasattr(ObserverInput(), "diff")
        fields = ObserverInput().__dataclass_fields__
        assert set(fields) == {
            "findings",
            "hunks",
            "impact_summary",
            "dropped_for_cost",
            "capped",
        }

    def test_restoring_the_full_diff_shows_up_as_matched_hunks_leaking(self):
        """CLAUSE 3, behavioural half: the most likely way someone 'restores'
        the full diff is by passing every hunk through as unmatched."""
        full_diff = [_hunk("a.py", f"+ {SECRET}", matched_by="gitleaks")]
        out = assemble([], full_diff)
        assert out.hunks == (), "a rule-matched hunk reached the observer"
        assert SECRET not in render(out)


class TestCostCap:
    def test_cap_drops_whole_hunks_never_half_of_one(self):
        """Half a hunk reads as complete context while hiding the line that
        mattered — worse than omitting it and saying so."""
        big = _hunk("big.py", "x" * 500)
        out = assemble([], [big], cost_cap_chars=100)
        assert out.hunks == ()
        assert out.dropped_for_cost == ("big.py",)

    def test_a_capped_run_says_so_in_the_payload(self):
        """A truncated review that reads as complete turns a missed finding
        into an assurance."""
        out = assemble([], [_hunk("big.py", "x" * 500)], cost_cap_chars=100)
        assert out.capped
        body = render(out)
        assert "INCOMPLETE" in body and "big.py" in body

    def test_an_uncapped_run_claims_nothing_about_completeness(self):
        out = assemble([], [_hunk("a.py", "+ x")])
        assert not out.capped
        assert "INCOMPLETE" not in render(out)

    def test_findings_and_summary_count_against_the_budget(self):
        """Otherwise the cap is bypassable by moving bulk into the summary."""
        out = assemble(
            [_finding(message="m" * 90)],
            [_hunk("a.py", "x" * 50)],
            impact_summary=None,
            cost_cap_chars=100,
        )
        assert out.dropped_for_cost == ("a.py",)

    def test_default_cap_is_a_backstop_not_the_mechanism(self):
        """An ordinary residual must pass untouched — a cap that fires
        routinely means the upstream filter is broken and nobody notices."""
        out = assemble([], [_hunk("a.py", "+ x") for _ in range(20)])
        assert not out.capped
        assert DEFAULT_COST_CAP_CHARS > 1000


class TestRenderIsTheOnlyDoor:
    def test_render_emits_only_assembled_content(self):
        out = assemble(
            [_finding(message="tainted")],
            [_hunk("a.py", "+ residual"), _hunk("b.py", "+ covered", matched_by="semgrep")],
            impact_summary="touches auth",
        )
        body = render(out)
        assert "tainted" in body and "+ residual" in body and "touches auth" in body
        assert "+ covered" not in body

    def test_empty_input_renders_empty_not_a_stub(self):
        """An empty prompt is how the caller knows to skip the observer; a
        polite 'nothing to review' would still cost a call."""
        assert render(ObserverInput()) == ""


class TestDisagreementIsFlaggedNotResolved:
    def test_deterministic_vulnerable_blocks_even_when_observer_says_safe(self):
        blocks, flag = resolve_disagreement(deterministic_vulnerable=True, observer_says_safe=True)
        assert blocks is True
        assert flag is True, "the dissent must reach a human, not be silently dropped"

    def test_agreement_on_vulnerable_blocks_without_a_triage_flag(self):
        blocks, flag = resolve_disagreement(deterministic_vulnerable=True, observer_says_safe=False)
        assert blocks is True and flag is False

    def test_observer_alone_never_blocks(self):
        """Layer 5 is advisory by construction — the reverse disagreement
        cannot stop a PR."""
        blocks, flag = resolve_disagreement(
            deterministic_vulnerable=False, observer_says_safe=False
        )
        assert blocks is False and flag is False

    def test_clean_on_both_sides_passes(self):
        assert resolve_disagreement(False, True) == (False, False)
