"""Cross-program send resolution — VENDORED PORT of ``otaman_cli.bus_target``.

Source of truth: ``otaman-cli/src/otaman_cli/bus_target.py`` (single-bus-
per-program tasks 2.1-2.3). bus_server.py imports otaman-cli's copy when
that package is present in the runtime env and falls back to this port
(CI checks out only the otaman-core sibling). Manual-sync chore, same as
the cc_fanout parity precedent, until the planned otaman-core extraction —
do not diverge here; port fixes wholesale.

Consumes ``otaman_core.bus.uri`` (the pure addressing layer, task 1.1) and
adds the filesystem half: local-context derivation, target-program root
resolution via the DECLARED org layout, and fail-closed enforcement of
the target's ``bus.boundaries``. The P1 split-brain lesson governs
everything here: resolution interprets the declared layout (``orgs/<org>/
programs/<program>/<meta-dir>``, org config ``programs:`` overrides, the
``<program>-otaman`` convention) and NEVER walks up or scans for
``.agents`` roots. A target that cannot be resolved from declarations is
refused with guidance, not discovered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Same slug grammar as otaman_core.bus.uri segments / platform-schema
# owner names. Kept local rather than importing core's private _SEGMENT.
_SEGMENT = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


class TargetResolutionError(Exception):
    """Raised when a cross-program target cannot be resolved from the declared layout."""


class BoundaryError(Exception):
    """Raised when the target program's ``bus.boundaries`` refuse the sender."""


class CrossOrgError(Exception):
    """Raised for targets in a foreign org — transport does not exist yet."""


@dataclass(frozen=True)
class LocalContext:
    """The sending program's position in the declared org layout."""

    org: str
    program: str
    program_root: Path  # the program meta dir (holds platform.yaml + .agents)
    org_root: Path  # orgs/<org>


def derive_local_context(program_root: Path) -> LocalContext | None:
    """Interpret *program_root* against the declared CE layout.

    ``program_root`` is the already-resolved project root (the program meta
    dir). Under the ce-directory-layout it sits at
    ``orgs/<org>/programs/<program>/<meta-dir>`` — positional
    interpretation of that declared structure, not discovery. Returns None
    when the tree does not conform (legacy layouts): bare-name sends then
    keep their exact legacy behavior and cross-program forms are refused.
    """
    try:
        resolved = program_root.resolve()
    except OSError:
        return None
    program_dir = resolved.parent
    programs_dir = program_dir.parent
    org_dir = programs_dir.parent
    if programs_dir.name != "programs" or org_dir.parent.name != "orgs":
        return None
    org = org_dir.name
    program = program_dir.name
    if not (_SEGMENT.match(org) and _SEGMENT.match(program)):
        return None
    return LocalContext(org=org, program=program, program_root=resolved, org_root=org_dir)


def _declared_program_roots(org_root: Path) -> list[Path]:
    """Read the org config's ``programs:`` list (declared meta-dir paths).

    Source: ``orgs/<org>/config/launch-settings.yaml`` — the org-scope
    config file ce-bootstrap scaffolds. Missing file / missing key / bad
    YAML all mean "nothing declared" (the conventional name still applies).
    """
    cfg = org_root / "config" / "launch-settings.yaml"
    if not cfg.is_file():
        return []
    try:
        import yaml

        doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    if not isinstance(doc, dict):
        return []
    raw = doc.get("programs") or []
    if not isinstance(raw, list):
        return []
    return [Path(p).expanduser() for p in raw if isinstance(p, str) and p.strip()]


def resolve_target_program_root(ctx: LocalContext, target_program: str) -> Path:
    """Resolve the TARGET program's meta dir from declarations only.

    Order (ce-directory-layout resolution rule):
      1. an entry in the org config ``programs:`` list whose parent
         directory is ``programs/<target-program>`` (this is how
         ``program_meta_dir`` overrides are declared);
      2. the conventional ``programs/<target-program>/<target-program>-otaman``.

    Anything else raises :class:`TargetResolutionError` — no walk-up, no
    scanning for ``.agents`` directories.
    """
    for declared in _declared_program_roots(ctx.org_root):
        if declared.parent.name == target_program and declared.is_dir():
            return declared

    conventional = ctx.org_root / "programs" / target_program / f"{target_program}-otaman"
    if conventional.is_dir():
        return conventional

    raise TargetResolutionError(
        f"cannot resolve program '{target_program}' in org '{ctx.org}': no entry in "
        f"{ctx.org_root / 'config' / 'launch-settings.yaml'} programs: list and no "
        f"conventional {conventional} directory. Declare the program's meta dir in the "
        "org config, or create the conventional folder."
    )


def check_boundaries(
    target_root: Path,
    *,
    sender_program: str,
    sender_agent: str,
    msg_type: str,
    target_program: str,
) -> None:
    """Enforce the TARGET program's ``bus.boundaries`` — fail closed.

    A grant matches when its ``program`` equals the sender's program and,
    where narrowed, its ``agents`` list contains the sender and its
    ``types`` list contains the message type. Absent config, absent
    section, or no matching grant → :class:`BoundaryError` naming exactly
    what is missing (the receiving side owns its front door; the error
    tells the operator what grant to add THERE).
    """
    platform = target_root / "platform.yaml"
    grant_hint = (
        f"bus:\n  boundaries:\n    allow_from:\n      - program: {sender_program}"
        f"\n        agents: [{sender_agent}]"
    )
    try:
        import yaml

        doc = yaml.safe_load(platform.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise BoundaryError(
            f"cannot read {platform} to verify bus.boundaries ({exc}); refusing cross-program send"
        ) from exc
    except Exception as exc:
        raise BoundaryError(
            f"{platform} is not valid YAML ({exc}); refusing cross-program send"
        ) from exc

    boundaries = (doc.get("bus") or {}).get("boundaries") if isinstance(doc, dict) else None
    allow_from = (boundaries or {}).get("allow_from") if isinstance(boundaries, dict) else None
    if not isinstance(allow_from, list) or not allow_from:
        raise BoundaryError(
            f"program '{target_program}' declares no bus.boundaries.allow_from grant — "
            f"cross-program ingress is closed by default. Ask its owner to add to "
            f"{platform}:\n{grant_hint}"
        )

    program_granted = False
    for grant in allow_from:
        if not isinstance(grant, dict) or grant.get("program") != sender_program:
            continue
        program_granted = True
        agents = grant.get("agents")
        if isinstance(agents, list) and sender_agent not in agents:
            continue
        types = grant.get("types")
        if isinstance(types, list) and msg_type not in types:
            continue
        return  # matched

    if program_granted:
        raise BoundaryError(
            f"program '{target_program}' grants program '{sender_program}' but not this "
            f"send: agent '{sender_agent}' / type '{msg_type}' fall outside the grant's "
            f"agents/types narrowing in {platform}"
        )
    raise BoundaryError(
        f"program '{target_program}' has no bus.boundaries.allow_from grant for program "
        f"'{sender_program}'. Ask its owner to add to {platform}:\n{grant_hint}"
    )


def resolve_cross_program_delivery(
    ctx: LocalContext,
    *,
    target_program: str,
    target_org: str,
    sender_agent: str,
    msg_type: str,
) -> Path:
    """Full 2.2/2.3 gate: cross-org rejection → root resolution → boundaries.

    Returns the target program's meta root on success; raises
    :class:`CrossOrgError` / :class:`TargetResolutionError` /
    :class:`BoundaryError` otherwise.
    """
    if target_org != ctx.org:
        raise CrossOrgError(
            f"cross-org routing not yet implemented: target org '{target_org}' differs "
            f"from local org '{ctx.org}' (ADR-012 Phase 5+ transport required)"
        )
    target_root = resolve_target_program_root(ctx, target_program)
    check_boundaries(
        target_root,
        sender_program=ctx.program,
        sender_agent=sender_agent,
        msg_type=msg_type,
        target_program=target_program,
    )
    return target_root


def envelope_uri_fields(ctx: LocalContext, *, sender_agent: str, to_uri: Any) -> dict[str, str]:
    """The schema-v2 projection fields for the frontmatter.

    ``from``/``to`` keep the bare-name convention every existing consumer
    (check, ack, bridge, fswatch) keys on; the canonical URIs travel in
    ``from-uri``/``to-uri`` and ``from_org``/``to_org`` are their org
    projections per the inter-org-envelope spec.
    """
    from_uri = f"otaman://{ctx.org}/{ctx.program}/{sender_agent}"
    return {
        "from-uri": from_uri,
        "to-uri": str(to_uri),
        "from_org": ctx.org,
        "to_org": to_uri.org,
    }


__all__ = [
    "BoundaryError",
    "CrossOrgError",
    "LocalContext",
    "TargetResolutionError",
    "check_boundaries",
    "derive_local_context",
    "envelope_uri_fields",
    "resolve_cross_program_delivery",
    "resolve_target_program_root",
]
