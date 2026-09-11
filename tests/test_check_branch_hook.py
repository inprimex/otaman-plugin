"""Tests for scripts/check-branch.sh — branch naming + protected-branch guard.

team-mode-registers-and-sessions 2.1 (B1, Roman ruling 2026-09-11):
.agents/current-agent is retired. This hook now resolves identity through
the shared resolve_agent_identity (otaman_core.identity), which is
cwd-ownership-authoritative with an OTAMAN_AGENT fallback — no
.agents/current-agent, no per-repo .otaman marker for this purpose.

Real execution against the actual scripts/check-branch.sh and a real git
repo — skipped where bash/git/the workspace otaman_core aren't available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "scripts" / "check-branch.sh"

HAVE_BASH = shutil.which("bash") is not None
HAVE_GIT = shutil.which("git") is not None

pytestmark = pytest.mark.skipif(not (HAVE_BASH and HAVE_GIT), reason="bash/git not on PATH")


def _make_repo(tmp_path: Path, branch: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", branch], cwd=repo, check=True)
    return repo


def _run_hook(repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )


class TestProtectedBranchStillBlocked:
    """Untouched by the identity migration — sanity check nothing broke."""

    def test_main_is_blocked_regardless_of_identity(self, tmp_path):
        repo = _make_repo(tmp_path, "main")
        r = _run_hook(repo, dict(os.environ))
        assert r.returncode == 1
        assert "BLOCKED" in r.stdout

    def test_allow_main_override(self, tmp_path):
        repo = _make_repo(tmp_path, "main")
        env = {**os.environ, "OTAMAN_ALLOW_MAIN": "1"}
        r = _run_hook(repo, env)
        assert r.returncode == 0


class TestIdentityViaOtamanAgentFallback:
    """No platform.yaml anywhere above repo -> cwd-ownership is unresolved
    -> OTAMAN_AGENT is the only remaining signal (current-agent is gone)."""

    def test_otaman_agent_drives_the_naming_warning(self, tmp_path):
        repo = _make_repo(tmp_path, "some-random-branch")
        env = {**os.environ, "OTAMAN_AGENT": "backend-agent"}
        r = _run_hook(repo, env)
        assert r.returncode == 0
        assert "naming convention" in r.stdout
        assert "agent/backend-agent/" in r.stdout

    def test_no_identity_signal_allows_silently(self, tmp_path):
        """No OTAMAN_AGENT, no platform.yaml ownership match -> unresolved
        -> human working directly -> no warning, no block."""
        repo = _make_repo(tmp_path, "some-random-branch")
        env = {k: v for k, v in os.environ.items() if k != "OTAMAN_AGENT"}
        r = _run_hook(repo, env)
        assert r.returncode == 0
        assert "naming convention" not in r.stdout

    def test_current_agent_file_alone_no_longer_drives_the_warning(self, tmp_path):
        """.agents/current-agent is retired — planting one (with no
        OTAMAN_AGENT and no ownership match) must NOT resolve identity."""
        repo = _make_repo(tmp_path, "some-random-branch")
        (repo / ".agents").mkdir()
        (repo / ".agents" / "current-agent").write_text("backend-agent", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "OTAMAN_AGENT"}
        r = _run_hook(repo, env)
        assert r.returncode == 0
        assert "naming convention" not in r.stdout

    def test_agent_branch_naming_no_warning(self, tmp_path):
        repo = _make_repo(tmp_path, "agent/backend-agent/some-feature")
        env = {**os.environ, "OTAMAN_AGENT": "backend-agent"}
        r = _run_hook(repo, env)
        assert r.returncode == 0
        assert "naming convention" not in r.stdout
