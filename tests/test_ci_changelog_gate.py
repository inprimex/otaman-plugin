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
