#!/usr/bin/env python3
"""Resolve launch-time state for the bash launcher and emit shell exports.

The bash launcher (``scripts/launch-agents.sh``) invokes this script with
a connection name, then ``eval``s the stdout to set up its environment.
All YAML parsing stays on the Python side where ``accounts.py``,
``_resolve.py`` and ``_secrets.py`` already handle it.

Usage::

    launch-resolve.py --connection <name> [--shell bash|ssh|zsh|fish]
                      [--otaman-root PATH]      # legacy: --maestro-root alias honored

Outputs (on stdout) shell-safe export statements:

    export MAESTRO_ACTIVE_CONNECTION='lan'
    export MAESTRO_ACTIVE_ACCOUNT='riseapps'
    export MAESTRO_CONNECTION_TYPE='ssh'
    export CLAUDE_CONFIG_DIR='/home/foo/.claude-riseapps'
    export MY_SECRET='val'
    # repos: auth-service,web-app,specs-repo

Status / error messages go to stderr. Exit code:
  0 — success
  1 — user error (unknown connection, missing config)
  2 — internal error

The ``# repos: ...`` comment line is consumed by the bash launcher for
``--list-repos`` output.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML is required. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).parent))

from _models_resolve import resolve_tier  # noqa: E402
from _resolve import expand_config_dir, find_maestro_root  # noqa: E402
from _secrets import load_dotenv  # noqa: E402


def _bash_single_quote(value: str) -> str:
    """Safely wrap a value in single quotes for bash eval."""
    return "'" + value.replace("'", "'\\''") + "'"


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def _resolve_extends(connections: dict[str, Any], name: str, depth: int = 0) -> dict[str, Any]:
    """Resolve an ``extends:`` chain. Child fields override parent."""
    if depth > 10:
        raise ValueError(f"extends: cycle at connection '{name}'")
    if name not in connections:
        raise KeyError(f"Unknown connection: {name}")
    conn = dict(connections[name] or {})
    parent = conn.pop("extends", None)
    if parent:
        base = _resolve_extends(connections, parent, depth + 1)
        base.update(conn)
        return base
    return conn


def resolve(
    maestro_root: Path,
    connection_name: str | None,
    shell: str,
) -> dict[str, Any]:
    """Compute the launch-time state for a connection.

    Returns a dict with keys:
      - connection_name     (str or "")
      - connection_type     (local / ssh / "")
      - account_name        (str or "")
      - config_dir_raw      (unexpanded YAML value)
      - config_dir_expanded (expanded for the target shell)
      - secrets             (dict[str, str])
      - repos               (list[str])
      - warnings            (list[str])
    """
    warnings: list[str] = []

    # launch-settings.yaml
    settings_path = maestro_root / "launch-settings.yaml"
    settings: dict[str, Any] = {}
    if settings_path.exists():
        settings = _load_yaml(settings_path)

    connections = settings.get("connections") or {}
    accounts = settings.get("accounts") or {}
    active_from_file = settings.get("active_connection")

    effective_conn_name = connection_name or active_from_file or ""
    if effective_conn_name and connections and effective_conn_name not in connections:
        warnings.append(f"connection '{effective_conn_name}' not found in launch-settings.yaml")
        effective_conn_name = ""

    conn_resolved: dict[str, Any] = {}
    if effective_conn_name:
        try:
            conn_resolved = _resolve_extends(connections, effective_conn_name)
        except (KeyError, ValueError) as e:
            warnings.append(str(e))

    connection_type = conn_resolved.get("type", "")
    account_name = conn_resolved.get("account", "")

    config_dir_raw = ""
    config_dir_expanded = ""
    if account_name:
        if account_name not in accounts:
            warnings.append(
                f"connection '{effective_conn_name}' references unknown account '{account_name}'"
            )
        else:
            acct = accounts[account_name] or {}
            config_dir_raw = acct.get("config_dir", "") or ""
            if config_dir_raw:
                config_dir_expanded = expand_config_dir(config_dir_raw, shell)

    # platform.yaml for repos list
    platform_path = maestro_root / "platform.yaml"
    repos: list[str] = []
    if platform_path.exists():
        platform = _load_yaml(platform_path)
        for r in platform.get("repos", []) or []:
            if not isinstance(r, dict):
                continue
            if r.get("disabled"):
                continue
            name = r.get("name")
            if name:
                repos.append(name)

    secrets = load_dotenv(maestro_root)

    # Resolve session model/effort from platform.yaml models: block.
    # No repo/agent context available at launch time unless the caller
    # passed it; the launcher can pass --repo / --agent / --model /
    # --effort to refine. Without them, only project default applies.
    tier = resolve_tier(maestro_root)

    return {
        "connection_name": effective_conn_name,
        "connection_type": connection_type,
        "account_name": account_name,
        "config_dir_raw": config_dir_raw,
        "config_dir_expanded": config_dir_expanded,
        "secrets": secrets,
        "repos": repos,
        "warnings": warnings,
        "model": tier.model,
        "effort": tier.effort,
        "model_source": tier.model_source,
        "effort_source": tier.effort_source,
    }


def resolve_for_repo(
    maestro_root: Path,
    *,
    repo: str | None = None,
    agent: str | None = None,
    cli_model: str | None = None,
    cli_effort: str | None = None,
) -> dict[str, str]:
    """Resolve model/effort with (repo, agent) context for a specific session.

    Returns a dict suitable for passing to ``emit_exports_for_tier``.
    Separate from the full ``resolve()`` because most sessions don't need
    the full launch-settings.yaml pipeline — just the model/effort tier.
    """
    tier = resolve_tier(
        maestro_root,
        repo=repo,
        agent=agent,
        cli_model=cli_model,
        cli_effort=cli_effort,
    )
    return tier.to_dict()


def emit_exports(state: dict[str, Any]) -> str:
    """Render the resolve() dict as a block of bash export statements.

    Emits both OTAMAN_* (current) and MAESTRO_* (legacy alias) for each
    routing var so consumers in any phase of the migration find what
    they expect. Consumer chain in ``otaman_core/_resolve.py`` reads
    OTAMAN_* first, falls back to MAESTRO_* — both names point at the
    same value here.
    """
    lines: list[str] = []
    conn = _bash_single_quote(state["connection_name"])
    acct = _bash_single_quote(state["account_name"])
    conn_type = _bash_single_quote(state["connection_type"])
    lines.append(f"export OTAMAN_ACTIVE_CONNECTION={conn}")
    lines.append(f"export OTAMAN_ACTIVE_ROUTING={acct}")
    lines.append(f"export OTAMAN_ACTIVE_ACCOUNT={acct}")
    lines.append(f"export OTAMAN_CONNECTION_TYPE={conn_type}")
    # Legacy aliases — keep until nothing reads them.
    lines.append(f"export MAESTRO_ACTIVE_CONNECTION={conn}")
    lines.append(f"export MAESTRO_ACTIVE_ACCOUNT={acct}")
    lines.append(f"export MAESTRO_CONNECTION_TYPE={conn_type}")
    # Session-default model/effort, if resolved from platform.yaml models:
    # chain. Claude Code picks these up at session start. If unset, Claude
    # Code uses its own default (whatever /model showed at last switch).
    if state.get("model"):
        lines.append(f"export ANTHROPIC_MODEL={_bash_single_quote(state['model'])}")
    if state.get("effort"):
        lines.append(f"export CLAUDE_CODE_EFFORT_LEVEL={_bash_single_quote(state['effort'])}")
    if state["config_dir_expanded"]:
        lines.append(f"export CLAUDE_CONFIG_DIR={_bash_single_quote(state['config_dir_expanded'])}")
    for k, v in state["secrets"].items():
        lines.append(f"export {k}={_bash_single_quote(v)}")
    lines.append(f"# repos: {','.join(state['repos'])}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="launch-resolve.py",
        description="Resolve launch state and emit shell exports",
    )
    parser.add_argument("--connection", help="Connection name from launch-settings.yaml")
    parser.add_argument(
        "--shell",
        default="bash",
        choices=["bash", "zsh", "fish", "powershell", "pwsh", "wsl", "ssh", "cmd"],
        help="Target shell for path expansion (default: bash)",
    )
    # Otaman folder path. `--otaman-root` is the preferred name;
    # `--maestro-root` is retained as a legacy: alias for back-compat with
    # callers that haven't migrated yet (e.g. wrapper scripts vendored
    # outside this repo). Both write to the same argparse dest so the
    # downstream code reads one value.
    parser.add_argument(
        "--otaman-root",
        "--maestro-root",  # legacy: --maestro-root CLI argument
        dest="maestro_root",  # legacy: maestro_root dest name
        metavar="PATH",
        help="Otaman folder path (default: auto-resolve from cwd)",
    )
    # Model/effort resolution inputs — lets the launcher pass per-repo /
    # per-agent context so resolve_tier picks the right rule.
    parser.add_argument(
        "--repo",
        help="Repo name to use when resolving session model (matches platform.yaml repos[].name)",
    )
    parser.add_argument(
        "--agent",
        help="Agent identity to use when resolving session model (overrides repo's owner lookup)",
    )
    parser.add_argument(
        "--model",
        help="Override session model (highest priority; skips resolution chain)",
    )
    parser.add_argument(
        "--effort",
        help="Override session effort level (highest priority)",
    )
    args = parser.parse_args(argv)

    if args.maestro_root:
        root = Path(args.maestro_root).expanduser().resolve()
    else:
        root = find_maestro_root()
        if root is None:
            print(
                "ERROR: no otaman folder found (run from inside a managed repo, "
                "pass --otaman-root, or set OTAMAN_ROOT). "
                "Legacy: --maestro-root / MAESTRO_ROOT still honored.",
                file=sys.stderr,
            )
            return 1

    state = resolve(root, args.connection, args.shell)
    # If the caller passed repo/agent/model/effort context, re-resolve
    # the tier with that context (resolve() defaults to no context).
    if args.repo or args.agent or args.model or args.effort:
        tier = resolve_tier(
            root,
            repo=args.repo,
            agent=args.agent,
            cli_model=args.model,
            cli_effort=args.effort,
        )
        state["model"] = tier.model
        state["effort"] = tier.effort
        state["model_source"] = tier.model_source
        state["effort_source"] = tier.effort_source
    for w in state["warnings"]:
        print(f"warning: {w}", file=sys.stderr)

    sys.stdout.write(emit_exports(state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
