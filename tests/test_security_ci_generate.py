"""Generated per-repo Hook C CI (security-gates-hook-c 1.4).

deploy 1.3 owns the mechanism (reusable workflow + caller variants), core 1.1
owns policy resolution. This module is the join, and decides no policy itself.

THE OUTCOME THAT MATTERS MOST is `no-gates`: a repo whose config resolves to no
layers gets NO workflow. Emitting one anyway would give it a passing security
check that ran nothing — a surface reporting success for work it never did,
which is the failure the whole ladder exists to prevent.
"""

from __future__ import annotations

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

needs_templates = pytest.mark.skipif(
    not (TEMPLATES / "variants" / "python.yml").is_file(),
    reason="otaman-deploy sibling checkout with 1.3 templates not present",
)


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
