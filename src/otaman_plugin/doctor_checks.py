"""Doctor checks contributed by otaman-plugin.

These functions are called by ``otaman doctor`` (otaman-cli, task 3.4 of
the ``finish-maestro-to-otaman-migration`` spec change — migration: spec
name retained as-shipped). The plugin owns the *check logic*; the CLI
owns dispatch + rendering.

API contract:

    from otaman_plugin.doctor_checks import run_all_checks
    warnings: list[DoctorWarning] = run_all_checks(otaman_root)

Each warning carries a stable ``code`` (e.g. ``M4_PLUGIN_DIR_DRIFT``) so the
CLI can format / filter / suppress per code if desired.

Implements:

* **M-4** ``check_plugin_dir_consistency`` — warns when ``platform.yaml`` per-repo
  ``launch_commands`` disagrees with ``launch-settings.yaml`` ``ssh_plugin_path``
  on ``--plugin-dir``; also warns when ``launch_commands`` reference WSL paths
  (``/mnt/c/...``) under an SSH connection (likely typo for a remote path).

* **M-13b** ``check_launch_commands_have_continue_flag`` — warns when per-repo
  ``launch_commands`` invoke ``claude`` without ``-c`` / ``--continue`` /
  ``--resume``. The launcher's rewrite logic adds ``-c`` for SSH-rebuild paths,
  but the tmux-wrap path consumes ``launch_commands`` verbatim — drift there
  bypasses the rewrite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    import yaml
except ImportError as exc:
    raise ImportError(
        "doctor_checks requires PyYAML; install with: pip install pyyaml"
    ) from exc


Severity = Literal["info", "warn", "error"]


@dataclass(frozen=True)
class DoctorWarning:
    """One observation surfaced by a plugin-side doctor check.

    Fields:
        severity: ``info`` (notable but not actionable), ``warn`` (drift / latent
            bug), or ``error`` (definite misconfiguration).
        code: Stable identifier the CLI can filter / suppress on. Format:
            ``<TICKET>_<SHORT_NAME>`` (e.g. ``M4_PLUGIN_DIR_DRIFT``).
        message: Human-readable description of the finding.
        repo: Repo name from ``platform.yaml`` this finding is about, if any.
        hint: Optional one-line suggested action.
    """
    severity: Severity
    code: str
    message: str
    repo: str | None = None
    hint: str | None = None


# ---------------------------------------------------------------------------
# helpers


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError):
        return {}


_PLUGIN_DIR_RE = re.compile(r"--plugin-dir\s+(\S+)")
_CLAUDE_INVOCATION_RE = re.compile(r"(^|[\s;&|])claude\b(?![-_])")
_CONTINUE_FLAG_RE = re.compile(r"(^|\s)(-c|--continue|--resume)\b")
_VERSION_PROBE_RE = re.compile(r"claude(\s+--plugin-dir\s+\S+)?\s+--version\b")


def _extract_plugin_dirs(commands: list[str]) -> list[str]:
    """Pull --plugin-dir <path> args out of a launch_commands list."""
    found: list[str] = []
    for cmd in commands or []:
        for m in _PLUGIN_DIR_RE.finditer(cmd or ""):
            found.append(m.group(1).strip("\"'"))
    return found


def _commands_invoke_claude_without_probe(commands: list[str]) -> list[str]:
    """Return commands that invoke ``claude`` for the slash-command call —
    excluding probe-only lines like ``claude --version``.
    """
    out: list[str] = []
    for cmd in commands or []:
        if not _CLAUDE_INVOCATION_RE.search(cmd):
            continue
        # Strip any --version probe pieces so we don't false-positive on lines
        # whose only claude invocation is the probe.
        without_probe = _VERSION_PROBE_RE.sub("", cmd)
        if _CLAUDE_INVOCATION_RE.search(without_probe):
            out.append(cmd)
    return out


# ---------------------------------------------------------------------------
# checks


def check_plugin_dir_consistency(otaman_root: Path) -> list[DoctorWarning]:
    """M-4: warn on plugin-dir drift between platform.yaml and launch-settings.yaml.

    Two failure modes covered:

    1. **Plugin-dir drift**: a repo's ``launch_commands`` contain a
       ``--plugin-dir <X>`` arg that disagrees with the active SSH connection's
       ``ssh_plugin_path``. When the launcher detects this drift it can
       silently rebuild the commands using ``ssh_plugin_path``, hiding the
       real configuration intent.

    2. **WSL path under SSH**: ``launch_commands`` reference a ``/mnt/c/...``
       path while the active connection is ``ssh`` or ``mesh`` — almost
       certainly a leftover from when the project was running locally in WSL
       and was migrated to SSH without a path rewrite.
    """
    warnings: list[DoctorWarning] = []
    platform = _load_yaml(otaman_root / "platform.yaml")
    settings = _load_yaml(otaman_root / "launch-settings.yaml")

    if not platform or not settings:
        return warnings

    active_name = settings.get("active_connection")
    connections = settings.get("connections") or {}
    active_conn = connections.get(active_name) or {}
    conn_type = (active_conn.get("type") or "").lower()
    ssh_plugin_path = active_conn.get("ssh_plugin_path") or ""

    repos = platform.get("repos") or []
    for repo in repos:
        if not isinstance(repo, dict) or repo.get("disabled"):
            continue
        name = repo.get("name", "<unnamed>")
        launch_block = repo.get("launch") or {}
        commands = launch_block.get("commands") or []
        if not commands:
            continue

        plugin_dirs = _extract_plugin_dirs(commands)
        if ssh_plugin_path and plugin_dirs and conn_type in {"ssh", "mesh"}:
            for found in plugin_dirs:
                if found != ssh_plugin_path:
                    warnings.append(
                        DoctorWarning(
                            severity="warn",
                            code="M4_PLUGIN_DIR_DRIFT",
                            repo=name,
                            message=(
                                f"platform.yaml launch_commands reference "
                                f"--plugin-dir '{found}' but active connection "
                                f"'{active_name}' has ssh_plugin_path='{ssh_plugin_path}'. "
                                f"The SSH-rebuild path will silently use ssh_plugin_path; "
                                f"the tmux-wrap path will use launch_commands as-is."
                            ),
                            hint=(
                                f"Align them: either update launch_commands to use "
                                f"'{ssh_plugin_path}', or update ssh_plugin_path to "
                                f"'{found}'."
                            ),
                        )
                    )

        if conn_type in {"ssh", "mesh"}:
            for cmd in commands:
                if "/mnt/c/" in cmd:
                    warnings.append(
                        DoctorWarning(
                            severity="warn",
                            code="M4_WSL_PATH_UNDER_SSH",
                            repo=name,
                            message=(
                                f"launch_commands reference a WSL path "
                                f"('/mnt/c/...') while active connection "
                                f"'{active_name}' is SSH. The remote shell "
                                f"won't resolve that path."
                            ),
                            hint=(
                                "Rewrite the path to its remote form (e.g. "
                                "/home/<user>/<project>/) and re-run the launcher."
                            ),
                        )
                    )

    return warnings


def check_launch_commands_have_continue_flag(otaman_root: Path) -> list[DoctorWarning]:
    """M-13b: warn when per-repo ``launch_commands`` invoke ``claude`` without
    ``-c`` / ``--continue`` / ``--resume``.

    The launcher's SSH-rebuild path rewrites commands to include ``-c``
    (see M-3); the tmux-wrap path consumes ``launch_commands`` verbatim, so
    drift in platform.yaml will silently strand a fresh session on SSH
    reconnect.
    """
    warnings: list[DoctorWarning] = []
    platform = _load_yaml(otaman_root / "platform.yaml")
    if not platform:
        return warnings

    repos = platform.get("repos") or []
    for repo in repos:
        if not isinstance(repo, dict) or repo.get("disabled"):
            continue
        name = repo.get("name", "<unnamed>")
        launch_block = repo.get("launch") or {}
        commands = launch_block.get("commands") or []
        offending = _commands_invoke_claude_without_probe(commands)
        for cmd in offending:
            if not _CONTINUE_FLAG_RE.search(cmd):
                warnings.append(
                    DoctorWarning(
                        severity="warn",
                        code="M13B_MISSING_CONTINUE_FLAG",
                        repo=name,
                        message=(
                            f"launch_commands invoke claude without -c / --continue / "
                            f"--resume: '{cmd.strip()}'. SSH reconnect into this "
                            f"tab will land in a fresh session, losing prior context."
                        ),
                        hint=(
                            "Add -c (or --continue) before the slash command, "
                            "matching the pattern in launch-agents.{sh,ps1}."
                        ),
                    )
                )

    return warnings


# ---------------------------------------------------------------------------
# entry point


def run_all_checks(otaman_root: Path) -> list[DoctorWarning]:
    """Run every plugin-side doctor check and return the combined warnings.

    This is the CLI's entry point. Order is stable across calls so the output
    is deterministic for tests.
    """
    out: list[DoctorWarning] = []
    out.extend(check_plugin_dir_consistency(otaman_root))
    out.extend(check_launch_commands_have_continue_flag(otaman_root))
    return out
