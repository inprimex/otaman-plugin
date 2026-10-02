"""Generated per-repo Hook C CI (security-gates-hook-c 1.4).

deploy 1.3 owns the mechanism (reusable workflow + caller variants), core 1.1
owns policy resolution. This module is the join, and decides no policy itself.

THE OUTCOME THAT MATTERS MOST is `no-gates`: a repo whose config resolves to no
layers gets NO workflow. Emitting one anyway would give it a passing security
check that ran nothing — a surface reporting success for work it never did,
which is the failure the whole ladder exists to prevent.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from otaman_plugin.security_ci_generate import (
    GENERATED,
    NO_GATES,
    NO_VARIANT,
    OPT_OUT,
    generate_for_repo,
    languages_for,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = (
    Path(__file__).resolve().parent.parent.parent
    / "otaman-deploy"
    / "ce"
    / "ci-templates"
    / "security-gates"
)

PY_LANG = {
    "ci-fast": {"tools": ["gitleaks", "bandit", "pip-audit"], "timeout": 2},
    "ci-medium": {
        "tools": ["semgrep", "trivy", "osv-scanner", "licensee"],
        "timeout": 6,
        "scanner-pair": ["trivy", "osv-scanner"],
    },
    "ci-slow": {"tools": ["codeql"], "timeout": 30},
}
BLOCK = {"languages": {"python": PY_LANG, "shell": {"ci-fast": {"tools": ["shellcheck"]}}}}

#: True inside GitHub Actions, where every sibling this suite reads is checked
#: out on purpose.
_IN_CI = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"


@pytest.fixture
def _require_deploy_templates():
    """A cross-repo contract test must not SKIP SILENTLY in CI.

    These read otaman-deploy's Hook C templates. They used to carry a plain
    `skipif(not present)`, so when deploy added `{{ CI_*_TIMEOUT }}`
    placeholders the suite went red locally and CI stayed GREEN on the same
    commit — the gate reported a contract it had not checked, which is the
    no-silent-success shape this codebase keeps paying for.

    deploy is now checked out in the test job. So absence in CI is no longer
    "not available", it is "the checkout that was supposed to provide it did
    not" — a failure. Locally it still skips: a developer without the sibling
    should not be blocked by it.
    """
    if (TEMPLATES / "variants" / "python.yml").is_file():
        return
    if _IN_CI:
        pytest.fail(
            "otaman-deploy sibling is absent in CI, so this cross-repo contract "
            "test did NOT run. The test job checks it out deliberately — fix the "
            "checkout rather than letting the gate pass on an unchecked contract."
        )
    pytest.skip("otaman-deploy sibling checkout not present (local run)")


needs_templates = pytest.mark.usefixtures("_require_deploy_templates")


class TestTechToLanguage:
    @pytest.mark.parametrize(
        "tech,expected",
        [
            (["python", "bash"], ("python", "shell")),
            (["typescript", "react"], ("node",)),  # both map to node, deduped
            (["go"], ("go",)),
            (["docs", "mkdocs"], ()),
            (None, ()),
        ],
    )
    def test_mapping(self, tech, expected):
        langs, unknown = languages_for(tech)
        assert langs == expected and unknown == ()

    def test_unknown_tech_is_returned_not_dropped(self):
        """A `tech: [rust]` repo generating no gates must be distinguishable
        from one correctly configured, or the vocabulary gap never surfaces."""
        langs, unknown = languages_for(["python", "rust", "cobol"])
        assert langs == ("python",)
        assert unknown == ("rust", "cobol")

    def test_non_code_tech_is_known_and_empty_not_unknown(self):
        """A docs repo is a deliberate no-language, not a gap to fix."""
        langs, unknown = languages_for(["docs", "yaml", "markdown"])
        assert langs == () and unknown == ()

    def test_case_and_whitespace_tolerated(self):
        assert languages_for([" Python ", "BASH"])[0] == ("python", "shell")


@needs_templates
class TestOutcomesStayDistinct:
    def test_generated_writes_a_workflow(self):
        r = generate_for_repo({"name": "p", "tech": ["python"]}, BLOCK, TEMPLATES)
        assert r.outcome == GENERATED and r.wrote_workflow

    def test_opt_out_writes_nothing_and_states_why(self):
        """The spec requires the skip be VISIBLE."""
        block = {**BLOCK, "repos": {"d": {"opt-out": True}}}
        r = generate_for_repo({"name": "d", "tech": ["docs"]}, block, TEMPLATES)
        assert r.outcome == OPT_OUT
        assert not r.wrote_workflow
        assert "opted out" in r.reason

    def test_no_gates_writes_nothing_and_says_why(self):
        """THE one that matters: a workflow with no layers is a green check
        that gates nothing."""
        r = generate_for_repo({"name": "x", "tech": ["python"]}, {}, TEMPLATES)
        assert r.outcome == NO_GATES
        assert not r.wrote_workflow
        assert "gates nothing" in r.reason

    def test_opt_out_and_no_gates_are_different_outcomes(self):
        """Both write no workflow. doctor must tell 'opted out' from 'never
        configured' — deploy's contract says so explicitly."""
        opted = generate_for_repo(
            {"name": "d", "tech": ["python"]},
            {**BLOCK, "repos": {"d": {"opt-out": True}}},
            TEMPLATES,
        )
        unconfigured = generate_for_repo({"name": "u", "tech": ["python"]}, {}, TEMPLATES)
        assert opted.outcome != unconfigured.outcome
        assert not opted.wrote_workflow and not unconfigured.wrote_workflow

    def test_language_without_a_variant_is_not_invented(self):
        """shell has defaults but deploy ships no shell variant. Rendering a
        variant I made up would put a template outside its owner's repo."""
        block = {"languages": {"shell": {"ci-fast": {"tools": ["shellcheck"]}}}}
        r = generate_for_repo({"name": "s", "tech": ["bash"]}, block, TEMPLATES)
        assert r.outcome == NO_VARIANT
        assert not r.wrote_workflow
        assert "shell" in r.unsupported_languages


@needs_templates
class TestRendering:
    def _wf(self, repo_tech=("python",), block=None):
        r = generate_for_repo({"name": "p", "tech": list(repo_tech)}, block or BLOCK, TEMPLATES)
        return r.workflow

    def test_output_is_valid_yaml(self):
        assert yaml.safe_load(self._wf())["jobs"]

    def test_no_placeholder_survives(self):
        """An unsubstituted {{ }} reaches CI as a literal and fails opaquely."""
        assert "{{" not in self._wf()

    def test_resolved_tools_are_substituted(self):
        doc = yaml.safe_load(self._wf())
        assert doc["jobs"]["ci-fast"]["with"]["tools"] == "gitleaks,bandit,pip-audit"

    def test_the_scanner_pair_is_carried(self):
        """The 2-of-3 rule's recorded pair makes the omitted third visible."""
        doc = yaml.safe_load(self._wf())
        assert doc["jobs"]["ci-medium"]["with"]["scanner_pair"] == "trivy,osv-scanner"

    def test_mixed_language_tools_are_unioned(self):
        doc = yaml.safe_load(self._wf(repo_tech=("python", "bash")))
        assert "shellcheck" in doc["jobs"]["ci-fast"]["with"]["tools"]

    def test_resolved_timeouts_are_substituted(self):
        """deploy added the placeholders (their half of the seam gap); core
        resolves `timeout` in SECONDS and deploy's field is `timeout_seconds`,
        so this passes through with NO conversion."""
        doc = yaml.safe_load(self._wf())
        # deploy quotes the placeholder, so YAML yields a string; Actions
        # coerces it for the `type: number` input.
        assert str(doc["jobs"]["ci-fast"]["with"]["timeout_seconds"]) == "2"
        assert str(doc["jobs"]["ci-medium"]["with"]["timeout_seconds"]) == "6"

    def test_the_seconds_value_is_not_converted(self):
        """core warned the hazard explicitly: with a minutes-named field,
        seconds would be written as minutes — 300s becoming 300 minutes,
        silently. Pin that the resolved number arrives unchanged."""
        block = {
            "languages": {
                "python": {"ci-fast": {"tools": ["x"], "timeout": 300}},
            }
        }
        doc = yaml.safe_load(self._wf(block=block))
        assert str(doc["jobs"]["ci-fast"]["with"]["timeout_seconds"]) == "300"

    def test_an_unset_timeout_renders_the_sentinel_zero_not_empty(self):
        """0 is deploy's sentinel: their job does
        `timeout_seconds > 0 && convert || timeout_minutes`, so 0 selects the
        template's own fallback. An empty string would be an invalid value for
        a `type: number` input and fail the workflow at run time — I had it
        empty first and read their reusable workflow to check."""
        block = {"languages": {"python": {"ci-fast": {"tools": ["x"]}}}}
        doc = yaml.safe_load(self._wf(block=block))
        assert str(doc["jobs"]["ci-fast"]["with"]["timeout_seconds"]) == "0"

    def test_ci_slow_is_omitted_entirely_not_emitted_disabled(self):
        """deploy's contract: an advisory job nobody asked for burns minutes on
        every PR and gets ignored, which trains people to ignore the blocking
        ones. Omitted, not present-and-false."""
        wf = self._wf()
        doc = yaml.safe_load(wf)
        assert "ci-slow" not in doc["jobs"]
        assert "ci-slow:" not in wf

    def test_a_repo_that_DID_opt_in_gets_ci_slow(self):
        """The other direction, and the one whose absence let an inversion
        ship. core corrected `opt_in` from "this is an opt-in LAYER" (monotonic
        from the language default) to "this REPO opted in" — the fix to the gap
        this generator surfaced. Under the old reading the code said
        `not slow.opt_in`, which was safe while opt_in was always True and
        became "emit ci-slow for everyone who did NOT opt in" the moment the
        semantics were corrected.

        Testing only the omit side could never catch that, because both
        readings omit when nothing opts in.
        """
        block = {
            "languages": {"python": PY_LANG},
            "repos": {"p": {"ci-slow": {"opt-in": True}}},
        }
        r = generate_for_repo({"name": "p", "tech": ["python"]}, block, TEMPLATES)
        doc = yaml.safe_load(r.workflow)
        assert "ci-slow" in doc["jobs"], "a repo that opted in did not get the job"
        assert doc["jobs"]["ci-slow"]["if"] == "true"

    def test_opting_in_and_not_produce_different_workflows(self):
        """Guard the distinction itself rather than either branch."""
        base = {"languages": {"python": PY_LANG}}
        out = generate_for_repo({"name": "p", "tech": ["python"]}, base, TEMPLATES).workflow
        opted = generate_for_repo(
            {"name": "p", "tech": ["python"]},
            {**base, "repos": {"p": {"ci-slow": {"opt-in": True}}}},
            TEMPLATES,
        ).workflow
        assert out != opted
        assert "ci-slow:" not in out and "ci-slow:" in opted

    def test_dropping_ci_slow_leaves_the_other_jobs_intact(self):
        """A line-based removal that ate the next job would be worse than
        leaving the job in."""
        doc = yaml.safe_load(self._wf())
        assert set(doc["jobs"]) == {"ci-fast", "ci-medium"}
        assert doc["jobs"]["ci-medium"]["needs"] == "ci-fast"

    def test_blocking_flags_survive_the_render(self):
        doc = yaml.safe_load(self._wf())
        assert doc["jobs"]["ci-fast"]["with"]["blocking"] is True
        assert doc["jobs"]["ci-medium"]["with"]["blocking"] is True


@needs_templates
class TestPolicyIsNotDecidedHere:
    def test_no_tool_names_are_hardcoded_in_the_module(self):
        """Policy lives in config. A tool id in this module would be a second
        home for the rule, and the second one is the broken one."""
        import otaman_plugin.security_ci_generate as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        for tool in ("gitleaks", "semgrep", "trivy", "bandit", "codeql", "osv-scanner"):
            assert tool not in src, f"{tool} hardcoded in the generator"

    def test_tools_come_from_the_config_not_the_template_defaults(self):
        """The variant ships default tool ids as comments/placeholders; the
        rendered values must be the RESOLVED ones."""
        block = {"languages": {"python": {"ci-fast": {"tools": ["only-this-one"]}}}}
        r = generate_for_repo({"name": "p", "tech": ["python"]}, block, TEMPLATES)
        doc = yaml.safe_load(r.workflow)
        assert doc["jobs"]["ci-fast"]["with"]["tools"] == "only-this-one"


class TestTheSkipCannotGoSilentInCI:
    """The blind spot itself, guarded.

    These contract tests read otaman-deploy. They carried a plain
    `skipif(not present)`, and CI did not check deploy out — so when deploy
    added `{{ CI_*_TIMEOUT }}` placeholders, the suite went red locally and CI
    stayed GREEN on the same commit. The gate reported a contract it had never
    checked.

    Two halves to the fix. Deploy is now checked out in the test job (so these
    run), and absence in CI is a FAILURE rather than a skip (so a broken
    checkout cannot quietly reopen the hole).
    """

    @staticmethod
    def _decide(present: bool, in_ci: bool) -> str:
        """The fixture's decision, isolated so it can be exercised directly.

        Mirrors `_require_deploy_templates`; `test_the_fixture_uses_this_rule`
        below pins the two together so this cannot drift into testing itself.
        """
        if present:
            return "ran"
        return "failed" if in_ci else "skipped"

    def test_absent_in_CI_is_a_failure_not_a_skip(self):
        assert self._decide(present=False, in_ci=True) == "failed"

    def test_absent_locally_still_skips(self):
        """A developer without the sibling must not be blocked by it."""
        assert self._decide(present=False, in_ci=False) == "skipped"

    def test_present_runs_either_way(self):
        assert self._decide(present=True, in_ci=True) == "ran"
        assert self._decide(present=True, in_ci=False) == "ran"

    def test_the_fixture_uses_this_rule(self):
        """Guard against the mirror drifting from the real fixture."""
        import inspect

        src = inspect.getsource(_require_deploy_templates)
        assert "pytest.fail(" in src and "_IN_CI" in src
        assert "pytest.skip(" in src
        assert src.index("pytest.fail(") < src.index("pytest.skip("), (
            "the CI branch must be decided before the local skip"
        )

    def test_ci_checks_deploy_out_so_the_tests_actually_run(self):
        """The other half. Without it, the guard above would just convert a
        silent skip into a loud failure on every CI run."""
        import yaml as _yaml

        wf = _yaml.safe_load(
            (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        )
        repos = [
            s.get("with", {}).get("repository", "")
            for s in wf["jobs"]["test"]["steps"]
            if isinstance(s, dict)
        ]
        assert "inprimex/otaman-deploy" in repos, (
            "the test job does not check out otaman-deploy, so these contract "
            "tests cannot run in CI"
        )
