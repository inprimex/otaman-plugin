"""Tests for hooks/session-start-clear-afk.sh — auto-clear AFK on new
Claude sessions so the user is back to native prompts after they relaunch.

Same subprocess pattern as test_ssh_auto_afk.py: invoke the bash script
against a fake maestro folder + .otaman marker.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
HOOK = REPO_ROOT / "hooks" / "session-start-clear-afk.sh"


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
    maestro = tmp_path / "my-maestro"
    maestro.mkdir()
    (maestro / "platform.yaml").write_text("project: test\n", encoding="utf-8")
    (maestro / ".agents").mkdir()
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".otaman").write_text("../my-maestro\n", encoding="utf-8")
    return {"root": tmp_path, "maestro": maestro, "repo": repo}


def _run(*, cwd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Strip out anything leaking from the dev's shell that could change behavior.
    for k in ("OTAMAN_UNATTENDED", "OTAMAN_AFK_AUTO",
              "OTAMAN_ACTIVE_ACCOUNT", "OTAMAN_AFK_NO_NOTIFY"):
        env.pop(k, None)
    # Tests must not actually try to talk to a daemon — the inner Python
    # call will fork and the suppress-flag short-circuits before any I/O.
    env["OTAMAN_AFK_NO_NOTIFY"] = "1"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [BASH, str(HOOK)],
        capture_output=True, text=True, timeout=15,
        cwd=cwd, env=env,
    )


def _write_afk(maestro: Path, source: str = "manual") -> Path:
    afk_dir = maestro / ".otaman"
    afk_dir.mkdir(exist_ok=True)
    f = afk_dir / "afk"
    f.write_text(
        "enabled_at: 2026-04-25T08:00:00+00:00\n"
        f"source: {source}\n"
        "enabled_by: human\n",
        encoding="utf-8",
    )
    return f


class TestClear:
    def test_clears_manual_afk(self, workspace):
        afk_file = _write_afk(workspace["maestro"], "manual")
        result = _run(cwd=workspace["repo"])
        assert result.returncode == 0
        assert not afk_file.exists()
        assert "auto-cleared" in result.stderr

    def test_clears_idle_auto_afk(self, workspace):
        afk_file = _write_afk(workspace["maestro"], "idle-auto")
        result = _run(cwd=workspace["repo"])
        assert result.returncode == 0
        assert not afk_file.exists()

    def test_clears_unattended_leftover(self, workspace):
        """A leftover unattended AFK from a prior session must be cleared
        when the new session is NOT itself unattended."""
        afk_file = _write_afk(workspace["maestro"], "unattended")
        result = _run(cwd=workspace["repo"])  # no OTAMAN_UNATTENDED=1
        assert result.returncode == 0
        assert not afk_file.exists()


class TestSkip:
    def test_skip_when_no_afk_file(self, workspace):
        """Idempotent: no file means nothing to do, exit 0 silently."""
        result = _run(cwd=workspace["repo"])
        assert result.returncode == 0
        assert result.stderr == ""

    def test_skip_when_unattended_session(self, workspace):
        """OTAMAN_UNATTENDED=1 means ssh-auto-afk.sh will set state next —
        clearing here would just produce a confusing notification pair."""
        afk_file = _write_afk(workspace["maestro"], "unattended")
        result = _run(
            cwd=workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        assert result.returncode == 0
        assert afk_file.exists()  # preserved

    def test_kill_switch_preserves_afk(self, workspace):
        """OTAMAN_AFK_AUTO=0 disables the auto-clear (mirrors auto-on)."""
        afk_file = _write_afk(workspace["maestro"], "manual")
        result = _run(
            cwd=workspace["repo"],
            env_extra={"OTAMAN_AFK_AUTO": "0"},
        )
        assert result.returncode == 0
        assert afk_file.exists()  # preserved

    def test_no_maestro_root_is_noop(self, tmp_path):
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        result = _run(cwd=orphan)
        assert result.returncode == 0


class TestDiagnostics:
    def test_log_records_clear_action(self, workspace):
        log = workspace["maestro"] / ".otaman" / "session-start-clear-afk.log"
        _write_afk(workspace["maestro"], "manual")
        _run(cwd=workspace["repo"])
        assert log.is_file()
        content = log.read_text(encoding="utf-8")
        assert "CLEARED AFK" in content
        assert "prior source=manual" in content

    def test_log_records_skip_when_unattended(self, workspace):
        log = workspace["maestro"] / ".otaman" / "session-start-clear-afk.log"
        _write_afk(workspace["maestro"], "manual")
        _run(
            cwd=workspace["repo"],
            env_extra={"OTAMAN_UNATTENDED": "1"},
        )
        content = log.read_text(encoding="utf-8")
        assert "skipped: OTAMAN_UNATTENDED=1" in content

    def test_log_records_kill_switch(self, workspace):
        log = workspace["maestro"] / ".otaman" / "session-start-clear-afk.log"
        _write_afk(workspace["maestro"], "manual")
        _run(
            cwd=workspace["repo"],
            env_extra={"OTAMAN_AFK_AUTO": "0"},
        )
        content = log.read_text(encoding="utf-8")
        assert "OTAMAN_AFK_AUTO=0" in content


class TestStderrMessage:
    def test_stdout_clean_stderr_informative(self, workspace):
        """Hook output never goes to stdout — that would pollute the
        UserPromptSubmit / SessionStart channel Claude reads."""
        _write_afk(workspace["maestro"], "manual")
        result = _run(cwd=workspace["repo"])
        assert result.stdout == ""
        assert "auto-cleared" in result.stderr
