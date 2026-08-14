"""Tests for hooks/ssh-auto-afk.sh + ssh-auto-afk-end.sh.

These are bash scripts invoked via subprocess so we can exercise the
actual logic Claude Code runs. Each test sets up a temp maestro folder
with a .otaman marker in a managed repo.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
START_HOOK = REPO_ROOT / "hooks" / "ssh-auto-afk.sh"
END_HOOK = REPO_ROOT / "hooks" / "ssh-auto-afk-end.sh"


def _find_bash() -> str | None:
    """Locate a usable bash. On Windows, avoid WSL's bash.exe (needs a
    running WSL distro) and prefer Git Bash at its standard locations."""
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        "/usr/bin/bash",
        "/bin/bash",
    ):
        if Path(candidate).is_file():
            return candidate
    # Fall back to PATH lookup (fine on Linux/macOS; may hit WSL on Windows).
    return shutil.which("bash")


BASH = _find_bash()
pytestmark = pytest.mark.skipif(
    BASH is None,
    reason="bash not available",
)


@pytest.fixture
def ssh_workspace(tmp_path):
    """Fake maestro folder + managed repo, caller starts in the repo."""
    maestro = tmp_path / "my-maestro"
    maestro.mkdir()
    (maestro / "platform.yaml").write_text("project: test\n", encoding="utf-8")
    (maestro / ".agents").mkdir()
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".otaman").write_text("../my-maestro\n", encoding="utf-8")
    return {"root": tmp_path, "maestro": maestro, "repo": repo}


def _run(
    script: Path,
    *,
    cwd: Path,
    env_extra: dict[str, str] | None = None,
    unset: list[str] | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Start clean — remove any pre-existing SSH/AFK vars.
    for k in (
        "SSH_CONNECTION",
        "SSH_TTY",
        "OTAMAN_AFK_AUTO",
        "OTAMAN_LAUNCHER_SSH",
        "OTAMAN_UNATTENDED",
    ):
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    for k in unset or []:
        env.pop(k, None)
    return subprocess.run(
        [BASH, str(script)],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=cwd,
        env=env,
    )


# ---------------------------------------------------------------------------
# SessionStart: ssh-auto-afk.sh


class TestAutoEnable:
    """SessionStart hook: auto-AFK fires ONLY when the launcher set
    OTAMAN_UNATTENDED=1. Pure SSH presence doesn't trigger anymore —
    that was misfiring on interactive launcher tabs."""

    def test_no_env_vars_is_noop(self, ssh_workspace):
        result = _run(START_HOOK, cwd=ssh_workspace["repo"])
        assert result.returncode == 0
        assert not (ssh_workspace["maestro"] / ".otaman" / "afk").exists()

    def test_unattended_triggers_afk(self, ssh_workspace):
        result = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        assert result.returncode == 0
        afk_file = ssh_workspace["maestro"] / ".otaman" / "afk"
        assert afk_file.is_file()
        content = afk_file.read_text(encoding="utf-8")
        assert "source: unattended" in content
        assert "signal: OTAMAN_UNATTENDED" in content
        assert "enabled_at:" in content

    def test_ssh_connection_alone_does_not_trigger(self, ssh_workspace):
        """SSH_CONNECTION by itself is no longer enough — the user may be
        actively driving the session from the other end."""
        result = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"SSH_CONNECTION": "1.2.3.4 5678 9.10.11.12 22"},
        )
        assert result.returncode == 0
        assert not (ssh_workspace["maestro"] / ".otaman" / "afk").exists()

    def test_ssh_tty_alone_does_not_trigger(self, ssh_workspace):
        """SSH_TTY (ssh -t) alone also doesn't trigger anymore."""
        result = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"SSH_TTY": "/dev/pts/0"},
        )
        assert result.returncode == 0
        assert not (ssh_workspace["maestro"] / ".otaman" / "afk").exists()

    def test_launcher_ssh_alone_does_not_trigger(self, ssh_workspace):
        """OTAMAN_LAUNCHER_SSH=1 remains a diagnostic-only signal —
        does NOT trigger auto-AFK on its own."""
        result = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"OTAMAN_LAUNCHER_SSH": "1"},
        )
        assert result.returncode == 0
        assert not (ssh_workspace["maestro"] / ".otaman" / "afk").exists()

    def test_unattended_zero_does_not_trigger(self, ssh_workspace):
        """OTAMAN_UNATTENDED=0 (anything other than '1') is a no-op."""
        result = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "0"},
        )
        assert result.returncode == 0
        assert not (ssh_workspace["maestro"] / ".otaman" / "afk").exists()

    def test_unattended_works_even_without_ssh_env(self, ssh_workspace):
        """Local unattended sessions (e.g. cron on this box) also benefit."""
        result = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        assert result.returncode == 0
        assert (ssh_workspace["maestro"] / ".otaman" / "afk").is_file()

    def test_opt_out_via_afk_auto_env(self, ssh_workspace):
        """OTAMAN_AFK_AUTO=0 remains the global kill switch."""
        result = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={
                "OTAMAN_UNATTENDED": "1",
                "OTAMAN_AFK_AUTO": "0",
            },
        )
        assert result.returncode == 0
        assert not (ssh_workspace["maestro"] / ".otaman" / "afk").exists()

    def test_does_not_clobber_existing_afk(self, ssh_workspace):
        """Manual AFK (with custom TTL / source) must not be overwritten."""
        maestro = ssh_workspace["maestro"]
        (maestro / ".otaman").mkdir(exist_ok=True)
        existing = (
            "enabled_at: 2026-01-01T00:00:00+00:00\n"
            "expires_at: 2030-01-01T00:00:00+00:00\n"
            "source: manual\n"
            "enabled_by: human\n"
        )
        (maestro / ".otaman" / "afk").write_text(existing, encoding="utf-8")
        result = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        assert result.returncode == 0
        assert (maestro / ".otaman" / "afk").read_text(encoding="utf-8") == existing

    def test_no_maestro_root_is_noop(self, tmp_path):
        """Outside a maestro workspace → silent exit 0, no file touched."""
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        result = _run(
            START_HOOK,
            cwd=orphan,
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        assert result.returncode == 0

    def test_message_on_stderr(self, ssh_workspace):
        """The informative message must go to stderr, not pollute stdout."""
        result = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        assert result.stdout == ""
        assert "AFK auto-enabled" in result.stderr

    def test_writes_diagnostic_log(self, ssh_workspace):
        """Every invocation appends a line to .otaman/ssh-auto-afk.log
        so users can diagnose 'why didn't AFK auto-enable?' after the fact."""
        log_file = ssh_workspace["maestro"] / ".otaman" / "ssh-auto-afk.log"

        # Case 1: no OTAMAN_UNATTENDED → log says "skipped: OTAMAN_UNATTENDED!=1"
        _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"SSH_CONNECTION": "1.2.3.4 5678 9.10.11.12 22"},
        )
        assert log_file.is_file()
        content = log_file.read_text(encoding="utf-8")
        assert "OTAMAN_UNATTENDED!=1" in content

        # Case 2: explicit unattended → log says "ENABLED"
        _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        content = log_file.read_text(encoding="utf-8")
        assert "ENABLED AFK" in content

        # Case 3: log also captures env var values for diagnostics
        assert "OTAMAN_UNATTENDED=" in content
        assert "SSH_CONNECTION=" in content
        assert "OTAMAN_AFK_AUTO=" in content

    def test_log_captures_optout_reason(self, ssh_workspace):
        """Opt-out via OTAMAN_AFK_AUTO=0 is recorded with the reason."""
        log_file = ssh_workspace["maestro"] / ".otaman" / "ssh-auto-afk.log"
        _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={
                "OTAMAN_UNATTENDED": "1",
                "OTAMAN_AFK_AUTO": "0",
            },
        )
        content = log_file.read_text(encoding="utf-8")
        assert "OTAMAN_AFK_AUTO=0" in content
        assert "skipped: OTAMAN_AFK_AUTO=0" in content


# ---------------------------------------------------------------------------
# SessionEnd: ssh-auto-afk-end.sh


class TestAutoDisable:
    def test_clears_unattended(self, ssh_workspace):
        maestro = ssh_workspace["maestro"]
        (maestro / ".otaman").mkdir(exist_ok=True)
        (maestro / ".otaman" / "afk").write_text(
            "enabled_at: 2026-04-23T00:00:00+00:00\nsource: unattended\n",
            encoding="utf-8",
        )
        result = _run(END_HOOK, cwd=ssh_workspace["repo"])
        assert result.returncode == 0
        assert not (maestro / ".otaman" / "afk").exists()

    def test_clears_legacy_ssh_auto(self, ssh_workspace):
        """Backwards-compat: AFK files written by old hook versions used
        `source: ssh-auto` — SessionEnd still clears them."""
        maestro = ssh_workspace["maestro"]
        (maestro / ".otaman").mkdir(exist_ok=True)
        (maestro / ".otaman" / "afk").write_text(
            "enabled_at: 2026-04-23T00:00:00+00:00\nsource: ssh-auto\n",
            encoding="utf-8",
        )
        result = _run(END_HOOK, cwd=ssh_workspace["repo"])
        assert result.returncode == 0
        assert not (maestro / ".otaman" / "afk").exists()

    def test_clears_idle_auto(self, ssh_workspace):
        """Idle-auto-enabled AFK also cleared on session end."""
        maestro = ssh_workspace["maestro"]
        (maestro / ".otaman").mkdir(exist_ok=True)
        (maestro / ".otaman" / "afk").write_text(
            "enabled_at: 2026-04-23T00:00:00+00:00\nsource: idle-auto\n",
            encoding="utf-8",
        )
        result = _run(END_HOOK, cwd=ssh_workspace["repo"])
        assert result.returncode == 0
        assert not (maestro / ".otaman" / "afk").exists()

    def test_preserves_manual(self, ssh_workspace):
        """Manually-set AFK (source: manual) survives SessionEnd."""
        maestro = ssh_workspace["maestro"]
        (maestro / ".otaman").mkdir(exist_ok=True)
        manual_content = (
            "enabled_at: 2026-04-23T00:00:00+00:00\n"
            "expires_at: 2030-01-01T00:00:00+00:00\n"
            "source: manual\n"
        )
        (maestro / ".otaman" / "afk").write_text(manual_content, encoding="utf-8")
        result = _run(END_HOOK, cwd=ssh_workspace["repo"])
        assert result.returncode == 0
        assert (maestro / ".otaman" / "afk").read_text(encoding="utf-8") == manual_content

    def test_no_afk_file_is_noop(self, ssh_workspace):
        result = _run(END_HOOK, cwd=ssh_workspace["repo"])
        assert result.returncode == 0

    def test_no_maestro_root_is_noop(self, tmp_path):
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        result = _run(END_HOOK, cwd=orphan)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Round-trip: SessionStart + SessionEnd


class TestRoundTrip:
    def test_unattended_session_autoenables_then_clears(self, ssh_workspace):
        maestro = ssh_workspace["maestro"]
        afk_file = maestro / ".otaman" / "afk"

        # Start of unattended session
        r = _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        assert r.returncode == 0
        assert afk_file.is_file()

        # End of session
        r = _run(END_HOOK, cwd=ssh_workspace["repo"])
        assert r.returncode == 0
        assert not afk_file.exists()

    def test_manual_beats_end_hook(self, ssh_workspace):
        """Manual AFK set during an unattended session survives session end."""
        maestro = ssh_workspace["maestro"]
        (maestro / ".otaman").mkdir(exist_ok=True)

        # Auto-enable first
        _run(
            START_HOOK,
            cwd=ssh_workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        # User overrides to manual
        (maestro / ".otaman" / "afk").write_text(
            "enabled_at: 2026-04-23T00:00:00+00:00\n"
            "expires_at: 2030-01-01T00:00:00+00:00\n"
            "source: manual\n",
            encoding="utf-8",
        )
        # Session ends
        _run(END_HOOK, cwd=ssh_workspace["repo"])
        # Manual entry survives
        assert (maestro / ".otaman" / "afk").is_file()
