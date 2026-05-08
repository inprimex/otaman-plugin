"""Tests for hooks/check-routing.sh — account mismatch warning.

Verifies the resolution order that mirrors bridge_approval.py's
_derive_account (OTAMAN_ACTIVE_ROUTING → CLAUDE_CONFIG_DIR basename
→ silent skip for custom layouts).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
HOOK = REPO_ROOT / "hooks" / "check-routing.sh"


def _find_bash() -> str | None:
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        "/usr/bin/bash",
        "/bin/bash",
    ):
        if Path(candidate).is_file():
            return candidate
    return shutil.which("bash")


BASH = _find_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


@pytest.fixture
def workspace(tmp_path):
    """Fake maestro + repo; caller sets expected_account per test."""
    maestro = tmp_path / "maestro"
    maestro.mkdir()
    (maestro / "platform.yaml").write_text(
        "project: test\n", encoding="utf-8",
    )
    (maestro / ".agents").mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    return {"root": tmp_path, "maestro": maestro, "repo": repo}


def _write_marker(workspace, expected_routing: str) -> None:
    """Write a .otaman marker with an expected_account field."""
    (workspace["repo"] / ".otaman").write_text(
        f"maestro_root: ../maestro\n"
        f"expected_routing: {expected_routing}\n",
        encoding="utf-8",
    )


def _run(workspace, *, env_extra=None, unset=None):
    env = os.environ.copy()
    for k in ("OTAMAN_ACTIVE_ROUTING", "CLAUDE_CONFIG_DIR"):
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    for k in unset or []:
        env.pop(k, None)
    return subprocess.run(
        [BASH, str(HOOK)],
        capture_output=True, text=True, timeout=10,
        cwd=workspace["repo"], env=env,
    )


# ---------------------------------------------------------------------------


class TestActiveAccountEnvVarWins:
    """OTAMAN_ACTIVE_ROUTING is the first signal — it disambiguates the
    'one CLAUDE_CONFIG_DIR, many accounts' shape."""

    def test_env_matches_marker_no_warning(self, workspace):
        _write_marker(workspace, "greenbin")
        result = _run(workspace, env_extra={
            "OTAMAN_ACTIVE_ROUTING": "greenbin",
            "CLAUDE_CONFIG_DIR": "/home/u/.claude-personal",  # shared with watchtower
        })
        assert result.returncode == 0
        assert "mismatch" not in result.stderr

    def test_env_overrides_config_dir_basename(self, workspace):
        """The exact "shared config dir, separate maestro accounts" scenario:
        CLAUDE_CONFIG_DIR says 'personal' but OTAMAN_ACTIVE_ROUTING says
        'greenbin' — the env var wins, marker check passes."""
        _write_marker(workspace, "greenbin")
        result = _run(workspace, env_extra={
            "OTAMAN_ACTIVE_ROUTING": "greenbin",
            "CLAUDE_CONFIG_DIR": "/home/u/.claude-personal",
        })
        assert "mismatch" not in result.stderr

    def test_env_mismatch_warns(self, workspace):
        _write_marker(workspace, "greenbin")
        result = _run(workspace, env_extra={
            "OTAMAN_ACTIVE_ROUTING": "someone-else",
        })
        assert result.returncode == 0
        assert "mismatch" in result.stderr
        assert "someone-else" in result.stderr
        assert "greenbin" in result.stderr
        assert "OTAMAN_ACTIVE_ROUTING" in result.stderr


class TestConfigDirFallback:
    """When OTAMAN_ACTIVE_ROUTING isn't set, fall back to
    CLAUDE_CONFIG_DIR basename (the legacy behavior)."""

    def test_matching_basename_no_warning(self, workspace):
        _write_marker(workspace, "personal")
        result = _run(workspace, env_extra={
            "CLAUDE_CONFIG_DIR": "/home/u/.claude-personal",
        })
        assert "mismatch" not in result.stderr

    def test_mismatched_basename_warns(self, workspace):
        _write_marker(workspace, "greenbin")
        result = _run(workspace, env_extra={
            "CLAUDE_CONFIG_DIR": "/home/u/.claude-personal",
        })
        assert "mismatch" in result.stderr
        # Warning attributes it to CLAUDE_CONFIG_DIR, not the env var
        assert "CLAUDE_CONFIG_DIR" in result.stderr
        assert "OTAMAN_ACTIVE_ROUTING" not in result.stderr

    def test_unset_config_dir_defaults(self, workspace):
        _write_marker(workspace, "default")
        result = _run(workspace)  # no env vars set
        assert "mismatch" not in result.stderr


class TestCustomConfigDirSkip:
    """Non-standard CLAUDE_CONFIG_DIR (not `.claude-*`) silently skips."""

    def test_custom_layout_no_warning(self, workspace):
        _write_marker(workspace, "greenbin")
        result = _run(workspace, env_extra={
            "CLAUDE_CONFIG_DIR": "/opt/custom/claude-config",
        })
        assert result.returncode == 0
        assert "mismatch" not in result.stderr


class TestNoMarker:
    def test_no_marker_silent_skip(self, workspace):
        """No .otaman marker → nothing to check against; silent exit."""
        result = _run(workspace, env_extra={
            "OTAMAN_ACTIVE_ROUTING": "anything",
        })
        assert result.returncode == 0
        assert result.stderr == ""


class TestMessageFormat:
    """Warning message includes enough context to debug."""

    def test_includes_marker_path(self, workspace):
        _write_marker(workspace, "greenbin")
        result = _run(workspace, env_extra={
            "OTAMAN_ACTIVE_ROUTING": "wrong",
        })
        # The fix hint mentions 'otaman accounts list'.
        assert "otaman accounts list" in result.stderr
