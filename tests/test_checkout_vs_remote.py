"""check 5 — a sibling checkout behind its own remote (rfsd 1.1, signal 2).

Fleet rules direct agents to read sibling repos as the contract. A checkout
silently behind its remote makes that contract wrong, and until this check
nothing on the tenant said so.

MEASURED INCIDENT (2026-10-03): plugin-agent consumed otaman-core #122 against
a core checkout one commit behind origin/main. The first signal was 31 failing
tests in CI — which fetches fresh — on a branch that touched only docstrings.

SIGNAL 1 IS DELIBERATELY ABSENT. rfsd 1.1 also names "commits on origin/main
since release.yaml installed_at". That is the comparand spec-agent pinned as
rejected on 20260925, which plugin-agent accepted in writing the same day and
then re-proposed in the SCR that produced this task. Sibling mains run ahead
of the last cut BY DESIGN, so it renders SKEWED on every healthy workspace
(measured while writing this: core 20, cli 34, plugin 19). Raised rather than
built — 20261004T095501.

THE COMPARAND IS THE DEFAULT BRANCH, NOT HEAD. 1.1 specifies
`HEAD..@{upstream}`; on this tenant that is not-checked for 3 of 6 actively
worked repos, because agents are on feature branches and one repo is on a
detached HEAD. The question is about the checkout's source of truth, not about
whatever branch someone is mid-task on.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

from otaman_plugin.runtime_freshness import check_checkout_vs_remote

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(cwd: pathlib.Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def _tenant(tmp_path: pathlib.Path, *, default_branch: str = "main"):
    """An otaman root with one sibling repo cloned from a real origin."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig")}

    origin = tmp_path / "origin.git"
    work = tmp_path / "seed"
    work.mkdir()
    _git(work, "init", "-q", f"--initial-branch={default_branch}", env=env)
    _git(work, "config", "user.email", "t@t", env=env)
    _git(work, "config", "user.name", "t", env=env)
    (work / "a.txt").write_text("1\n", encoding="utf-8")
    _git(work, "add", "-A", env=env)
    _git(work, "commit", "-qm", "one", env=env)
    _git(work, "clone", "-q", "--bare", str(work), str(origin), env=env)

    root = tmp_path / "otaman-meta"
    root.mkdir()
    (root / "platform.yaml").write_text(
        "repos:\n  - name: acme-lib\n    path: ../acme-lib\n", encoding="utf-8"
    )
    checkout = tmp_path / "acme-lib"
    _git(tmp_path, "clone", "-q", str(origin), str(checkout), env=env)
    _git(checkout, "config", "user.email", "t@t", env=env)
    _git(checkout, "config", "user.name", "t", env=env)
    return root, checkout, work, origin, env


def _advance_origin(work: pathlib.Path, origin: pathlib.Path, env: dict, n: int = 1):
    """Push n new commits to origin WITHOUT touching the checkout."""
    for i in range(n):
        (work / "a.txt").write_text(f"{i + 2}\n", encoding="utf-8")
        _git(work, "add", "-A", env=env)
        _git(work, "commit", "-qm", f"more {i}", env=env)
    _git(work, "push", "-q", str(origin), "HEAD", env=env)


def _by_subject(findings):
    return {f.subject: f for f in findings}


class TestItCatchesTheIncidentItWasBuiltFor:
    def test_a_checkout_behind_its_remote_is_SKEWED(self, tmp_path):
        root, checkout, work, origin, env = _tenant(tmp_path)
        _advance_origin(work, origin, env, n=1)
        _git(checkout, "fetch", "-q", "origin", env=env)

        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert f.verdict == "skewed"
        assert f.evidence["behind"] == 1
        assert "behind origin/main" in f.reason

    def test_it_NAMES_the_count_not_just_the_fact(self, tmp_path):
        """ "behind" with no number cannot be triaged against other repos."""
        root, checkout, work, origin, env = _tenant(tmp_path)
        _advance_origin(work, origin, env, n=4)
        _git(checkout, "fetch", "-q", "origin", env=env)

        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert f.evidence["behind"] == 4
        assert "4 commit(s) behind" in f.reason

    def test_the_remedy_is_actionable_and_names_the_repo(self, tmp_path):
        root, checkout, work, origin, env = _tenant(tmp_path)
        _advance_origin(work, origin, env, n=1)
        _git(checkout, "fetch", "-q", "origin", env=env)

        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert "pull --ff-only" in f.remedy
        assert str(checkout) in f.remedy

    def test_a_level_checkout_is_FRESH(self, tmp_path):
        """It must not cry wolf on the healthy case, or the section gets
        skipped — the failure D3 of the parent change exists to prevent."""
        root, _checkout, _work, _origin, _env = _tenant(tmp_path)
        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert f.verdict == "fresh"
        assert f.evidence["behind"] == 0


class TestNotCheckedIsLoudAndNeverFresh:
    """nss clause 2, and the clause-3 case the task names: collapsing
    not-checked into fresh must fail."""

    def test_every_verdict_DATES_the_refs_it_rests_on(self, tmp_path):
        """The honest limit of an offline check, made legible.

        This check never fetches — doctor doing network writes to every
        sibling, with a hung remote able to hang the run, is a worse trade.
        So it cannot know that origin moved one second after a clone: here,
        origin is 3 ahead and the local refs say level.

        What it CAN guarantee is that no verdict is readable as "verified
        against the live remote". Every reason carries the refs' age, and
        evidence carries the timestamp, so "fresh" means "level as of refs
        this old" and an operator can see when that stops being good enough.
        """
        root, checkout, work, origin, env = _tenant(tmp_path)
        _advance_origin(work, origin, env, n=3)
        # deliberately NO fetch — the refs cannot have seen those 3 commits
        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert "refs" in f.reason and "h old" in f.reason, (
            f"a verdict with no as-of reads as verified-now: {f.reason!r}"
        )
        assert f.evidence.get("fetched_at"), "the basis timestamp is not recorded"

    def test_refs_older_than_the_window_are_NOT_fresh(self, tmp_path):
        """The case the as-of alone does not save: refs so old they cannot
        speak to the question. This fleet merged 43 commits across four repos
        in one measured day, so a day-old ref answers nothing."""
        import os as _os
        import time as _time

        root, checkout, work, origin, env = _tenant(tmp_path)
        old = _time.time() - (3 * 24 * 3600)
        for rel in ("FETCH_HEAD", "packed-refs", "refs/remotes/origin/main"):
            path = checkout / ".git" / rel
            if path.exists():
                _os.utime(path, (old, old))

        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert f.verdict == "not-checked"
        assert "too" in f.reason and "old" in f.reason
        assert f.ok is False

    def test_a_non_git_path_is_not_checked_naming_why(self, tmp_path):
        root = tmp_path / "otaman-meta"
        root.mkdir()
        (root / "platform.yaml").write_text(
            "repos:\n  - name: plain\n    path: ../plain\n", encoding="utf-8"
        )
        (tmp_path / "plain").mkdir()
        f = _by_subject(check_checkout_vs_remote(root))["checkout plain"]
        assert f.verdict == "not-checked"
        assert "not a git checkout" in f.reason
        assert f.ok is False, "not-checked must never satisfy ok"

    def test_no_declared_repos_is_not_checked_not_silence(self, tmp_path):
        root = tmp_path / "otaman-meta"
        root.mkdir()
        (root / "platform.yaml").write_text("repos: []\n", encoding="utf-8")
        findings = check_checkout_vs_remote(root)
        assert len(findings) == 1
        assert findings[0].verdict == "not-checked"
        assert "no repo paths" in findings[0].reason

    def test_not_checked_never_reports_ok(self, tmp_path):
        root = tmp_path / "otaman-meta"
        root.mkdir()
        (root / "platform.yaml").write_text("repos: []\n", encoding="utf-8")
        assert all(not f.ok for f in check_checkout_vs_remote(root))


class TestTheDefaultBranchIsASKEDNotASSUMED:
    def test_a_repo_whose_default_is_not_main_still_resolves(self, tmp_path):
        """otaman-landing uses `dev`. Assuming `main` would render it
        not-checked forever for a reason its owner cannot act on."""
        root, checkout, work, origin, env = _tenant(tmp_path, default_branch="dev")
        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert f.verdict == "fresh"
        assert f.evidence["branch"] == "dev"

    def test_drift_is_detected_on_that_branch_too(self, tmp_path):
        root, checkout, work, origin, env = _tenant(tmp_path, default_branch="dev")
        _advance_origin(work, origin, env, n=2)
        _git(checkout, "fetch", "-q", "origin", env=env)
        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert f.verdict == "skewed"
        assert f.evidence["branch"] == "dev"
        assert f.evidence["behind"] == 2

    def test_a_DETACHED_HEAD_does_not_mask_it(self, tmp_path):
        """Named explicitly by the amended 1.1 ("feature branch / detached
        HEAD do not mask it"), and not hypothetical — otaman-core sits on a
        detached HEAD on this tenant right now, which is the repo the check
        was built to catch.

        `HEAD..@{upstream}` cannot answer at all here; the default-branch
        comparand is unaffected because it never consults HEAD.
        """
        root, checkout, work, origin, env = _tenant(tmp_path)
        _advance_origin(work, origin, env, n=3)
        _git(checkout, "fetch", "-q", "origin", env=env)
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()
        _git(checkout, "checkout", "-q", "--detach", sha, env=env)

        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert f.verdict == "skewed", "a detached HEAD hid the drift"
        assert f.evidence["behind"] == 3
        assert f.evidence["branch"] == "main"

    def test_a_feature_branch_does_not_change_the_answer(self, tmp_path):
        """The reason 1.1's `HEAD..@{upstream}` was wrong: an agent mid-task
        is on an unpushed branch, and the question is about the checkout's
        source of truth, not about their working branch."""
        root, checkout, work, origin, env = _tenant(tmp_path)
        _advance_origin(work, origin, env, n=1)
        _git(checkout, "fetch", "-q", "origin", env=env)
        _git(checkout, "checkout", "-q", "-b", "agent/someone/wip", env=env)

        f = _by_subject(check_checkout_vs_remote(root))["checkout acme-lib"]
        assert f.verdict == "skewed", "a feature branch hid the drift"
        assert f.evidence["behind"] == 1


class TestSignal1IsNotHere:
    """It is a rejection this agent made and re-proposed; building it would
    render SKEWED on every healthy workspace."""

    def test_the_module_does_not_measure_commits_since_install(self):
        import pathlib as _p

        import otaman_plugin.runtime_freshness as m

        src = _p.Path(m.__file__).read_text(encoding="utf-8")
        body = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
        assert "--since" not in body, (
            "commits-since-installed_at is back — it is the comparand pinned "
            "rejected on 20260925 and renders SKEWED on every dev workspace"
        )

    def test_the_rejection_is_recorded_where_the_next_proposer_will_look(self):
        """The whole reason this recurred: the rejection lived in a comment
        the next proposer (me) did not read before writing the SCR."""
        import pathlib as _p

        import otaman_plugin.runtime_freshness as m

        src = _p.Path(m.__file__).read_text(encoding="utf-8")
        assert "20260925" in src
        assert "cry-wolf" in src or "permanently yellow" in src


class TestItIsACTUALLYWIRED:
    """Clause 3, the half I failed first time.

    Every other test here calls `check_checkout_vs_remote` directly, so the
    check could be defined and never invoked by doctor and all of them stay
    green. Sabotage proved it: deleting the `out.extend(...)` line from
    `assess` passed 14/14. A signal nobody runs is a signal removed.
    """

    def test_run_all_checks_emits_checkout_drift(self, tmp_path):
        from otaman_plugin.runtime_freshness import assess

        root, _checkout, _work, _origin, _env = _tenant(tmp_path)
        checks = {f.check for f in assess(root)}
        assert "checkout-drift" in checks, (
            "check 5 is defined but doctor never runs it — orphaned, not shipped"
        )

    def test_the_drift_verdict_survives_the_aggregation(self, tmp_path):
        """Not just present: the real verdict must reach the caller, since
        doctor renders what assess() returns and nothing else."""
        from otaman_plugin.runtime_freshness import assess

        root, checkout, work, origin, env = _tenant(tmp_path)
        _advance_origin(work, origin, env, n=2)
        _git(checkout, "fetch", "-q", "origin", env=env)

        drift = [f for f in assess(root) if f.check == "checkout-drift"]
        assert [f.verdict for f in drift] == ["skewed"]
        assert drift[0].evidence["behind"] == 2


class TestAGitDirWithNoRemoteRefs:
    """What this ACTUALLY exercises, after sabotage corrected me.

    I wrote it believing it drove the "refs cannot be dated" branch. It does
    not: `_default_branch` returns None first, so the verdict comes from the
    earlier guard. Sabotaging the dating branch left all tests green, which is
    how I found out.

    The dating branch is in fact practically UNREACHABLE — if a default branch
    resolved, its ref is either loose or in packed-refs, and both are datable.
    It survives only a stat race or an unreadable .git. Kept as a defensive
    not-checked (the alternative is an unhandled None flowing into arithmetic),
    documented as untested rather than given a test that proves nothing.
    """

    def test_no_resolvable_default_branch_is_not_checked(self, tmp_path):
        root = tmp_path / "otaman-meta"
        root.mkdir()
        (root / "platform.yaml").write_text(
            "repos:\n  - name: bare-ish\n    path: ../bare-ish\n", encoding="utf-8"
        )
        repo = tmp_path / "bare-ish"
        (repo / ".git").mkdir(parents=True)

        f = _by_subject(check_checkout_vs_remote(root))["checkout bare-ish"]
        assert f.verdict == "not-checked"
        assert f.ok is False
        assert "source of truth" in f.reason, (
            "this is the default-branch guard, not the refs-dating one"
        )
