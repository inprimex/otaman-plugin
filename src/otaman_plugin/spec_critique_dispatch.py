"""Stage-2 critic-session dispatch (spec-proposal-constitutional-gate 1.2, JTBD-57).

Stage 1 is otaman-core's deterministic lint (`otaman_core.spec_gate.lint_proposal`
-> `LintResult`). This module is Stage 2's plugin-owned half: on a Stage 1 pass,
decide whether/who runs the Constitutional critique (design D4 — structurally
independent, deterministic selection), and build the two bus-message envelopes
that carry it — the dispatch request to the critic, and the critic's own
`spec-proposal-critique-result` reply. It performs no bus I/O itself; callers
hand the returned envelope to `otaman send` (CLI) or `otaman_send` (MCP).

Comment-never-block (D1): nothing here refuses a proposal. A missing eligible
critic or an exhausted pass cap just means Stage 2 doesn't run (`dispatch_critique`
returns ``None``) — the proposal still reaches the human queue on Stage 1's
result alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from otaman_core.owner_paths import PlatformConfig
    from otaman_core.spec_gate import LintResult

#: The versioned rubric skill (design D3). Referenced by id only — this
#: module never reads the skill file; the critic session does that itself.
CONSTITUTION_SKILL_ID = "tech-startup:spec-critique-constitution"

#: The critic-persona skill the dispatched session runs.
CRITIC_SKILL_ID = "spec-critique"

#: Design D2's hard cap — a 3rd pass is refused, not attempted.
MAX_PASSES = 2

#: Requirement text: "emitting a `spec-proposal-critique-result` bus message."
#: Not yet in shared-contracts' registered type table as of 2026-09-08 — a
#: known gap (flagged to spec-agent separately); `otaman send` degrades an
#: unregistered type to a warning, not a hard error, so dispatch proceeds.
CRITIQUE_RESULT_TYPE = "spec-proposal-critique-result"

VERDICTS = ("pass", "fail", "has-comments")


def stage1_passed(lint_result: LintResult) -> bool:
    """Whether Stage 1 passed and Stage 2 may run.

    A "pass" is the absence of any error-level finding — a `warn`-only
    result (e.g. a malformed-but-present outcome id) still triggers Stage 2;
    Stage 1's own score/tier is advisory context for the critic, not the
    gate itself (D1: Stage 1 "failures" are what return to the proposer
    immediately, per the spec-proposal-gate delta).
    """
    return not any(f.level == "error" for f in lint_result.findings)


def select_critic(
    platform: PlatformConfig,
    affected_repos: list[str] | tuple[str, ...] | set[str],
    *,
    proposer: str,
    exclude: frozenset[str] | set[str] = frozenset(),
) -> str | None:
    """Deterministically pick a structurally independent critic (D4).

    Eligible = the agent owns a repo declared in ``platform.repos``, that
    repo is NOT in ``affected_repos``, and the agent is neither ``proposer``
    nor in ``exclude`` (callers pass prior passes' critics here to avoid
    repeating the same critic across a proposal's 2-pass cap, though the
    spec only requires the affected_repos exclusion).

    Deterministic = candidates are sorted by agent name and the first is
    returned, so the same inputs always yield the same critic. Returns
    ``None`` if no eligible candidate exists (e.g. every declared repo is
    affected) — callers treat that as "Stage 2 doesn't run", not an error.
    """
    affected = set(affected_repos)
    candidates = {
        repo.owner
        for repo in platform.repos
        if repo.name not in affected and repo.owner != proposer and repo.owner not in exclude
    }
    if not candidates:
        return None
    return sorted(candidates)[0]


@dataclass(frozen=True)
class CritiqueDispatch:
    """A Stage-2 dispatch request envelope, ready for `otaman send`.

    ``type`` is deliberately ``task-assignment`` (a registered bus type) —
    only the critic's *reply* uses the not-yet-registered
    ``spec-proposal-critique-result`` type; the request itself carries no
    registry risk.
    """

    to: str
    change: str
    pass_index: int
    subject: str
    body: str
    type: str = "task-assignment"


def build_critique_dispatch(
    *,
    change: str,
    critic: str,
    pass_index: int,
    proposal_summary: str,
) -> CritiqueDispatch:
    """Build the dispatch envelope for one critique pass.

    Raises :class:`ValueError` if ``pass_index`` is outside the D2 cap
    (1 or 2) — the same bound `otaman_core.spec_gate.record_critic_cost`
    enforces, so a caller can't dispatch a pass it could never bill.
    """
    if pass_index < 1 or pass_index > MAX_PASSES:
        raise ValueError(f"pass_index must be 1..{MAX_PASSES} (D2 cap), got {pass_index}")

    subject = f"spec-critique-request: {change} (pass {pass_index}/{MAX_PASSES})"
    body = (
        f"Run the `{CRITIC_SKILL_ID}` skill against `{change}` "
        f"using `{CONSTITUTION_SKILL_ID}`.\n\n"
        f"This is a FRESH session — you have no context from the proposer "
        f"beyond what follows. Critique pass {pass_index} of a {MAX_PASSES}-pass "
        f"maximum (D2). Your own repo must not appear in this proposal's "
        f"affected_repos — if it does, refuse and report instead of critiquing.\n\n"
        f"## Proposal\n\n{proposal_summary}\n"
    )
    return CritiqueDispatch(
        to=critic,
        change=change,
        pass_index=pass_index,
        subject=subject,
        body=body,
    )


@dataclass(frozen=True)
class CritiqueFinding:
    """One rubric-item result, mirroring the constitution's output shape."""

    item: int
    result: str  # "pass" | "fail" | "comment"
    note: str


@dataclass(frozen=True)
class CritiqueResultMessage:
    """The critic's reply envelope — ``type`` is the spec-mandated value."""

    to: str
    cc: tuple[str, ...]
    subject: str
    body: str
    type: str = CRITIQUE_RESULT_TYPE


def derive_verdict(findings: list[CritiqueFinding]) -> str:
    """Overall verdict from per-item findings, per the constitution's rule."""
    if any(f.result == "fail" for f in findings):
        return "fail"
    if any(f.result == "comment" for f in findings):
        return "has-comments"
    return "pass"


def build_critique_result(
    *,
    change: str,
    proposer: str,
    critic: str,
    pass_index: int,
    constitution_version: str,
    findings: list[CritiqueFinding],
) -> CritiqueResultMessage:
    """Build the `spec-proposal-critique-result` reply envelope (D1, D3).

    Addressed to the proposer (the human queue's approval stays with
    whoever owns that decision) with `spec-agent` CC'd — spec-agent owns
    tasks.md/queue reconciliation and otaman-cli's console surface (1.3)
    reads the attached metadata from there, per D6 (no parallel state
    store; this rides the existing bus + change-file substrate).
    """
    verdict = derive_verdict(findings)
    lines = [
        f"verdict: {verdict}",
        f"critic: {critic!r}",
        f"constitution_version: {constitution_version!r}",
        f"pass_index: {pass_index}",
        "findings:",
    ]
    for f in findings:
        lines.append(f"  - item: {f.item}")
        lines.append(f"    result: {f.result}")
        lines.append(f"    note: {f.note!r}")
    body = "\n".join(lines)
    subject = f"Critique: {change} — {verdict}"
    return CritiqueResultMessage(to=proposer, cc=("spec-agent",), subject=subject, body=body)


def dispatch_critique(
    *,
    platform: PlatformConfig,
    change: str,
    affected_repos: list[str] | tuple[str, ...] | set[str],
    proposer: str,
    lint_result: LintResult,
    proposal_summary: str,
    pass_index: int = 1,
    previous_critics: tuple[str, ...] = (),
) -> CritiqueDispatch | None:
    """Orchestrate one Stage-2 dispatch decision.

    Returns ``None`` (Stage 2 does not run this call) when Stage 1 failed,
    the pass cap is exhausted, or no eligible critic exists — never raises
    for these ordinary "don't run" outcomes (comment-never-block extends to
    the dispatcher itself: an inability to critique is not an error, it's
    Stage 1's result standing alone).
    """
    if not stage1_passed(lint_result):
        return None
    if pass_index > MAX_PASSES:
        return None

    critic = select_critic(
        platform,
        affected_repos,
        proposer=proposer,
        exclude=frozenset(previous_critics),
    )
    if critic is None:
        return None

    return build_critique_dispatch(
        change=change,
        critic=critic,
        pass_index=pass_index,
        proposal_summary=proposal_summary,
    )


__all__ = [
    "CONSTITUTION_SKILL_ID",
    "CRITIC_SKILL_ID",
    "CRITIQUE_RESULT_TYPE",
    "MAX_PASSES",
    "VERDICTS",
    "CritiqueDispatch",
    "CritiqueFinding",
    "CritiqueResultMessage",
    "build_critique_dispatch",
    "build_critique_result",
    "derive_verdict",
    "dispatch_critique",
    "select_critic",
    "stage1_passed",
]
