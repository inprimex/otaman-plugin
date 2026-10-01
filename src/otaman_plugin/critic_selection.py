"""Critic selection at the dispatch seam (critic-selection-policy 1.2).

core #97 owns the POLICIES (`otaman_core.verification_gates.select_critics`)
and the clearance gate. This module owns what only the dispatcher knows: how to
build a `SelectionContext` from platform config, and how to compose the
cofounder 4-layer stack from the policies core provides.

NOTHING HERE RE-IMPLEMENTS A POLICY. JTBD-57's `select_critic` picked a critic
by its own rule — repo owner, not the proposer, not affected. That rule is now
one of four named policies with a clearance gate in front of it, and keeping a
local copy would be the two-implementations drift this fleet has paid for
repeatedly today. `select_critic` delegates.

NOT-RUN IS A RENDERED LAYER, NOT AN ABSENCE. A stack layer that could not run
has to say so and say why — a four-layer review showing three layers reads as
a four-layer review that found nothing in the fourth. core's
`dropped_uncleared` carries exactly the agents a sensitivity gate removed, and
that is the reason text the layer renders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from otaman_core.verification_gates import SelectionContext, VerificationGatesConfig

#: The cofounder stack, outermost-last. Deterministic checks are free and
#: always run; the human is the last resort, never the first.
STACK_LAYERS: tuple[str, ...] = (
    "deterministic",
    "self-critique",
    "cleared-peer",
    "human",
)

RAN = "ran"
NOT_RUN = "not-run"


@dataclass(frozen=True)
class LayerOutcome:
    """One stack layer: whether it ran, who ran it, and if not — why not."""

    layer: str
    state: str
    critics: tuple[str, ...] = ()
    reason: str = ""

    @property
    def ran(self) -> bool:
        return self.state == RAN


@dataclass(frozen=True)
class StackResult:
    """The assembled cofounder stack, plus the policy that chose the peer.

    `policy` is recorded because every core selection names the policy that
    fired, and a gate result that does not say which rule selected its critic
    cannot be audited later.
    """

    layers: tuple[LayerOutcome, ...]
    policy: str | None = None
    dropped_uncleared: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ran_layers(self) -> tuple[str, ...]:
        return tuple(la.layer for la in self.layers if la.ran)

    @property
    def complete(self) -> bool:
        """Did every layer run? A stack with a not-run layer is NOT complete,
        and callers must not present it as a full review."""
        return all(la.ran for la in self.layers)


def build_context(
    platform: Any,
    *,
    affected_repos: tuple[str, ...] = (),
    proposer: str | None = None,
    sensitivity: str | None = None,
    consumers: tuple[str, ...] = (),
    agent_roles: dict[str, str] | None = None,
    target_role: str | None = None,
) -> SelectionContext:
    """Assemble the inputs each policy needs from platform config.

    `repo_owners` and the candidate set are the dispatcher's knowledge — core
    cannot derive them, which is why this seam exists rather than core taking a
    platform config it has no business parsing.

    The proposer is excluded from candidates here rather than inside a policy:
    structural independence is a property of the DISPATCH (who may review this
    proposal), not of any one selection rule, and every policy needs it.
    """
    from otaman_core.verification_gates import SelectionContext

    repo_owners = {repo.name: repo.owner for repo in platform.repos if repo.owner}
    candidates = tuple(
        sorted({owner for owner in repo_owners.values() if owner and owner != proposer})
    )
    return SelectionContext(
        candidates=candidates,
        sensitivity=sensitivity,
        affected_repos=tuple(affected_repos),
        repo_owners=repo_owners,
        consumers=tuple(consumers),
        agent_roles=dict(agent_roles or {}),
        target_role=target_role,
    )


def cofounder_stack(
    config: VerificationGatesConfig,
    ctx: SelectionContext,
    *,
    hook: str,
    self_critique_agent: str | None = None,
    human: str = "human",
) -> StackResult:
    """The 4-layer cofounder stack, with every layer accounted for.

    core supplies the policies and the clearance gate; the composition is this
    module's. Each layer renders RAN or NOT-RUN with a reason — never silence,
    because a stack that simply omits a layer looks like a stack that passed it.
    """
    from otaman_core.verification_gates import VerificationGatesError, select_critics

    layers: list[LayerOutcome] = []
    policy: str | None = None
    dropped: tuple[str, ...] = ()

    # 1. Deterministic — always available, costs nothing, needs no selection.
    layers.append(LayerOutcome("deterministic", RAN, reason="deterministic checks need no critic"))

    # 2. Self-critique — the proposing agent re-reads its own work.
    if self_critique_agent:
        layers.append(LayerOutcome("self-critique", RAN, critics=(self_critique_agent,)))
    else:
        layers.append(
            LayerOutcome(
                "self-critique",
                NOT_RUN,
                reason="no proposing agent named, so there is nobody to self-critique",
            )
        )

    # 3. Cleared peer — core selects, and the clearance gate may remove every
    #    candidate. That is the case this layer exists to render honestly.
    try:
        result = select_critics(config, hook, ctx)
    except VerificationGatesError as exc:
        layers.append(LayerOutcome("cleared-peer", NOT_RUN, reason=f"selection refused: {exc}"))
    else:
        policy = result.policy
        dropped = tuple(result.dropped_uncleared)
        if result.critics:
            layers.append(LayerOutcome("cleared-peer", RAN, critics=tuple(result.critics)))
        else:
            # Name WHO was dropped and why. "No peer available" sends the
            # reader hunting; "dropped for missing clearance: x, y" does not.
            reason = (
                "every candidate lacks clearance for sensitivity "
                f"{ctx.sensitivity!r}: {', '.join(dropped)}"
                if dropped
                else "no eligible peer for this hook"
            )
            layers.append(LayerOutcome("cleared-peer", NOT_RUN, reason=reason))

    # 4. Human — the last resort. Always reachable, so always RAN as a layer:
    #    its availability is the point, not whether a human has yet looked.
    layers.append(LayerOutcome("human", RAN, critics=(human,)))

    return StackResult(layers=tuple(layers), policy=policy, dropped_uncleared=dropped)


# JTBD-57's `select_critic` is NOT migrated here, deliberately.
#
# csp 1.2 says the picker "migrates onto stakeholder-affected/sensitivity-
# scoped". Doing that literally inverts D4. `stakeholder-affected` selects "one
# critic per owner of each affected repo" — by design, so every repo a change
# touches gets its owner as a reviewer. JTBD-57's D4 selects an owner whose
# repo is NOT affected, for structural independence. They are opposites.
#
# Measured, not reasoned about: with repos a/b, proposer a-agent, affected
# ("a",) — the local D4 rule picks b-agent; stakeholder-affected picks
# a-agent. The proposer reviews its own proposal.
#
# So the migration as written would retire D4's independence property. That may
# be intended — adversarial diversity from stakeholders is a coherent choice —
# but it is a contract change to JTBD-57, not a refactor, and it is not mine to
# make silently. Raised with spec-agent/core; the picker stays in
# spec_critique_dispatch.py until it is ruled on.
