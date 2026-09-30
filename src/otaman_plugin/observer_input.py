"""What the LLM security observer is allowed to see (security-gates-hook-c 1.5).

Hook C runs five layers in cost order; the observer is layer 5, advisory, and
the most expensive. Design D2: its input is the ENFORCEMENT POINT. The harness
constructs exactly three things —

  (a) needs-judgment findings from layers 1-4,
  (b) diff hunks no deterministic rule matched,
  (c) optionally an architectural-impact summary

— and the full diff is never passed. The spec calls a full diff reaching the
observer "a conformance defect enforced at input assembly".

WHY THIS IS A PIPELINE AND NOT A PROMPT. Telling the agent "only look at the
residual" is advisory: it is a sentence in a file the model may or may not
honour, and nothing fails when it doesn't. Building the restriction into the
assembly makes it structural — the full diff is not withheld from the observer,
it is never assembled into what the observer receives. Clause 3 is the proof:
restore the full diff and the tests fail.

Cost is the second-order benefit, not the point. D1: putting judgment last
means every LLM finding arrives with deterministic context already attached,
so the findings are better, not merely cheaper. The per-PR cost cap here is a
runtime backstop for the case where the residual is itself enormous.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Findings a deterministic layer produced but could not rule on. Only these
#: reach the observer — a finding the tools already decided is not judgment
#: work, and forwarding it would invite the LLM to relitigate a reproducible
#: verdict (D3: deterministic wins).
NEEDS_JUDGMENT = "needs-judgment"

#: Per-PR ceiling on assembled characters. A backstop, not the mechanism: if
#: this is doing the work, the residual filter upstream has failed.
DEFAULT_COST_CAP_CHARS = 60_000


@dataclass(frozen=True)
class Hunk:
    """One diff hunk, plus whether a deterministic rule already matched it."""

    path: str
    body: str
    matched_by: str | None = None

    @property
    def unmatched(self) -> bool:
        return not self.matched_by


@dataclass(frozen=True)
class Finding:
    """A layer 1-4 finding. Only ``disposition == NEEDS_JUDGMENT`` is forwarded."""

    layer: str
    rule: str
    path: str
    message: str
    disposition: str


@dataclass(frozen=True)
class ObserverInput:
    """Exactly what the observer receives. There is no full-diff field.

    That absence is the design. A struct carrying the whole diff plus a flag
    saying "don't read it" would put the restriction back in the prompt, which
    is where D2 says it must not live.
    """

    findings: tuple[Finding, ...] = ()
    hunks: tuple[Hunk, ...] = ()
    impact_summary: str | None = None
    dropped_for_cost: tuple[str, ...] = field(default_factory=tuple)
    capped: bool = False

    @property
    def is_empty(self) -> bool:
        """Nothing left for judgment — the cheap layers covered the diff.

        The spec's first scenario: a fully rule-covered PR reaches the observer
        as zero hunks at ~zero cost. Callers skip the observer entirely on this,
        and must STATE the skip rather than silently not running it.
        """
        return not self.findings and not self.hunks and not self.impact_summary


def assemble(
    findings: list[Finding],
    hunks: list[Hunk],
    impact_summary: str | None = None,
    cost_cap_chars: int = DEFAULT_COST_CAP_CHARS,
) -> ObserverInput:
    """Build the observer's input from layer 1-4 output.

    Filters to the residual: needs-judgment findings and unmatched hunks only.
    A hunk any rule matched is dropped — the deterministic layer already has a
    reproducible verdict on it, and re-showing it is both the cost and the
    invitation to disagree with evidence.

    Applies the cost cap by DROPPING whole hunks, never by truncating one.
    Half a hunk is worse than no hunk: it reads as complete context while
    hiding the line that mattered. What was dropped is named in
    ``dropped_for_cost`` so a capped run is never mistaken for a clean one.
    """
    kept_findings = tuple(f for f in findings if f.disposition == NEEDS_JUDGMENT)
    residual = [h for h in hunks if h.unmatched]

    budget = cost_cap_chars - sum(len(f.message) for f in kept_findings)
    budget -= len(impact_summary or "")

    kept_hunks: list[Hunk] = []
    dropped: list[str] = []
    for hunk in residual:
        cost = len(hunk.body)
        if cost <= budget:
            kept_hunks.append(hunk)
            budget -= cost
        else:
            dropped.append(hunk.path)

    return ObserverInput(
        findings=kept_findings,
        hunks=tuple(kept_hunks),
        impact_summary=impact_summary,
        dropped_for_cost=tuple(dropped),
        capped=bool(dropped),
    )


def render(observer_input: ObserverInput) -> str:
    """The observer's prompt payload — assembled from the struct and nothing else.

    Every call site must render through here. A caller that formats a diff
    itself bypasses the seam, which is precisely the defect clause 3 guards.
    """
    parts: list[str] = []
    if observer_input.findings:
        parts.append("## Findings needing judgment (layers 1-4 could not rule)")
        for f in observer_input.findings:
            parts.append(f"- [{f.layer}] `{f.rule}` {f.path}: {f.message}")
    if observer_input.hunks:
        parts.append("\n## Diff hunks no deterministic rule matched")
        for h in observer_input.hunks:
            parts.append(f"\n### {h.path}\n```diff\n{h.body}\n```")
    if observer_input.impact_summary:
        parts.append(f"\n## Architectural impact\n{observer_input.impact_summary}")
    if observer_input.capped:
        # Never a silent truncation: a capped review that reads as complete is
        # how a missed finding becomes an assurance.
        parts.append(
            "\n## INCOMPLETE — per-PR cost cap reached\n"
            "These paths were NOT shown and are unreviewed: "
            + ", ".join(observer_input.dropped_for_cost)
        )
    return "\n".join(parts)


def resolve_disagreement(
    deterministic_vulnerable: bool, observer_says_safe: bool
) -> tuple[bool, bool]:
    """(blocks, flag_for_triage) — D3: deterministic wins, dissent is surfaced.

    A tool saying vulnerable while the observer says safe BLOCKS, and the
    disagreement is flagged for a human rather than resolved by whichever ran
    last. The reverse is advisory by construction: layer 5 never blocks, so an
    observer worrying about something the tools cleared cannot stop a PR.
    """
    blocks = deterministic_vulnerable
    flag = deterministic_vulnerable and observer_says_safe
    return blocks, flag
