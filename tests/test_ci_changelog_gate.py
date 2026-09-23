"""This repo's CI wires the core-invokable changelog-fragment gate
(release-notes-sibling-coverage 2.5).

The gate must be the SHARED entry point — `python -m
otaman_core.changelog_fragment --check` — not a repo-local script and not
cli's `otaman policy check-changelog`. Six siblings wire the same one line
(task 1.3, amended by SCR 20260921T152814); a repo-local variant would be the
seventh hand-rolled definition of a shared rule.

The `ci-ok` interaction is the part worth pinning. This repo's aggregate
deliberately FAILS on any non-success dependency, including `skipped`, so a
skipped required check cannot let a broken PR through. But the changelog job
is PR-only, so it is legitimately skipped on push to main. Accepting `skipped`
for that one job — and only that one — is the narrow exception, and these
tests exist so nobody widens it by accident.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"


def _ci_ok_run(wf: dict) -> str:
    """The ci-ok verification step's raw shell, not a re-dump of it — a
    yaml.safe_dump round-trip escapes the quotes these assertions match on."""
    return "\n".join(s.get("run", "") for s in wf["jobs"]["ci-ok"]["steps"])


@pytest.fixture(scope="module")
def wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


class TestGateIsWired:
    def test_changelog_job_exists(self, wf):
        assert "changelog" in wf["jobs"]

    def test_uses_the_core_invokable_entry_point(self, wf):
        steps = yaml.safe_dump(wf["jobs"]["changelog"]["steps"])
        assert "otaman_core.changelog_fragment" in steps
        assert "--check" in steps

    def test_is_not_a_repo_local_script_or_the_cli_verb(self, wf):
        """Both would be a second definition of a shared rule."""
        steps = yaml.safe_dump(wf["jobs"]["changelog"]["steps"])
        assert "policy check-changelog" not in steps
        assert "scripts/" not in steps

    def test_passes_the_pr_number_and_body(self, wf):
        """Without --pr a PR could ride a sibling's fragment file; without
        the body file the documented exemption marker cannot work."""
        steps = yaml.safe_dump(wf["jobs"]["changelog"]["steps"])
        assert "--pr " in steps or "--pr\n" in steps
        assert "--pr-body-file" in steps

    def test_full_history_is_fetched(self, wf):
        """A shallow checkout cannot resolve the base...HEAD merge-base, so
        the diff would be wrong rather than absent."""
        checkout = next(
            s
            for s in wf["jobs"]["changelog"]["steps"]
            if "checkout" in str(s.get("uses", "")) and "otaman-plugin" in str(s.get("with", {}))
        )
        assert checkout["with"]["fetch-depth"] == 0


class TestPrOnlyWithoutBreakingCiOk:
    def test_gate_runs_only_on_pull_requests(self, wf):
        assert wf["jobs"]["changelog"]["if"] == "github.event_name == 'pull_request'"

    def test_ci_ok_depends_on_it(self, wf):
        """Otherwise the gate is advisory and blocks nothing."""
        assert "changelog" in wf["jobs"]["ci-ok"]["needs"]

    def test_ci_ok_tolerates_skipped_for_the_gate_only(self, wf):
        """The narrow exception: PR-only means deterministically skipped on
        push. lint/test must still be strictly `success`."""
        run = _ci_ok_run(wf)
        assert "skipped" in run, "push to main would fail ci-ok on the skipped gate"
        assert 'needs.lint.result }}" != "success"' in run
        assert 'needs.test.result }}" != "success"' in run

    def test_skipped_is_not_accepted_for_lint_or_test(self, wf):
        """Guard against widening the exception: a skipped lint/test must
        still fail ci-ok, which is why this aggregate exists at all."""
        run = _ci_ok_run(wf)
        for job in ("lint", "test"):
            assert f'needs.{job}.result }}}}" != "skipped"' not in run


class TestPrBodyIsNotInterpolatedIntoTheShell:
    def test_body_passed_via_env_not_expression(self, wf):
        """A PR body is attacker-controlled text. Interpolating it directly
        into a `run:` would be a shell-injection vector; it must arrive via
        env and be written with printf."""
        step = next(s for s in wf["jobs"]["changelog"]["steps"] if s.get("name") == "Write PR body")
        assert "PR_BODY" in step.get("env", {})
        assert "${{ github.event.pull_request.body }}" not in step["run"]


class TestMatrixBlockingPolicy:
    """macOS and Windows are INFORMATIONAL legs, and must SAY so.

    Roman held macOS support on 2026-09-23, so gating merges on it would
    commit the fleet to a platform it has not committed to. The leg stays
    anyway, and stays green: it went 27 failures -> 0 across PRs #68-#70 and
    that work should not have to be redone if support is revisited.

    But an unlabelled non-blocking leg is exactly what hid those four
    problems for months — three of which were real, the worst being 13
    ownership tests asserting a DENY and silently receiving an ALLOW. In the
    PR checks list a non-blocking green tick is indistinguishable from a
    blocking one. The failure was never that the leg could not fail the
    build; it was that nobody read it and the failures carried an unexamined
    label.

    So the check NAME carries the disclaimer, and these tests keep it there.
    The defect class that actually matters is caught by
    test_shell_bash32_portability.py, which runs on Linux in the BLOCKING job.
    """

    def _test_job(self) -> dict:
        return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["test"]

    def test_non_ubuntu_legs_are_labelled_informational(self):
        """The label is the fix. Without it the leg is a green tick that
        guarantees nothing, which is how this went wrong the first time."""
        name = " ".join(str(self._test_job()["name"]).split())
        assert "INFORMATIONAL" in name, (
            f"check name {name!r} does not mark the non-blocking legs — a "
            f"reader sees a green tick identical to a gating one"
        )
        assert "does not gate" in name, f"the disclaimer should say what it means: {name!r}"
        assert "ubuntu-latest" in name, (
            f"the label must be CONDITIONAL on the leg, or ubuntu — the real "
            f"gate — gets marked informational too: {name!r}"
        )

    def test_ubuntu_remains_the_gate(self):
        expr = str(self._test_job().get("continue-on-error", ""))
        assert "ubuntu-latest" in expr, expr

    def test_all_three_platforms_still_run(self):
        """Informational is not the same as absent. macOS stays so it cannot
        silently rot back to 27 failures; Windows stays so its ~155 remain
        visible and shrinkable."""
        oses = self._test_job()["strategy"]["matrix"]["os"]
        assert {"ubuntu-latest", "macos-latest", "windows-latest"} <= set(oses), oses
