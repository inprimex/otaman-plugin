"""Emit Hook C's ``security-gate-report`` (security-gates-hook-c 1.7, plugin half).

The ladder's layers run elsewhere; this turns their outcomes into the record
core #93 defined, which cli renders in the review flow. Ruling 20260930T210003
gave Hook C its own surface rather than reusing JTBD-57's spec-proposal
critique — two pipelines sharing the word "critique" is the conflation class.

BLOCKING IS NOT DECIDED HERE. ``otaman_core.security_gate_report.is_blocked``
is the one derivation, so the emitter (this module) and the renderer (cli)
cannot disagree about whether a report stops a PR. My 1.5 stand-in computed
``blocks = deterministic_vulnerable`` locally; that was correct in isolation
and is deleted now rather than left as a second copy of a rule with one home.
Two implementations of a rule agree until the day they do not, and that day is
the one nobody is watching.

What IS decided here is the DISAGREEMENT (design D3): a deterministic layer
calling something vulnerable while the observer calls it safe. The
deterministic verdict stands and blocks; the dissent is recorded for human
triage, never silently reconciled. The reverse — observer worried, tools clean
— is advisory by construction and records no disagreement, because layer 5
cannot block and a "disagreement" nobody can act on is noise in a triage queue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from otaman_core.security_gate_report import SecurityGateReport

#: The registered bus type (core #93 added it to validate_message.VALID_TYPES).
REPORT_TYPE = "security-gate-report"

#: Layers whose findings are judgments, not reproducible evidence. A
#: disagreement is only meaningful against a DETERMINISTIC verdict.
_OBSERVER_LAYER = "llm-observer"


def build_report(
    repo: str,
    layer_verdicts: list[Any],
    *,
    pr: str | None = None,
    observer_cleared: tuple[str, ...] = (),
    suppressions: list[Any] | None = None,
) -> SecurityGateReport:
    """Assemble the report; derive D3 disagreements from the layer verdicts.

    *observer_cleared* names findings the LLM observer judged safe. A finding
    that a deterministic layer FAILED on and the observer cleared is recorded
    as a :class:`Disagreement` — the tool verdict already blocks via
    ``is_blocked``; this makes the dissent visible to the human who triages it.

    A name in *observer_cleared* that no deterministic layer failed on produces
    nothing: there is no conflict, and manufacturing one would bury the real
    disagreements in a queue of agreements.
    """
    from otaman_core.security_gate_report import Disagreement, SecurityGateReport

    failed: list[tuple[str, str]] = []
    for verdict in layer_verdicts:
        if verdict.layer == _OBSERVER_LAYER or verdict.verdict != "fail":
            continue
        for finding in verdict.findings:
            failed.append((finding, verdict.layer))

    cleared = set(observer_cleared)
    disagreements = tuple(
        Disagreement(
            finding=finding,
            deterministic="vulnerable",
            observer="safe",
            layer=layer,
        )
        for finding, layer in failed
        if finding in cleared
    )

    return SecurityGateReport(
        repo=repo,
        pr=pr,
        layers=tuple(layer_verdicts),
        disagreements=disagreements,
        suppressions=tuple(suppressions or ()),
    )


def report_body(report: SecurityGateReport) -> dict[str, Any]:
    """The bus/artifact body for *report*, via core's serializer.

    Round-trips through core's own ``report_to_dict`` rather than building a
    dict here, so a schema change in core cannot leave the plugin emitting a
    shape the renderer no longer reads.
    """
    from otaman_core.security_gate_report import report_to_dict

    return report_to_dict(report)


def render_summary(report: SecurityGateReport) -> str:
    """A short human line for the PR/review flow.

    States the gate outcome, then the two things a reader must not miss: an
    unjustified suppression (which is itself a block) and a recorded dissent.
    A report that blocks and says only "blocked" sends someone to read five
    layers of output to find out why.
    """
    from otaman_core.security_gate_report import is_blocked

    verdict = "BLOCKED" if is_blocked(report) else "passed"
    parts = [f"Hook C {verdict} for {report.repo}"]

    failures = [la for la in report.layers if la.verdict == "fail"]
    if failures:
        parts.append("failing layers: " + ", ".join(la.layer for la in failures))

    unjustified = report.unjustified_suppressions
    if unjustified:
        # Named individually: "2 unjustified suppressions" is not actionable.
        parts.append(
            "unjustified suppressions: "
            + ", ".join(f"{s.marker} at {s.location}" for s in unjustified)
        )

    if report.disagreements:
        parts.append(
            f"{len(report.disagreements)} observer dissent(s) flagged for triage — "
            "the deterministic verdict stands"
        )
    return "; ".join(parts)
