"""Tests for scripts/check-destructive-op.sh (destructive-op-guard 1.1/1.3).

Runs the real shell hook via subprocess (matching test_check_ownership_hook.py's
convention) against a real git working tree — the working-tree-destructive
class needs `git status --porcelain` / `git rev-parse` to resolve against
actual repo state, not a mocked one.

Covers the spec's named scenarios (destructive-op-guard spec.md):
- forked subagent `gh pr merge` requires fresh confirmation despite
  pre-approved/auto permission mode (the hook has no notion of permission
  mode at all — it fires unconditionally, which is exactly the point)
- `git reset --hard` with a dirty tree is intercepted; a clean tree passes
- force-push and push-to-main/master require confirmation
- an unrelated command passes silently (no confirmation-fatigue false
  positives)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "scripts" / "check-destructive-op.sh"


@pytest.fixture
def git_repo(tmp_path):
    """A real git working tree, checked out on `main`, with one commit."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)
    return root


def run_bash(cwd: Path, command: str) -> tuple[int, dict | None]:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(cwd),
        env={"PATH": "/usr/bin:/bin", "HOME": str(cwd)},
    )
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None)


def assert_allowed(rc: int, parsed: dict | None):
    assert rc == 0
    assert parsed is None, f"expected silent allow, got {parsed}"


def assert_asked(rc: int, parsed: dict | None) -> str:
    assert rc == 0, f"ask must exit 0 (not {rc})"
    assert parsed is not None, "ask must emit JSON on stdout"
    hso = parsed["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "ask"
    assert hso.get("permissionDecisionReason"), "reason must reach the model"
    assert parsed.get("systemMessage"), "reason must reach the operator"
    return hso["permissionDecisionReason"]


class TestNonBashOrIrrelevant:
    def test_non_bash_tool_allowed(self, git_repo):
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "x.py"}})
        proc = subprocess.run(
            ["bash", str(HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(git_repo),
            env={"PATH": "/usr/bin:/bin", "HOME": str(git_repo)},
        )
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""

    def test_unrelated_bash_command_allowed(self, git_repo):
        assert_allowed(*run_bash(git_repo, "ls -la"))

    def test_git_status_allowed(self, git_repo):
        assert_allowed(*run_bash(git_repo, "git status"))


class TestPublishMergeClassAlwaysConfirms:
    def test_gh_pr_merge_asks(self, git_repo):
        reason = assert_asked(*run_bash(git_repo, "gh pr merge 24 --squash"))
        assert "gh pr merge" in reason

    def test_gh_repo_delete_asks(self, git_repo):
        assert_asked(*run_bash(git_repo, "gh repo delete owner/repo --yes"))

    def test_force_push_dash_f_asks(self, git_repo):
        assert_asked(*run_bash(git_repo, "git push origin feature -f"))

    def test_force_push_long_flag_asks(self, git_repo):
        assert_asked(*run_bash(git_repo, "git push origin feature --force"))

    def test_force_with_lease_asks(self, git_repo):
        assert_asked(*run_bash(git_repo, "git push origin feature --force-with-lease"))

    def test_push_explicit_main_asks(self, git_repo):
        assert_asked(*run_bash(git_repo, "git push origin main"))

    def test_push_explicit_master_asks(self, git_repo):
        assert_asked(*run_bash(git_repo, "git push origin master"))

    def test_push_refspec_to_main_asks(self, git_repo):
        assert_asked(*run_bash(git_repo, "git push origin +main:main"))

    def test_bare_push_with_no_branch_named_allowed(self, git_repo):
        # v1 deliberately does not resolve a bare push (no branch argument)
        # against the current checkout — see the hook's own comment on why.
        assert_allowed(*run_bash(git_repo, "git push origin"))

    def test_push_to_non_shared_branch_allowed(self, git_repo):
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feature/agent/topic"], cwd=git_repo, check=True
        )
        assert_allowed(*run_bash(git_repo, "git push origin feature/agent/topic"))

    def test_push_to_branch_merely_containing_main_substring_allowed(self, git_repo):
        # 'feature/main-fix' contains "main" as a fragment, not the branch
        # `main` itself — must not false-positive on branch-name text.
        assert_allowed(*run_bash(git_repo, "git push origin feature/main-fix"))

    def test_push_delete_asks(self, git_repo):
        assert_asked(*run_bash(git_repo, "git push origin --delete stale-branch"))

    def test_branch_delete_main_asks(self, git_repo):
        assert_asked(*run_bash(git_repo, "git branch -D main"))

    def test_branch_delete_other_branch_allowed(self, git_repo):
        subprocess.run(["git", "branch", "feature/agent/topic"], cwd=git_repo, check=True)
        assert_allowed(*run_bash(git_repo, "git branch -D feature/agent/topic"))


class TestWorkingTreeClassOnlyOnDirtyTree:
    def test_reset_hard_with_dirty_tree_asks(self, git_repo):
        (git_repo / "README.md").write_text("changed\n", encoding="utf-8")
        reason = assert_asked(*run_bash(git_repo, "git reset --hard HEAD"))
        assert "uncommitted" in reason

    def test_reset_hard_on_clean_tree_allowed(self, git_repo):
        assert_allowed(*run_bash(git_repo, "git reset --hard HEAD"))

    def test_checkout_force_with_dirty_tree_asks(self, git_repo):
        (git_repo / "README.md").write_text("changed\n", encoding="utf-8")
        assert_asked(*run_bash(git_repo, "git checkout -f main"))

    def test_checkout_force_on_clean_tree_allowed(self, git_repo):
        assert_allowed(*run_bash(git_repo, "git checkout -f main"))

    def test_clean_force_with_untracked_file_asks(self, git_repo):
        (git_repo / "scratch.tmp").write_text("junk\n", encoding="utf-8")
        assert_asked(*run_bash(git_repo, "git clean -f"))

    def test_clean_force_on_clean_tree_allowed(self, git_repo):
        assert_allowed(*run_bash(git_repo, "git clean -f"))


class TestLocalWidening:
    def test_local_merge_class_pattern_asks(self, git_repo):
        claude_dir = git_repo / ".claude"
        claude_dir.mkdir()
        (claude_dir / "destructive-op-patterns.local").write_text(
            "# comment\nmerge:npm publish\n", encoding="utf-8"
        )
        reason = assert_asked(*run_bash(git_repo, "npm publish --access public"))
        assert "npm publish" in reason
        assert "locally widened" in reason

    def test_local_worktree_class_pattern_respects_dirty_check(self, git_repo):
        claude_dir = git_repo / ".claude"
        claude_dir.mkdir()
        (claude_dir / "destructive-op-patterns.local").write_text(
            "worktree:rm -rf build/\n", encoding="utf-8"
        )
        # Commit the config file itself first — otherwise it's an untracked
        # file and the "clean tree" case below would start dirty already.
        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "add local patterns"], cwd=git_repo, check=True
        )

        assert_allowed(*run_bash(git_repo, "rm -rf build/"))  # clean tree
        (git_repo / "README.md").write_text("changed\n", encoding="utf-8")
        assert_asked(*run_bash(git_repo, "rm -rf build/"))  # dirty tree

    def test_absent_local_file_is_a_no_op(self, git_repo):
        assert_allowed(*run_bash(git_repo, "ls -la"))
