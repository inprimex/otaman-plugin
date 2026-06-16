"""Skill-pack resolution for ``otaman-plugin`` (tech-startup-skill-pack-implementation 2.1-2.4).

A *skill pack* lives outside the plugin's source tree — typically at
``<otaman-meta>/skill-packs/<pack-id>/`` — and ships with a ``pack.yaml``
manifest enumerating every skill plus its access level. ``platform.yaml``
controls activation:

.. code-block:: yaml

    program:
      processes:
        skills:
          profile: tech-startup-cofounder         # selects the pack
          active_skills:                          # optional explicit override
            - tech-startup:pitch-deck-composer
            - tech-startup:market-sizing-analyst

    identity:
      roles:
        cofounder: roman                          # Mode 1 cofounder marker

The resolver:

1. Looks up the pack in :data:`KNOWN_PACKS` (task 2.1).
2. Reads the pack manifest at ``<pack>/pack.yaml`` (task 2.2).
3. Filters by ``active_skills`` if set, else returns every skill in the pack
   (task 2.3).
4. Drops ``access: cofounder-only`` skills when ``identity.roles.cofounder``
   doesn't match the active user (Mode 1 honor-based enforcement per task 2.4).

This is a Mode 1 resolver. Mode 2+ enforcement lives in ``otaman-bridge``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError as exc:  # pragma: no cover — install-time failure
    raise RuntimeError(
        "PyYAML is required to use otaman_plugin.skill_packs"
    ) from exc


# ---------------------------------------------------------------------------
# Pack registry (task 2.1)
# ---------------------------------------------------------------------------
#
# Every known pack is registered here with a callable that returns the
# pack's absolute root path for a given project root. The callable form
# lets us resolve packs that live in sibling repos (e.g. ``otaman-meta``)
# without hardcoding filesystem layout assumptions into the registry data
# itself. To add a new pack: register the ID + locator function below.

PackLocator = "Callable[[Path], Path]"


def _otaman_meta_pack(pack_id: str):
    """Locator factory for packs hosted under ``<otaman-meta>/skill-packs/<id>/``.

    ``project_root`` is the resolved otaman folder (the directory holding
    ``platform.yaml``). Per `tech-startup-skill-pack-implementation`
    proposal §2 this is the canonical location for skill packs because
    otaman-meta is already a per-program writable repo.
    """
    def locate(project_root: Path) -> Path:
        return project_root / "skill-packs" / pack_id

    return locate


# Registry: pack_id → locator function
KNOWN_PACKS: dict[str, Any] = {
    "tech-startup": _otaman_meta_pack("tech-startup"),
}


# ---------------------------------------------------------------------------
# Profile → pack mapping
# ---------------------------------------------------------------------------
#
# A profile names a curated selection on top of a pack — e.g. the
# "tech-startup-cofounder" profile activates the tech-startup pack with
# every skill available subject to the access filter. Future profiles may
# layer on top of the same pack (e.g. "tech-startup-public" that excludes
# cofounder-only skills regardless of identity).
#
# For v1 we only ship the cofounder profile.

_PROFILE_TO_PACK: dict[str, str] = {
    "tech-startup-cofounder": "tech-startup",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SkillRef:
    """A resolved skill reference. Returned by the resolver."""

    id: str
    """Fully-qualified skill identifier — e.g. ``tech-startup:pitch-deck-composer``."""

    file: Path
    """Absolute path to the skill markdown file under the pack root."""

    access: str
    """Access level recorded in the pack manifest — typically ``public`` or
    ``cofounder-only``. Carried through so callers can audit decisions."""


@dataclass(frozen=True)
class ResolveResult:
    """Outcome of a resolution call.

    ``skills`` is the activated set, post-filtering. ``skipped`` records
    the skills that were dropped along with the reason — useful for
    diagnostics and for the CLI confirmation screen (task 4.x in
    otaman-cli) that surfaces why a skill didn't activate.
    """

    skills: list[SkillRef]
    skipped: list[tuple[SkillRef, str]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_yaml(path: Path) -> Mapping[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_pack_root(pack_id: str, project_root: Path) -> Path | None:
    """Return the pack's absolute root path or ``None`` if the pack ID is
    not known to this plugin build.

    Callers should treat ``None`` as a hard error (the platform.yaml
    declared a pack the plugin has never heard of) and ``a path that
    doesn't exist on disk`` as a soft error (the pack is known but its
    files are missing — e.g. otaman-meta wasn't cloned yet).
    """
    locator = KNOWN_PACKS.get(pack_id)
    if locator is None:
        return None
    return locator(project_root)


def load_pack_manifest(pack_root: Path) -> Mapping[str, Any]:
    """Read ``<pack_root>/pack.yaml`` and return its parsed mapping."""
    manifest = pack_root / "pack.yaml"
    if not manifest.is_file():
        return {}
    return _read_yaml(manifest)


def _iter_pack_skills(
    pack_root: Path, manifest: Mapping[str, Any]
) -> Iterable[SkillRef]:
    for entry in manifest.get("skills") or []:
        if not isinstance(entry, Mapping):
            continue
        skill_id = entry.get("id")
        file_rel = entry.get("file")
        access = entry.get("access", "public")
        if not skill_id or not file_rel:
            continue
        yield SkillRef(
            id=str(skill_id),
            file=(pack_root / str(file_rel)).resolve(),
            access=str(access),
        )


def _cofounder_username(platform: Mapping[str, Any]) -> str | None:
    """Extract the configured cofounder username from ``platform.yaml``."""
    identity = platform.get("identity") or {}
    if not isinstance(identity, Mapping):
        return None
    roles = identity.get("roles") or {}
    if not isinstance(roles, Mapping):
        return None
    val = roles.get("cofounder")
    if val is None:
        return None
    return str(val).strip() or None


def _normalize_active_skills(active_skills: Any) -> set[str]:
    if not isinstance(active_skills, list):
        return set()
    return {str(s).strip() for s in active_skills if isinstance(s, str) and s.strip()}


# ---------------------------------------------------------------------------
# Main resolver (tasks 2.2 + 2.3 + 2.4)
# ---------------------------------------------------------------------------

def resolve_active_skills(
    platform: Mapping[str, Any],
    project_root: Path,
    active_user: str | None = None,
) -> ResolveResult:
    """Resolve the activated skill set for the current session.

    Arguments:
        platform: parsed ``platform.yaml`` mapping
        project_root: directory containing the otaman folder (typically
            the directory holding ``platform.yaml``)
        active_user: the username of the human / agent driving this session.
            Mode 1 cofounder-only check matches this against
            ``platform.yaml`` ``identity.roles.cofounder``. Pass ``None``
            when the caller has no notion of an active user — every
            ``cofounder-only`` skill is then skipped.

    Returns a :class:`ResolveResult` with the post-filter skill set and
    the per-skill skip reasons.
    """
    skills_cfg = (
        ((platform.get("program") or {}).get("processes") or {}).get("skills") or {}
    )
    if not isinstance(skills_cfg, Mapping):
        return ResolveResult(skills=[], skipped=[])

    profile = skills_cfg.get("profile")
    pack_id: str | None = None
    if isinstance(profile, str):
        pack_id = _PROFILE_TO_PACK.get(profile.strip())

    # No recognised profile → nothing to load. Callers that want raw
    # pack access without a profile should add an entry to
    # ``_PROFILE_TO_PACK`` or invoke the lower-level pack helpers directly.
    if not pack_id:
        return ResolveResult(skills=[], skipped=[])

    pack_root = resolve_pack_root(pack_id, project_root)
    if pack_root is None:
        return ResolveResult(skills=[], skipped=[])

    manifest = load_pack_manifest(pack_root)
    if not manifest:
        return ResolveResult(skills=[], skipped=[])

    active_set = _normalize_active_skills(skills_cfg.get("active_skills"))
    cofounder = _cofounder_username(platform)

    activated: list[SkillRef] = []
    skipped: list[tuple[SkillRef, str]] = []

    for skill in _iter_pack_skills(pack_root, manifest):
        # active_skills explicit override (task 2.3): when set, drop any
        # skill not named in the list. Empty list (`active_skills: []`)
        # opts the user out of every skill while still surfacing them in
        # `skipped` for diagnostics.
        if active_set and skill.id not in active_set:
            skipped.append((skill, "not in active_skills"))
            continue

        # Mode 1 cofounder enforcement (task 2.4). The pack-level
        # `access` value is the gate; the per-session `active_user` is
        # compared to the program-level `identity.roles.cofounder`
        # honor-marker. Mode 2+ replaces this with a bridge-side token
        # check (see otaman-bridge tasks 3.x).
        if skill.access == "cofounder-only":
            if not active_user or not cofounder or active_user != cofounder:
                skipped.append((skill, "cofounder-only — active user is not the cofounder"))
                continue

        activated.append(skill)

    return ResolveResult(skills=activated, skipped=skipped)
