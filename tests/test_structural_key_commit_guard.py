"""Structural platform.yaml keys need the human, even from the owner.

otaman-meta-ownership 1.1. The otaman folder now has a declared owner, and
the owner's authority is MERGE, not approval: `repos`, `ownership`, `bus`,
`communication` and `program` re-point who owns what, who hears what, and
which repos exist. A commit touching one is refused naming the key.

WHY A COMMIT GUARD. A PreToolUse write hook sees only `file_path` through
this script's flat JSON reader; proposed content arrives as escaped
multi-line text it cannot parse. A commit has `git diff --cached`, so before
and after are both real files and the comparison is exact. Editing
platform.yaml stays free — landing it is what needs the human.

WHAT THIS IS NOT. Not a security boundary; the human reviewing the PR is
that. It fails OPEN where it genuinely cannot tell (no python, no git, an
unparseable file), because a hook that refused every commit it could not
analyse gets routed around within a day — the cry-wolf failure that makes a
guard worse than none.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "scripts" / "check-ownership.sh"
AGENT = "test-agent"

NON_STRUCTURAL = 'project: test\nversion: "1.0"\nknowledge:\n  ttl: {ttl}\n'
WITH_REPOS = (
    'project: test\nversion: "1.0"\nknowledge:\n  ttl: 30\n'
    "repos:\n  - name: a\n    owner: {owner}\n"
)


@pytest.fixture
def meta(tmp_path):
    """An otaman folder that is a real git repo, with an identity the
    enforcement resolver can find (the `.otaman` ancestry walk, per F013)."""
    root = tmp_path / "otaman-meta"
    (root / ".agents").mkdir(parents=True)
    (root / ".otaman").write_text(f".\nagent: {AGENT}\n", encoding="utf-8")
    (root / ".agents" / "ownership.json").write_text(
        json.dumps({"project": "test", "repos": []}, indent=2), encoding="utf-8"
    )
    env = {"PATH": "/usr/bin:/bin", "HOME": str(root), "GIT_CONFIG_GLOBAL": str(tmp_path / "gc")}

    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (root / "platform.yaml").write_text(WITH_REPOS.format(owner="a-agent"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "init")
    return {"root": root, "git": git, "env": env}


def _commit_attempt(meta, otaman_bin: str | None = None) -> dict | None:
    """Run the hook as if `git commit` were about to execute.

    *otaman_bin* puts the stub CLI on PATH so the enforcement identity
    actually RESOLVES. Without it nobody is identified, and a test claiming
    to prove something about the owner proves only that an anonymous
    committer is refused — which is a different statement.
    """
    import sys

    payload = json.dumps({"tool_name": "Bash", "command": "git commit -m x"})
    env = dict(meta["env"])
    if otaman_bin:
        env["PATH"] = f"{otaman_bin}:{env['PATH']}"
    env["PATH"] = f"{Path(sys.executable).parent}:{env['PATH']}"
    env["PYTHONPATH"] = str(REPO / "src")
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(meta["root"]),
        env=env,
    )
    out = proc.stdout.strip()
    assert proc.returncode == 0, f"hook must always exit 0: {proc.stderr}"
    return json.loads(out) if out else None


def _reason(parsed: dict) -> str:
    return parsed["hookSpecificOutput"]["permissionDecisionReason"]


class TestStructuralChangesAreRefused:
    def test_changing_repos_is_refused_naming_the_key(self, meta):
        (meta["root"] / "platform.yaml").write_text(
            WITH_REPOS.format(owner="someone-else"), encoding="utf-8"
        )
        meta["git"]("add", "platform.yaml")

        parsed = _commit_attempt(meta)
        assert parsed is not None, "a structural change committed without the human"
        assert parsed["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "repos" in _reason(parsed)

    def test_adding_an_ownership_block_is_refused(self, meta):
        """Ownership is the key this very change adds — re-pointing it later
        must not be easier than declaring it was."""
        (meta["root"] / "platform.yaml").write_text(
            WITH_REPOS.format(owner="a-agent") + "ownership:\n  otaman-folder: someone\n",
            encoding="utf-8",
        )
        meta["git"]("add", "platform.yaml")

        parsed = _commit_attempt(meta)
        assert parsed is not None
        assert "ownership" in _reason(parsed)

    def test_the_refusal_says_what_to_DO(self, meta):
        """A refusal with no next step is a wall. The owner needs to know the
        human authorizes structure, and that the rest of the commit can go."""
        (meta["root"] / "platform.yaml").write_text(WITH_REPOS.format(owner="x"), encoding="utf-8")
        meta["git"]("add", "platform.yaml")

        reason = _reason(_commit_attempt(meta))
        assert "decision-required" in reason
        assert "unstage" in reason

    def test_it_refuses_the_OWNER_too(self, meta, otaman_stub_bin):
        """The whole point: ownership is merge authority, not approval
        authority. A guard the owner can walk through guards nothing, since
        the owner is who commits here.

        `otaman_stub_bin` is load-bearing. Without it the enforcement
        identity never resolves, and sabotaging the guard with
        `[[ "$CURRENT_AGENT" == "test-agent" ]] && return 0` passed — because
        CURRENT_AGENT was empty and the owner branch was never reached. The
        test named the owner and tested an anonymous committer.
        """
        (meta["root"] / "platform.yaml").write_text(WITH_REPOS.format(owner="x"), encoding="utf-8")
        (meta["root"] / ".agents" / "ownership.json").write_text(
            json.dumps(
                {
                    "project": "test",
                    "repos": [],
                    "otaman_folder": {"path": ".", "owner": AGENT, "authority": "merge"},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        meta["git"]("add", "-A")

        parsed = _commit_attempt(meta, otaman_bin=otaman_stub_bin)
        assert parsed is not None, "the declared owner walked through the structural guard"
        assert "repos" in _reason(parsed)


class TestOrdinaryWorkIsUnaffected:
    """Clause 3's other half. A guard that fires on normal commits teaches
    operators to bypass it, which is worse than not having it."""

    def test_a_non_structural_key_commits_freely(self, meta):
        (meta["root"] / "platform.yaml").write_text(
            WITH_REPOS.format(owner="a-agent").replace("ttl: 30", "ttl: 90"), encoding="utf-8"
        )
        meta["git"]("add", "platform.yaml")
        assert _commit_attempt(meta) is None, "a knowledge TTL change needed the human"

    def test_a_commit_not_touching_platform_yaml_is_untouched(self, meta):
        (meta["root"] / "notes.md").write_text("hello\n", encoding="utf-8")
        meta["git"]("add", "notes.md")
        assert _commit_attempt(meta) is None

    def test_a_non_commit_bash_command_is_untouched(self, meta):
        (meta["root"] / "platform.yaml").write_text(
            WITH_REPOS.format(owner="someone-else"), encoding="utf-8"
        )
        meta["git"]("add", "platform.yaml")
        payload = json.dumps({"tool_name": "Bash", "command": "git status"})
        proc = subprocess.run(
            ["bash", str(HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(meta["root"]),
            env=meta["env"],
        )
        assert proc.stdout.strip() == "", "git status was treated as a commit"


class TestItFailsOpenWhenItCannotTell:
    """ "Could not check" must not become "refused" here, deliberately: this
    is a speed bump on structure, and the human at PR review is the boundary.
    A hook that blocks whenever its analysis is unavailable gets disabled."""

    # The "no python interpreter" fail-open is NOT unit-tested, deliberately.
    # I wrote a test for it that passed locally and failed in CI: omitting the
    # venv python does not remove python, CI has a system one that imports the
    # package fine, and `resolve_otaman_python` probes absolute paths besides.
    # The test was asserting an environment I cannot create rather than a
    # behaviour I control — a flaky test waiting to happen. The branch is one
    # line (`[[ -n "$py" ]] || return 0`); the paths below are the fail-opens
    # a sandbox can actually produce.

    def test_a_non_git_directory_is_not_guessed_at(self, meta):
        """`git rev-parse` fails, so there is no staged diff to analyse and
        nothing to have an opinion about."""
        import shutil as _shutil

        (meta["root"] / "platform.yaml").write_text(
            WITH_REPOS.format(owner="someone-else"), encoding="utf-8"
        )
        meta["git"]("add", "platform.yaml")
        _shutil.rmtree(meta["root"] / ".git")
        assert _commit_attempt(meta) is None

    def test_platform_yaml_not_staged_is_not_analysed(self, meta):
        """Structural keys differ in the WORKTREE but nothing is staged —
        there is no commit to guard, and editing stays free by design."""
        (meta["root"] / "platform.yaml").write_text(
            WITH_REPOS.format(owner="someone-else"), encoding="utf-8"
        )
        # deliberately NOT staged
        assert _commit_attempt(meta) is None

    def test_an_unparseable_platform_yaml_is_not_guessed_at(self, meta):
        """Refusing on unparseable YAML would block the commit that FIXES it."""
        (meta["root"] / "platform.yaml").write_text("{{{ not yaml\n", encoding="utf-8")
        meta["git"]("add", "platform.yaml")
        assert _commit_attempt(meta) is None


class TestTheListHasOneHome:
    def test_the_guard_and_the_generator_share_the_constant(self):
        """The hook enforces STRUCTURAL_PLATFORM_KEYS and the generated
        instructions render it. Two lists would teach one rule and enforce
        another."""
        from otaman_plugin.generate_agent_config import STRUCTURAL_PLATFORM_KEYS

        hook = HOOK.read_text(encoding="utf-8")
        assert "STRUCTURAL_PLATFORM_KEYS" in hook
        assert "repos" in STRUCTURAL_PLATFORM_KEYS
        assert "ownership" in STRUCTURAL_PLATFORM_KEYS
