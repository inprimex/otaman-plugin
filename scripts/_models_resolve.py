"""Resolve the effective model + effort tier for a session.

Walks a priority chain over platform.yaml's ``models:`` block to pick
the right tier for a given (repo, agent) pair. Used by the launcher to
inject ``ANTHROPIC_MODEL`` / ``CLAUDE_CODE_EFFORT_LEVEL`` into the
spawned Claude session, and by ``otaman models show`` to explain
which rule applied.

Resolution chain (first non-empty wins, model and effort resolved
independently):

    1. Explicit caller override  (CLI --model / --effort)
    2. Per-repo       models.by_repo.<repo>.{model, effort}
    3. Per-agent      models.by_agent.<agent>.{model, effort}
       (agent can be the repo's owner from platform.yaml repos[].owner,
       or the active .agents/current-agent, whichever the caller passes)
    4. Project default  models.default, models.default_effort
    5. None (launcher leaves env unset; Claude Code's own default applies)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Human-readable tier names → Claude Code CLI model aliases.
# Claude Code's /model accepts these aliases, and Anthropic's API
# accepts the same names for current models. These ARE stable: what
# changes over time is which specific version "opus"/"sonnet"/"haiku"
# resolves to — Claude Code handles that internally.
VALID_MODEL_ALIASES = frozenset({"opus", "sonnet", "haiku", "inherit"})
VALID_EFFORT_LEVELS = frozenset({"low", "medium", "high", "xhigh", "max", "inherit"})


@dataclass
class ModelResolution:
    """Result of resolving (model, effort) for a session, with provenance."""

    model: str = ""        # empty = not set; caller should leave env unset
    effort: str = ""
    model_source: str = ""  # "cli" | "by_repo" | "by_agent" | "default" | ""
    effort_source: str = ""

    def is_empty(self) -> bool:
        return not self.model and not self.effort

    def to_dict(self) -> dict[str, str]:
        return {
            "model": self.model,
            "effort": self.effort,
            "model_source": self.model_source,
            "effort_source": self.effort_source,
        }


def _validate(tier: str, valid: frozenset[str], field: str) -> str:
    """Return ``tier`` if it's one of the valid values, else empty string.

    Invalid values are silently dropped rather than raising, because this
    function runs at launch time and the user should not be blocked by a
    typo in platform.yaml. ``otaman models show`` warns about invalid
    values separately.
    """
    if not tier:
        return ""
    norm = str(tier).strip().lower()
    if norm in valid:
        return norm
    return ""


def _read_models_from_yaml(path: Path) -> dict[str, Any]:
    """Read the ``models:`` block from a single YAML file. Empty if missing."""
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    models = data.get("models")
    if not isinstance(models, dict):
        return {}
    return models


def _merge_models(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge two ``models:`` blocks, overlay winning per key.

    Top-level keys (``default``, ``default_effort``, etc.) are
    overlay-wins. ``by_repo`` and ``by_agent`` deep-merge per entry:
    if both define the same repo/agent, the overlay's fields overlay
    the base's — letting platform.yaml set a default model while
    launch-settings.yaml refines just the effort, for example.
    """
    out: dict[str, Any] = dict(base)
    for k, v in overlay.items():
        if k in ("by_repo", "by_agent") and isinstance(v, dict):
            merged = dict(out.get(k) or {})
            if not isinstance(merged, dict):
                merged = {}
            for name, cfg in v.items():
                if isinstance(cfg, dict) and isinstance(merged.get(name), dict):
                    entry = dict(merged[name])
                    entry.update(cfg)
                    merged[name] = entry
                else:
                    merged[name] = cfg
            out[k] = merged
        else:
            out[k] = v
    return out


def _load_models_block(maestro_root_or_file: Path) -> dict[str, Any]:  # legacy: maestro_root param name
    """Load merged models config from the otaman root or a single file.

    If ``maestro_root_or_file`` is a directory, reads both:
      - ``<root>/platform.yaml``     (project-global, lower priority)
      - ``<root>/launch-settings.yaml`` (launcher-local, higher priority)
    and deep-merges. This lets launcher-only configs (common when the
    otaman folder lives on a remote host and the launcher runs on
    Windows) define model routing without round-tripping the remote.

    If ``maestro_root_or_file`` is a file path, reads that file only.
    """
    if maestro_root_or_file.is_file():
        return _read_models_from_yaml(maestro_root_or_file)

    # Directory case: merge platform.yaml (base) + launch-settings.yaml (overlay)
    platform_models = _read_models_from_yaml(
        maestro_root_or_file / "platform.yaml"
    )
    launch_models = _read_models_from_yaml(
        maestro_root_or_file / "launch-settings.yaml"
    )
    return _merge_models(platform_models, launch_models)


def _repos_to_owner(platform_yaml: Path) -> dict[str, str]:
    """Map repo-name → owning agent (from platform.yaml repos[].owner)."""
    if not platform_yaml.is_file():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(platform_yaml.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    out: dict[str, str] = {}
    for r in data.get("repos") or []:
        if isinstance(r, dict):
            name = r.get("name")
            owner = r.get("owner")
            if name and owner:
                out[str(name)] = str(owner)
    return out


def resolve_tier(
    maestro_root: Path,
    *,
    repo: str | None = None,
    agent: str | None = None,
    cli_model: str | None = None,
    cli_effort: str | None = None,
) -> ModelResolution:
    """Walk the resolution chain and return the effective (model, effort).

    Args:
        maestro_root: path to the otaman folder (contains platform.yaml).  # legacy: maestro_root param name
        repo: active repo name (matches a platform.yaml repos[].name).
        agent: current agent identity. If not given but ``repo`` is, the
            repo's owner is used as the lookup agent.
        cli_model, cli_effort: explicit overrides from the caller (launcher
            --model flag, etc). These always win.
    """
    # Resolve from both platform.yaml AND launch-settings.yaml in the
    # otaman root. launch-settings.yaml wins when present — it's the
    # launcher-local source, right next to connections/accounts.
    models = _load_models_block(maestro_root)
    platform_yaml = maestro_root / "platform.yaml"
    resolved = ModelResolution()

    # 1. CLI override (highest priority)
    m = _validate(cli_model or "", VALID_MODEL_ALIASES, "model")
    if m and m != "inherit":
        resolved.model = m
        resolved.model_source = "cli"
    e = _validate(cli_effort or "", VALID_EFFORT_LEVELS, "effort")
    if e and e != "inherit":
        resolved.effort = e
        resolved.effort_source = "cli"

    # Determine agent identity if repo is given but agent isn't
    if agent is None and repo:
        owner_map = _repos_to_owner(platform_yaml)
        agent = owner_map.get(repo)

    # 2. Per-repo
    by_repo = models.get("by_repo") or {}
    if repo and isinstance(by_repo, dict):
        cfg = by_repo.get(repo) or {}
        if isinstance(cfg, dict):
            if not resolved.model:
                m = _validate(cfg.get("model") or "", VALID_MODEL_ALIASES, "model")
                if m and m != "inherit":
                    resolved.model = m
                    resolved.model_source = "by_repo"
            if not resolved.effort:
                e = _validate(cfg.get("effort") or "", VALID_EFFORT_LEVELS, "effort")
                if e and e != "inherit":
                    resolved.effort = e
                    resolved.effort_source = "by_repo"

    # 3. Per-agent
    by_agent = models.get("by_agent") or {}
    if agent and isinstance(by_agent, dict):
        cfg = by_agent.get(agent) or {}
        if isinstance(cfg, dict):
            if not resolved.model:
                m = _validate(cfg.get("model") or "", VALID_MODEL_ALIASES, "model")
                if m and m != "inherit":
                    resolved.model = m
                    resolved.model_source = "by_agent"
            if not resolved.effort:
                e = _validate(cfg.get("effort") or "", VALID_EFFORT_LEVELS, "effort")
                if e and e != "inherit":
                    resolved.effort = e
                    resolved.effort_source = "by_agent"

    # 4. Project default
    if not resolved.model:
        m = _validate(models.get("default") or "", VALID_MODEL_ALIASES, "model")
        if m and m != "inherit":
            resolved.model = m
            resolved.model_source = "default"
    if not resolved.effort:
        e = _validate(models.get("default_effort") or "", VALID_EFFORT_LEVELS, "effort")
        if e and e != "inherit":
            resolved.effort = e
            resolved.effort_source = "default"

    return resolved


def explain_chain(
    maestro_root: Path,
    *,
    repo: str | None = None,
    agent: str | None = None,
    cli_model: str | None = None,
    cli_effort: str | None = None,
) -> list[str]:
    """Return human-readable lines explaining which rule fired.

    Used by ``otaman models show`` to make the resolution transparent.
    """
    resolved = resolve_tier(
        maestro_root,
        repo=repo, agent=agent,
        cli_model=cli_model, cli_effort=cli_effort,
    )
    platform_yaml = maestro_root / "platform.yaml"
    # Resolve from both files (same as resolve_tier) so the explanation
    # reflects what actually drove the decision.
    models = _load_models_block(maestro_root)

    lines = [
        f"Resolution chain for repo={repo or '-'} agent={agent or '-'}:",
    ]

    def _line(rank: int, label: str, found: str, using: bool) -> str:
        marker = "->" if using else "  "
        return f"  {marker} {rank}. {label}: {found or '(unset)'}"

    # 1. CLI
    cli_desc = []
    if cli_model:
        cli_desc.append(f"--model={cli_model}")
    if cli_effort:
        cli_desc.append(f"--effort={cli_effort}")
    lines.append(_line(
        1, "CLI override",
        " ".join(cli_desc) if cli_desc else "",
        resolved.model_source == "cli" or resolved.effort_source == "cli",
    ))

    # 2. by_repo
    by_repo_cfg = (models.get("by_repo") or {}).get(repo or "") or {}
    lines.append(_line(
        2, f"by_repo[{repo or '-'}]",
        f"model={by_repo_cfg.get('model', '')} effort={by_repo_cfg.get('effort', '')}" if by_repo_cfg else "",
        resolved.model_source == "by_repo" or resolved.effort_source == "by_repo",
    ))

    # 3. by_agent
    resolved_agent = agent
    if resolved_agent is None and repo:
        resolved_agent = _repos_to_owner(platform_yaml).get(repo)
    by_agent_cfg = (models.get("by_agent") or {}).get(resolved_agent or "") or {}
    lines.append(_line(
        3, f"by_agent[{resolved_agent or '-'}]",
        f"model={by_agent_cfg.get('model', '')} effort={by_agent_cfg.get('effort', '')}" if by_agent_cfg else "",
        resolved.model_source == "by_agent" or resolved.effort_source == "by_agent",
    ))

    # 4. default
    lines.append(_line(
        4, "project default",
        f"model={models.get('default', '')} effort={models.get('default_effort', '')}",
        resolved.model_source == "default" or resolved.effort_source == "default",
    ))

    lines.append("")
    lines.append(
        f"Effective: model={resolved.model or '(inherit)'} "
        f"({resolved.model_source or 'none'}), "
        f"effort={resolved.effort or '(inherit)'} "
        f"({resolved.effort_source or 'none'})"
    )
    return lines
