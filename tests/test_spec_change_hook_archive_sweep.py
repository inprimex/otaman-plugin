"""Tests for scripts/spec-change-hook.sh's archive backstop
(blocked-entry-lifecycle 1.2).

The hook is a raw git post-commit script installed in the SPECS repo — a
write path that bypasses `otaman_send`/MCP entirely (same class of
producer as otaman-cli's `otaman approve`). When a commit moves a change
into openspec/changes/archive/, the hook now shells out to a python
capable of importing otaman_plugin and calls
`sweep_archived_blocked(root, archived_change_names(root))` directly,
sweeping any live `## Blocked:` entry (either Kind) across every agent's
blocked file whose `**Change**:` field names the newly-archived change.

Real execution against the actual hook script + a real git repo, with
PATH pinned to the shared workspace venv (the only place otaman_plugin is
importable) — skipped where bash/git aren't on PATH or that venv doesn't
exist (matches this repo's convention for other real-subprocess hook
tests, e.g. test_check_branch_hook.py).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "scripts" / "spec-change-hook.sh"
WORKSPACE_VENV_BIN = REPO.parent / ".venv" / "bin"

HAVE_BASH = shutil.which("bash") is not None
HAVE_GIT = shutil.which("git") is not None
HAVE_WORKSPACE_PYTHON = (WORKSPACE_VENV_BIN / "python3").exists()

pytestmark = pytest.mark.skipif(
    not (HAVE_BASH and HAVE_GIT and HAVE_WORKSPACE_PYTHON),
    reason="bash/git not on PATH, or no shared workspace venv to import otaman_plugin from",
)


def _write_blocked(path: Path, *, title: str, change: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"\n## Blocked: {title}\n"
        f"- **Change**: {change}\n"
        f"- **Blocked since**: 2026-06-10T16:15:00Z\n",
        encoding="utf-8",
    )


def _make_specs_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "otaman-specs"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README.md").write_text("specs\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


def _run_hook_via_archive_commit(otaman_root: Path, specs_repo: Path, change_name: str) -> None:
    archive_dir = specs_repo / "openspec" / "changes" / "archive" / change_name
    archive_dir.mkdir(parents=True)
    (archive_dir / "proposal.md").write_text("archived\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=specs_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", f"spec: archive {change_name}"], cwd=specs_repo, check=True
    )

    env = dict(os.environ)
    env["OTAMAN_ROOT"] = str(otaman_root)
    env["PATH"] = f"{WORKSPACE_VENV_BIN}:{env.get('PATH', '')}"
    result = subprocess.run(
        ["bash", str(HOOK)],
        cwd=specs_repo,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, result.stderr


class TestArchiveSweepWiredIntoHook:
    def test_archiving_a_change_sweeps_its_blocked_entries(self, tmp_path):
        otaman_root = tmp_path / "my-otaman"
        otaman_root.mkdir()
        (otaman_root / "platform.yaml").write_text(
            "specs:\n  path: ../otaman-specs\n", encoding="utf-8"
        )
        blocked_file = otaman_root / ".agents" / "blocked" / "plugin-agent.md"
        _write_blocked(blocked_file, title="waiting on it", change="the-archived-change")

        specs_repo = _make_specs_repo(tmp_path)
        _run_hook_via_archive_commit(otaman_root, specs_repo, "the-archived-change")

        text = blocked_file.read_text(encoding="utf-8")
        assert "— change archived -->" in text
        assert "\n## Blocked: waiting on it" not in text

    def test_unrelated_blocked_entry_is_untouched(self, tmp_path):
        otaman_root = tmp_path / "my-otaman"
        otaman_root.mkdir()
        (otaman_root / "platform.yaml").write_text(
            "specs:\n  path: ../otaman-specs\n", encoding="utf-8"
        )
        blocked_file = otaman_root / ".agents" / "blocked" / "plugin-agent.md"
        _write_blocked(blocked_file, title="still active", change="a-different-change")
        before = blocked_file.read_text(encoding="utf-8")

        specs_repo = _make_specs_repo(tmp_path)
        _run_hook_via_archive_commit(otaman_root, specs_repo, "the-archived-change")

        assert blocked_file.read_text(encoding="utf-8") == before

    def test_non_archive_commit_does_not_invoke_the_sweep(self, tmp_path):
        """A regular spec-content commit (no archive/ path) must not touch
        blocked files at all — the sweep is scoped to archive commits only."""
        otaman_root = tmp_path / "my-otaman"
        otaman_root.mkdir()
        (otaman_root / "platform.yaml").write_text(
            "specs:\n  path: ../otaman-specs\n", encoding="utf-8"
        )
        blocked_file = otaman_root / ".agents" / "blocked" / "plugin-agent.md"
        _write_blocked(blocked_file, title="still active", change="some-change")
        before = blocked_file.read_text(encoding="utf-8")

        specs_repo = _make_specs_repo(tmp_path)
        (specs_repo / "openspec").mkdir()
        (specs_repo / "openspec" / "notes.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=specs_repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "spec: notes"], cwd=specs_repo, check=True)

        env = dict(os.environ)
        env["OTAMAN_ROOT"] = str(otaman_root)
        env["PATH"] = f"{WORKSPACE_VENV_BIN}:{env.get('PATH', '')}"
        result = subprocess.run(
            ["bash", str(HOOK)], cwd=specs_repo, capture_output=True, text=True, env=env
        )
        assert result.returncode == 0, result.stderr
        assert blocked_file.read_text(encoding="utf-8") == before
