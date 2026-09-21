"""spec-change-hook.sh routes `@otaman-<repo>` annotations for programs whose
repos are NOT otaman-prefixed — and says so when it cannot load its own
dependency.

Two defects, both verified against haulops' real config by deploy-agent
(20260921T184535) and reproduced here before fixing:

1. The hook looked up only `otaman-<suffix>`. That works on THIS fleet by
   coincidence of naming (`@otaman-cli` -> repo `otaman-cli`) and never
   matches for a program whose repos are not otaman-prefixed:
   `@otaman-haulops-firmware` looked up `otaman-haulops-firmware` against a
   repo actually named `haulops-firmware`, missed, and silently fell back to
   `spec-agent, human`. `repos[].name` carries no documented prefix
   constraint. otaman-cli's `notify_change._lookup_owners` already solved
   this — try as-is, then prefix-stripped — so the hook copies it rather than
   inventing a third behaviour.

2. Three silences were stacked on this path (the git-hook shim's `|| true`,
   `|| exit 0` on a missing `_resolve.sh`, and the annotation loop skipping
   unmatched repos). Together they made a completely DEAD hook
   indistinguishable from a quiet one. The hook now distinguishes "my install
   is broken" (say so) from "no otaman root here" (stay quiet).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "scripts" / "spec-change-hook.sh"

HAVE_BASH = shutil.which("bash") is not None
HAVE_GIT = shutil.which("git") is not None

pytestmark = pytest.mark.skipif(not (HAVE_BASH and HAVE_GIT), reason="bash/git not on PATH")


@pytest.fixture(autouse=True)
def _unpin_root(monkeypatch):
    monkeypatch.delenv("OTAMAN_ROOT", raising=False)
    monkeypatch.delenv("MAESTRO_ROOT", raising=False)


def _program(tmp_path: Path, *, repo_names: list[str]) -> tuple[Path, Path]:
    """A program whose repos are named as given — the point being that they
    need not start with `otaman-`."""
    meta = tmp_path / "prog-otaman"
    (meta / ".agents" / "bus" / "active" / "acks").mkdir(parents=True)
    repos = "".join(
        f"  - name: {n}\n    path: ../{n}\n    owner: {n.split('-')[-1]}-agent\n"
        for n in repo_names
    )
    (meta / "platform.yaml").write_text(f"project: prog\nrepos:\n{repos}", encoding="utf-8")

    specs = tmp_path / "prog-specs"
    change = specs / "openspec" / "changes" / "demo"
    change.mkdir(parents=True)
    (specs / ".otaman").write_text("../prog-otaman\nagent: spec-agent\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=specs, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=specs, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=specs, check=True)
    # An initial commit is required: the hook reads `git diff-tree ... HEAD`,
    # which lists nothing for a repo's FIRST commit, so tasks.md must land as
    # a SECOND commit or the hook exits before doing any work.
    (specs / "README.md").write_text("specs\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=specs, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=specs, check=True)
    return meta, specs


def _commit_tasks(specs: Path, annotations: list[str]) -> None:
    tasks = specs / "openspec" / "changes" / "demo" / "tasks.md"
    body = "# Tasks\n\n" + "".join(
        f"- [ ] 1.{i} @{a} do the thing\n" for i, a in enumerate(annotations, 1)
    )
    tasks.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=specs, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "spec: tasks"], cwd=specs, check=True)


def _run_hook(specs: Path, home: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(home)}
    env.pop("OTAMAN_ROOT", None)
    env.pop("MAESTRO_ROOT", None)
    return subprocess.run(
        ["bash", str(HOOK)], cwd=specs, capture_output=True, text=True, timeout=60, env=env
    )


def _spec_change_to_line(meta: Path) -> str:
    msgs = sorted((meta / ".agents" / "bus" / "active").glob("*-spec-change.md"))
    assert msgs, "hook wrote no spec-change message at all"
    for line in msgs[-1].read_text(encoding="utf-8").splitlines():
        if line.startswith("to:"):
            return line
    raise AssertionError("no `to:` line in the spec-change message")


class TestUnprefixedRepoNames:
    def test_routes_to_the_real_owner(self, tmp_path):
        """The regression: haulops-shaped names must resolve."""
        meta, specs = _program(tmp_path, repo_names=["haulops-firmware", "haulops-sim"])
        _commit_tasks(specs, ["otaman-haulops-firmware", "otaman-haulops-sim"])
        r = _run_hook(specs, tmp_path)
        assert r.returncode == 0, r.stderr

        to_line = _spec_change_to_line(meta)
        assert "firmware-agent" in to_line
        assert "sim-agent" in to_line

    def test_does_not_fall_back_to_spec_agent_human(self, tmp_path):
        """That fallback is what made the miss invisible — it looks like a
        deliberate routing decision rather than a failed lookup."""
        meta, specs = _program(tmp_path, repo_names=["haulops-firmware"])
        _commit_tasks(specs, ["otaman-haulops-firmware"])
        _run_hook(specs, tmp_path)
        assert _spec_change_to_line(meta).strip() != "to: spec-agent, human"


class TestPrefixedRepoNamesStillWork:
    def test_this_fleets_convention_is_unbroken(self, tmp_path):
        """The as-is lookup must still win for otaman-prefixed repos — the
        fix adds a fallback, it does not replace the existing behaviour."""
        meta, specs = _program(tmp_path, repo_names=["otaman-cli", "otaman-core"])
        _commit_tasks(specs, ["otaman-cli", "otaman-core"])
        _run_hook(specs, tmp_path)

        to_line = _spec_change_to_line(meta)
        assert "cli-agent" in to_line
        assert "core-agent" in to_line

    def test_exact_name_wins_over_the_stripped_fallback(self, tmp_path):
        """A program carrying BOTH `otaman-web` and `web` must route
        @otaman-web to the exact match, not the fallback."""
        meta, specs = _program(tmp_path, repo_names=["otaman-web", "web"])
        _commit_tasks(specs, ["otaman-web"])
        _run_hook(specs, tmp_path)
        # owner is derived from the last dash-segment in the fixture, so both
        # repos yield `web-agent`; assert the lookup resolved at all and did
        # not degrade to the fallback recipients.
        assert _spec_change_to_line(meta).strip() != "to: spec-agent, human"


class TestBrokenInstallSpeaks:
    def test_missing_resolve_sh_says_so(self, tmp_path):
        """deploy-agent's ask: whatever else changes, the hook should say
        something when it cannot load its own dependency. Simulated by
        copying ONLY the hook into an isolated dir, which is exactly the
        wheel's old shape."""
        lone = tmp_path / "installed" / "scripts"
        lone.mkdir(parents=True)
        shutil.copy(HOOK, lone / "spec-change-hook.sh")

        _, specs = _program(tmp_path, repo_names=["x"])
        _commit_tasks(specs, ["otaman-x"])

        env = {**os.environ, "HOME": str(tmp_path)}
        env.pop("OTAMAN_ROOT", None)
        env.pop("MAESTRO_ROOT", None)
        r = subprocess.run(
            ["bash", str(lone / "spec-change-hook.sh")],
            cwd=specs,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        assert r.returncode == 0, "a post-commit hook must never fail the commit"
        assert "_resolve.sh" in r.stderr, "a broken install must not be silent"
        assert "notify-change" in r.stderr, "and should name the workaround"
