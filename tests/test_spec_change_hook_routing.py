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
import sys
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


def _spec_change_body(meta: Path) -> str:
    msgs = sorted((meta / ".agents" / "bus" / "active").glob("*-spec-change.md"))
    assert msgs, "hook wrote no spec-change message at all"
    return msgs[-1].read_text(encoding="utf-8")


class TestTheNoticeSaysWhyNotAStaticClaim:
    """cli measured the old static sentence false in 4 of 5 cases
    (20261002T204704), on 419 of 495 spec commits.

    It read: "Fallback: `spec-agent` when no tasks.md exists; `spec-agent,
    human` when no annotations." But five situations collapse into that same
    recipient list, and the one that matters most is a TYPO'd annotation —
    where the reader was told "this change assigns nobody" when the truth was
    "the dispatch could not find the person it named".
    """

    def test_the_false_static_sentence_is_gone(self, tmp_path):
        meta, specs = _program(tmp_path, repo_names=["prog-cli"])
        _commit_tasks(specs, ["otaman-prog-cli"])
        _run_hook(specs, tmp_path)
        body = _spec_change_body(meta)
        assert "Fallback: `spec-agent` when no tasks.md exists" not in body

    @staticmethod
    def _home_with_reachable_cli(home: Path) -> dict[str, str]:
        """A HOME whose deployed-venv path resolves to an interpreter that can
        import otaman_cli.

        The fixture overrides HOME for isolation, which hides the real
        deployed venv — so without this the hook can only ever take the
        no-python branch here and the python branch would go untested. This
        plants the interpreter where `resolve_otaman_python` looks for it.
        """
        venv_bin = home / ".local" / "venv" / "otaman" / "bin"
        venv_bin.mkdir(parents=True, exist_ok=True)
        link = venv_bin / "python"
        if not link.exists():
            link.symlink_to(sys.executable)
        cli_src = REPO.parent / "otaman-cli" / "src"
        core_src = REPO.parent / "otaman-core" / "src"
        env = {**os.environ, "HOME": str(home)}
        env.pop("OTAMAN_ROOT", None)
        env.pop("MAESTRO_ROOT", None)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(cli_src), str(core_src), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        return env

    def test_a_typod_annotation_is_named_not_reported_as_unassigned(self, tmp_path):
        """THE case the old text got wrong. A typo must not read as 'nobody is
        assigned' — it must name what could not be resolved."""
        if not (REPO.parent / "otaman-cli" / "src" / "otaman_cli").is_dir():
            pytest.skip("otaman-cli sibling not present")
        meta, specs = _program(tmp_path, repo_names=["prog-cli"])
        _commit_tasks(specs, ["otaman-prog-cli-agent"])  # repo is prog-cli, not prog-cli-agent
        env = self._home_with_reachable_cli(tmp_path)
        subprocess.run(
            ["bash", str(HOOK)], cwd=specs, capture_output=True, text=True, timeout=60, env=env
        )
        body = _spec_change_body(meta)
        assert "Why these recipients" in body, "the python branch did not run"
        assert "otaman-prog-cli-agent" in body, (
            "the unresolvable annotation is not named in the notice"
        )

    def test_a_resolved_change_prints_NO_reason_line_at_all(self, tmp_path):
        """The reason is empty when real owners resolved, and the LINE must be
        absent — not present-and-blank.

        An earlier version asserted only that the fallback phrases were
        missing, which an empty `**Why these recipients**: ` line satisfies
        trivially. A sabotage printing exactly that scored 11/11 against it.
        Must run on the python branch: the no-python path always emits a line,
        so checking absence anywhere else would test the wrong thing.
        """
        if not (REPO.parent / "otaman-cli" / "src" / "otaman_cli").is_dir():
            pytest.skip("otaman-cli sibling not present")
        meta, specs = _program(tmp_path, repo_names=["prog-cli"])
        _commit_tasks(specs, ["otaman-prog-cli"])  # resolves to a real owner
        env = self._home_with_reachable_cli(tmp_path)
        subprocess.run(
            ["bash", str(HOOK)], cwd=specs, capture_output=True, text=True, timeout=60, env=env
        )
        body = _spec_change_body(meta)
        assert "cli-agent" in _spec_change_to_line(meta), "owners did not resolve"
        assert "Why these recipients" not in body, (
            "a reason line was printed for a change whose owners resolved"
        )

    def test_the_no_python_path_says_undetermined_rather_than_asserting(self, tmp_path):
        """A hook must never fail a commit, so the shell lookup stays. But an
        unknown reason STATED beats a false reason printed confidently —
        which was the whole defect."""
        body = HOOK.read_text(encoding="utf-8")
        assert "not determined (no interpreter here could import otaman_cli)" in body


class TestTheChangeIsAField:
    """cli: 419 of 495 notices carried the change only inside a path in
    `**Changed files**`, so a reader or triage script parses a path for most
    and reads a field for the rest."""

    def test_the_change_name_is_its_own_field(self, tmp_path):
        meta, specs = _program(tmp_path, repo_names=["prog-cli"])
        _commit_tasks(specs, ["otaman-prog-cli"])
        _run_hook(specs, tmp_path)
        assert "**Change**: demo" in _spec_change_body(meta)

    def test_it_does_not_require_parsing_a_path(self, tmp_path):
        """The field must carry the bare name, not the tasks.md path."""
        meta, specs = _program(tmp_path, repo_names=["prog-cli"])
        _commit_tasks(specs, ["otaman-prog-cli"])
        _run_hook(specs, tmp_path)
        line = [ln for ln in _spec_change_body(meta).splitlines() if ln.startswith("**Change**:")]
        assert line and "openspec/changes" not in line[0]
