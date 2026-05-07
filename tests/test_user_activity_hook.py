"""Tests for hooks/user-activity.sh — UserPromptSubmit → timestamp file."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
HOOK = REPO_ROOT / "hooks" / "user-activity.sh"


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
    (maestro / "platform.yaml").write_text(
        "project: test\n", encoding="utf-8",
    )
    (maestro / ".agents").mkdir()
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".otaman").write_text("../my-maestro\n", encoding="utf-8")
    return {"root": tmp_path, "maestro": maestro, "repo": repo}


def _run(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, str(HOOK)],
        capture_output=True, text=True, timeout=10, cwd=cwd,
    )


class TestUserActivityHook:
    def test_writes_timestamp_file(self, workspace):
        result = _run(workspace["repo"])
        assert result.returncode == 0
        activity_file = workspace["maestro"] / ".otaman" / "last-user-activity"
        assert activity_file.is_file()
        content = activity_file.read_text(encoding="utf-8").strip()
        # ISO-8601 UTC: YYYY-MM-DDTHH:MM:SS+00:00
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$", content)

    def test_updates_mtime_on_each_call(self, workspace):
        result = _run(workspace["repo"])
        assert result.returncode == 0
        activity_file = workspace["maestro"] / ".otaman" / "last-user-activity"
        first_mtime = activity_file.stat().st_mtime
        time.sleep(1.1)  # filesystem mtime resolution varies
        _run(workspace["repo"])
        second_mtime = activity_file.stat().st_mtime
        assert second_mtime > first_mtime

    def test_no_maestro_root_is_silent_noop(self, tmp_path):
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        result = subprocess.run(
            [BASH, str(HOOK)],
            capture_output=True, text=True, timeout=10, cwd=orphan,
        )
        assert result.returncode == 0

    def test_no_stdout_pollution(self, workspace):
        """UserPromptSubmit hook must not add junk to the prompt context."""
        result = _run(workspace["repo"])
        assert result.stdout == ""
