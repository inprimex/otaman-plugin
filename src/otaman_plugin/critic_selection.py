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
    agent_roles: dict[str, tuple[str, ...]] | None = None,
    target_role: str | None = None,
) -> SelectionContext:
    """Assemble the inputs each policy needs from platform config.

    `repo_owners` and the candidate set are the dispatcher's knowledge — core
    cannot derive them, which is why this seam exists rather than core taking a
    platform config it has no business parsing.

    The proposer is handed to CORE, not filtered out here. It used to be
    filtered here, and that was the measured inversion I reported: trimming
    `candidates` only protects `sensitivity-scoped`, because
    `stakeholder-affected` reads `repo_owners`/`affected_repos` and never looks
    at `candidates` at all. So the proposer who owned an affected repo was
    selected to review their own proposal. spec-agent ruled it an invariant OVER
    policies rather than a policy (csp shared-contracts, ruling 20261001), core
    implemented it in #104, and the local filter is now the second home of a
    rule that only ever half-worked here.
    """
    from otaman_core.verification_gates import SelectionContext

    repo_owners = {repo.name: repo.owner for repo in platform.repos if repo.owner}
    candidates = tuple(sorted({owner for owner in repo_owners.values() if owner}))
    kwargs: dict[str, Any] = {
        "candidates": candidates,
        "sensitivity": sensitivity,
        "affected_repos": tuple(affected_repos),
        "repo_owners": repo_owners,
        "consumers": tuple(consumers),
        "agent_roles": dict(agent_roles or {}),
        # None by default (csp 1.7): core resolves `ctx.target_role or
        # hp.target_role`, so leaving it unset lets the hook's configured
        # role win. Setting it here unconditionally would shadow the file.
        "target_role": target_role,
    }
    if proposer is not None and "proposer" in getattr(SelectionContext, "__dataclass_fields__", {}):
        kwargs["proposer"] = proposer
    return SelectionContext(**kwargs)


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


#: The hook name JTBD-57's Stage-2 constitutional critique selects under.
#: `verification-gates.yaml` keys its policies by hook, so the dispatcher has to
#: name which one it is; this is that name.
SPEC_CRITIQUE_HOOK = "spec-proposal-critique"

#: `critic` is None and the reason is one of these. They are distinct on purpose:
#: "no gate config on this tenant", "this hook has no policy", "the installed
#: engine cannot enforce D4" and "the policy selected nobody" are four different
#: situations, and collapsing them into a bare None is what makes a dispatcher
#: that silently stopped look like one that found nothing to do.
NO_CONFIG = "no-config"
HOOK_UNCONFIGURED = "hook-unconfigured"
INVARIANT_UNENFORCEABLE = "invariant-unenforceable"
NO_ELIGIBLE = "no-eligible-critic"

#: core 1.4's fifth state, surfaced rather than folded. A policy that could not
#: be EVALUATED for want of a declared input is not a policy that chose nobody
#: — one is the tenant's config to fix and names what is missing, the other is
#: an answer. Folding them is the conflation the csp ruling exists to end, and
#: this module was one core release away from shipping it.
COULD_NOT_EVALUATE = "could-not-evaluate"

# SPEC_CRITIQUE_ROLE is DELETED (csp 1.7).
#
# It existed for four hours as the workaround for an input core's parse could
# not see: `role-based` read its roles table from config but took
# `target_role` from the caller, so a tenant with a correct
# verification-gates.yaml still got could-not-evaluate on every proposal.
#
# core 1.6 moved it into the file — `target-role:` per hook, resolved inside
# `select_critics` as `ctx.target_role or hp.target_role`, with the parse-time
# refusal extended to a role-based hook that declares neither. So the constant
# is not merely redundant: keeping it would shadow the configured value for
# every caller that routes through here, and a hook misconfigured in the file
# would keep working HERE and nowhere else. Deleted, not defaulted — the
# route_id lesson.
#
# The generalisable half, from spec-agent's ruling: parse-time refusal can
# only guard inputs the parse can SEE, so every input an invariant makes
# load-bearing has to live in config.


def invariant_enforced() -> bool:
    """Whether the INSTALLED engine removes the proposer from a selection (#104).

    Probed on `SelectionResult.excluded_proposer` rather than on a version:
    core records the exclusion as a recorded fact, so the field's presence is
    the engine's own statement that it applies the rule. Attribute-probe
    adoption, the same shape cli used.

    Merged is not installed. This fleet runs deploy-cut bundles that lag main,
    and that gap has bitten four times this week — so the question "is the rule
    canon" and the question "does THIS bundle apply it" have different answers
    and need different checks.
    """
    try:
        from otaman_core.verification_gates import SelectionResult
    except Exception:  # noqa: BLE001 - engine absent entirely -> cannot enforce
        return False
    return "excluded_proposer" in getattr(SelectionResult, "__dataclass_fields__", {})


@dataclass(frozen=True)
class CriticChoice:
    """Who critiques, under which policy — or precisely why nobody does."""

    critic: str | None = None
    policy: str | None = None
    reason: str | None = None
    excluded_proposer: bool = False
    fell_back: bool = False
    dropped_uncleared: tuple[str, ...] = ()
    #: The declared inputs that were missing, when `reason` is
    #: COULD_NOT_EVALUATE. Named, never just counted — "could not evaluate"
    #: without saying what is absent leaves the tenant guessing at their own
    #: config.
    missing_inputs: tuple[str, ...] = ()

    @property
    def selected(self) -> bool:
        return self.critic is not None


def select_critic(
    platform: Any,
    affected_repos: tuple[str, ...] | list[str] | set[str],
    *,
    proposer: str,
    config: VerificationGatesConfig | None = None,
    hook: str = SPEC_CRITIQUE_HOOK,
    exclude: frozenset[str] | set[str] = frozenset(),
    sensitivity: str | None = None,
    agent_roles: dict[str, tuple[str, ...]] | None = None,
    target_role: str | None = None,
) -> CriticChoice:
    """JTBD-57's Stage-2 picker, now resolved through core's declared policies.

    THE MIGRATION, AND WHY IT NEEDED A RULING FIRST. JTBD-57's D4 picked an
    agent whose repo is NOT affected — structural independence. csp 1.2 says
    that picker "migrates onto stakeholder-affected/sensitivity-scoped", and
    `stakeholder-affected` selects exactly the owners of the affected repos.
    Those are opposites: taken literally the migration selects the proposer to
    review their own proposal whenever they own an affected repo, which I
    measured and refused to ship. spec-agent ruled (csp shared-contracts): the
    independence is an INVARIANT OVER policies, not a policy of its own, and
    when exclusion empties a policy's set the fallback applies. core #104
    implements it. With that in place the migration is no longer an inversion,
    so it happens here.

    FAILS CLOSED ON AN ENGINE THAT CANNOT ENFORCE IT. On a bundle predating
    #104, nothing applies the exclusion — `stakeholder-affected` would hand the
    proposal straight back to its author. This returns no critic with
    `INVARIANT_UNENFORCEABLE` rather than dispatching that. Declining to
    dispatch is not blocking the proposal (D1): Stage 1's result still reaches
    the human queue on its own, which is the whole point of
    comment-never-block.

    *exclude* carries prior passes' critics so the D2 two-pass cap does not
    re-ask the same agent; the spec requires only the proposer exclusion, which
    is core's now.
    """
    from otaman_core.verification_gates import VerificationGatesError, select_critics

    if config is None or not config.hooks:
        return CriticChoice(
            reason=NO_CONFIG,
            policy=None,
        )
    if hook not in config.hooks:
        return CriticChoice(reason=HOOK_UNCONFIGURED)
    if not invariant_enforced():
        return CriticChoice(reason=INVARIANT_UNENFORCEABLE)

    ctx = build_context(
        platform,
        affected_repos=tuple(affected_repos),
        proposer=proposer,
        sensitivity=sensitivity,
        agent_roles=agent_roles,
        target_role=target_role,
    )
    try:
        result = select_critics(config, hook, ctx)
    except VerificationGatesError:
        return CriticChoice(reason=HOOK_UNCONFIGURED)

    # NOT re-filtering the proposer here. core #104 did it, this call is gated
    # on an engine that does it, and a local copy "just in case" is a second
    # home that would keep a sabotaged core looking correct. `exclude` IS mine:
    # it carries prior passes' critics for the D2 cap, which core knows nothing
    # about.
    remaining = tuple(c for c in result.critics if c not in exclude)

    # core 1.4: a non-empty `could_not_evaluate` means the policy never ran for
    # want of a declared input, and the tuple NAMES them. Distinct from an
    # empty selection, which is an answer.
    missing = tuple(getattr(result, "could_not_evaluate", ()) or ())
    if remaining:
        reason = None
    elif missing:
        reason = COULD_NOT_EVALUATE
    else:
        reason = NO_ELIGIBLE

    return CriticChoice(
        critic=remaining[0] if remaining else None,
        policy=result.policy,
        reason=reason,
        excluded_proposer=bool(getattr(result, "excluded_proposer", False)),
        fell_back=result.fell_back,
        dropped_uncleared=tuple(result.dropped_uncleared),
        missing_inputs=missing,
    )
