"""Shared otaman root resolution for all Python scripts.

Resolution chain (first match wins):
1. .otaman/.maestro marker file in start dir or ancestors  # legacy: .maestro marker supported
2. OTAMAN_ROOT / MAESTRO_ROOT environment variable  # legacy: MAESTRO_ROOT env var supported
3. Walk-up fallback: look for platform.yaml or .agents/ (legacy/monorepo compat)

Also exposes expand_config_dir() for per-shell tilde / env-var expansion of
account config_dir paths declared in launch-settings.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path

# Shells that resolve paths on a different host (remote / different userspace)
# from the Python interpreter. For these, we emit POSIX-style paths and defer
# tilde / env expansion to the target shell.
_DEFERRED_SHELLS = frozenset({"wsl", "ssh"})

# Shells that speak native Windows paths.
_WINDOWS_SHELLS = frozenset({"powershell", "pwsh", "cmd"})

# Known fields in .otaman/.maestro marker files. Unknown `key:` lines fall through to  # legacy: .maestro supported
# bare-path handling, which preserves support for Windows absolute paths
# (e.g. ``C:/work/my-otaman``) that happen to contain a colon.
_KNOWN_MARKER_FIELDS = frozenset({"maestro_root", "expected_account"})  # legacy: maestro_root field name


def find_maestro_root(start: Path | None = None) -> Path | None:
    """Find the otaman root directory.  # legacy: function name kept for callers

    Args:
        start: Directory to start searching from. Defaults to cwd.

    Returns:
        Resolved absolute path to the otaman root, or None if not found.
    """
    origin = (start or Path.cwd()).resolve()

    # 1. .otaman/.maestro marker file — walk up looking for it  # legacy: .maestro marker supported
    current = origin
    while current != current.parent:
        marker = current / ".otaman"
        if not marker.is_file():
            marker = current / ".maestro"  # legacy: .maestro marker path
        if marker.is_file():
            rel = parse_marker_fields(marker).get("maestro_root")  # legacy: maestro_root field name
            if rel:
                candidate = (current / rel).resolve()
                if (candidate / "platform.yaml").exists() or (candidate / ".agents").is_dir():
                    return candidate
        current = current.parent

    # 2. OTAMAN_ROOT / MAESTRO_ROOT environment variable  # legacy: MAESTRO_ROOT env var
    env_root = os.environ.get("OTAMAN_ROOT", os.environ.get("MAESTRO_ROOT", "")).strip()  # legacy: MAESTRO_ROOT env var
    if env_root:
        p = Path(env_root).resolve()
        if (p / "platform.yaml").exists() or (p / ".agents").is_dir():
            return p

    # 3. Walk-up fallback (legacy layout: otaman artifacts in a parent directory)
    current = origin
    while current != current.parent:
        if (current / "platform.yaml").exists() or (current / ".agents").is_dir():
            return current
        current = current.parent

    return None


def parse_marker_fields(marker_path: Path) -> dict[str, str]:
    """Parse a ``.otaman``/``.maestro`` marker file into a dict of fields.  # legacy: .maestro supported

    Accepts two formats, chosen line-by-line:

    - **Legacy** — a single bare line holding the relative path to the
      otaman folder (e.g. ``../my-otaman``). Becomes ``maestro_root``.  # legacy: maestro_root field name
    - **Extended** — ``key: value`` lines for known fields, plus an
      optional bare path line. Current known fields: ``maestro_root``,  # legacy: maestro_root field name
      ``expected_account``.

    Unknown ``key: value`` lines are ignored so that Windows absolute
    paths containing a colon (``C:/foo``) continue to parse as bare
    ``maestro_root`` values.  # legacy: maestro_root field name
    """
    fields: dict[str, str] = {}
    try:
        text = marker_path.read_text(encoding="utf-8")
    except OSError:
        return fields
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key in _KNOWN_MARKER_FIELDS:
                fields.setdefault(key, value)
                continue
        # Bare line → treat as maestro_root if not set  # legacy: maestro_root field name
        fields.setdefault("maestro_root", line)  # legacy: maestro_root field name
    return fields


def find_marker(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default: cwd) looking for a ``.otaman``/``.maestro`` marker.  # legacy: .maestro supported

    Returns the marker path, or None if no marker is found on the way up.
    """
    origin = (start or Path.cwd()).resolve()
    current = origin
    while current != current.parent:
        marker = current / ".otaman"
        if not marker.is_file():
            marker = current / ".maestro"  # legacy: .maestro marker path
        if marker.is_file():
            return marker
        current = current.parent
    return None


def read_expected_account(start: Path | None = None) -> str | None:
    """Return the ``expected_account`` field from the nearest ``.otaman``/``.maestro`` marker.  # legacy: .maestro supported

    Returns None if no marker is found or the field is absent/empty.
    """
    marker = find_marker(start)
    if marker is None:
        return None
    value = parse_marker_fields(marker).get("expected_account")
    return value if value else None


def expand_config_dir(config_dir: str, shell: str, *, home: str | None = None) -> str:
    """Expand a ``config_dir`` spec for a target shell.

    The value comes from ``launch-settings.yaml accounts.<name>.config_dir``
    (e.g. ``~/.claude-personal``). Different shells expand tildes and env
    variables differently, and some shells (wsl, ssh) resolve on a different
    host entirely — in those cases we defer expansion to the target shell.

    Args:
        config_dir: Raw value from YAML. May contain ``~``, ``$HOME``,
            ``${HOME}``, ``$USERPROFILE``, ``${USERPROFILE}``.
        shell: Target shell name. Understood values:
            - ``powershell`` / ``pwsh`` / ``cmd`` — native Windows path output
            - ``bash`` / ``zsh`` / ``fish`` — POSIX-slash output, expanded
            - ``wsl`` / ``ssh`` — pass-through; target shell resolves
        home: Override for ``$HOME`` / ``~``. Defaults to ``Path.home()``.
            Mainly for tests and cross-shell expansion (e.g. a Windows
            launcher computing a WSL path without needing to shell out).

    Returns:
        A path string appropriate for the target shell. Empty input returns
        an empty string.
    """
    if not config_dir:
        return ""

    # Accept both forward and back slashes in the input.
    s = config_dir.replace("\\", "/")

    if shell in _DEFERRED_SHELLS:
        # Deferred: keep as-is (POSIX slashes already). Remote shell expands.
        return s

    # Local shell — expand env vars and tilde.
    resolved_home = home if home is not None else str(Path.home())
    resolved_home = resolved_home.replace("\\", "/")

    for token in ("${HOME}", "$HOME", "${USERPROFILE}", "$USERPROFILE"):
        s = s.replace(token, resolved_home)

    if s == "~":
        s = resolved_home
    elif s.startswith("~/"):
        s = f"{resolved_home}/{s[2:]}"

    if shell in _WINDOWS_SHELLS:
        return s.replace("/", "\\")
    return s.replace("\\", "/")
