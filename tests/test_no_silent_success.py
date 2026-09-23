"""no-silent-success 1.1 + 1.2 — the two named open instances.

1.1 A hook that EXISTS is not a hook that RUNS. haulops had post-commit,
    spec-change and check-branch all installed, readable and executable —
    and all inert, because the wheel shipped the entry points without
    `_resolve.sh`, which every one of them sources. Install said success;
    doctor said nothing; nothing dispatched for weeks.

1.2 map-tasks conflated "no otaman root" with "nothing to do", and exited 0
    on runs that dispatched nothing — including the haulops case where a
    task ANNOTATED for a repo silently resolved to no owner.

Per the delta's third requirement, a guard verified only on clean code is
not enforcement — so every check here is exercised with the defect
deliberately present, not just absent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "src"))

from otaman_plugin.doctor_checks import check_installed_hooks_are_live  # noqa: E402
from otaman_plugin.hook_liveness import probe_hook_liveness  # noqa: E402

SCRIPT = REPO / "scripts" / "map-tasks.py"


# --------------------------------------------------------------------------
# 1.1 — hook liveness
# --------------------------------------------------------------------------


def _hook_dir(tmp_path: Path, *, with_resolve: bool) -> Path:
    d = tmp_path / "scripts"
    d.mkdir()
    shutil.copy(REPO / "scripts" / "post-commit-hook.sh", d / "post-commit-hook.sh")
    if with_resolve:
        shutil.copy(REPO / "scripts" / "_resolve.sh", d / "_resolve.sh")
    return d


class TestHookLiveness:
    def test_a_complete_install_is_live(self, tmp_path):
        v = probe_hook_liveness(_hook_dir(tmp_path, with_resolve=True) / "post-commit-hook.sh")
        assert v.ok and v.performed and v.state == "live"

    def test_the_haulops_shape_is_inert_not_ok(self, tmp_path):
        """Entry point present, dependency absent — exactly what shipped."""
        v = probe_hook_liveness(_hook_dir(tmp_path, with_resolve=False) / "post-commit-hook.sh")
        assert v.ok is False
        assert v.performed is True
        assert v.state == "inert"
        assert "_resolve.sh" in v.reason and "inert" in v.reason

    def test_a_missing_hook_is_a_failure_not_a_pass(self, tmp_path):
        v = probe_hook_liveness(tmp_path / "nope.sh")
        assert v.ok is False and v.performed is True

    def test_unperformable_check_is_its_own_state(self, tmp_path, monkeypatch):
        """The delta is explicit: a check that could not run renders as its
        own visible state, never OK and never silence."""
        monkeypatch.setattr(shutil, "which", lambda _n: None)
        v = probe_hook_liveness(_hook_dir(tmp_path, with_resolve=True) / "post-commit-hook.sh")
        assert v.performed is False
        assert v.state == "not-checked"
        assert v.ok is False, "not-checked must never read as OK"


class TestDoctorSurfacesInertHooks:
    def test_healthy_tree_reports_nothing(self):
        assert check_installed_hooks_are_live(REPO) == []

    def test_inert_install_is_an_error_finding(self, tmp_path, monkeypatch):
        import otaman_plugin.doctor_checks as dc

        monkeypatch.setattr(
            dc, "_plugin_scripts_dir", lambda: _hook_dir(tmp_path, with_resolve=False)
        )
        found = dc.check_installed_hooks_are_live(tmp_path)
        assert found, "an inert hook rendered as silence — the defect itself"
        assert any(w.severity == "error" and w.code == "NSS1_HOOK_INERT" for w in found)
        assert all(w.hint for w in found), "a failure must name the fix"

    def test_the_check_is_registered_in_run_all_checks(self, tmp_path, monkeypatch):
        """An unregistered check never runs, so testing it directly proves
        nothing about doctor. Found by reintroducing the defect: deleting the
        `out.extend(...)` line broke no test until this one existed — the
        vacuous-guard case the delta's third requirement is about."""
        import otaman_plugin.doctor_checks as dc

        called: list[str] = []
        monkeypatch.setattr(
            dc, "check_installed_hooks_are_live", lambda root: called.append("yes") or []
        )
        monkeypatch.setattr(dc, "check_plugin_dir_consistency", lambda root: [])
        monkeypatch.setattr(dc, "check_launch_commands_have_continue_flag", lambda root: [])
        dc.run_all_checks(tmp_path)
        assert called == ["yes"], "hook-liveness check is not wired into run_all_checks"

    def test_cannot_locate_scripts_is_not_checked_not_ok(self, tmp_path, monkeypatch):
        import otaman_plugin.doctor_checks as dc

        monkeypatch.setattr(dc, "_plugin_scripts_dir", lambda: None)
        found = dc.check_installed_hooks_are_live(tmp_path)
        assert [w.code for w in found] == ["NSS1_HOOK_LIVENESS_NOT_CHECKED"]


class TestInstallRefusesToClaimAnInertHook:
    def test_install_errors_rather_than_reporting_success(self, tmp_path, monkeypatch):
        import otaman_plugin.generate_agent_config as gac

        hook = _hook_dir(tmp_path, with_resolve=False) / "post-commit-hook.sh"
        monkeypatch.setattr(gac, "_find_plugin_script", lambda _p: hook)
        results = gac.install_repo_post_commit_hooks(tmp_path, {"repos": []})
        blob = "\n".join(results)
        assert "ERROR" in blob
        assert "inert" in blob
        assert "refusing to report" in blob


# --------------------------------------------------------------------------
# 1.2 — map-tasks outcomes
# --------------------------------------------------------------------------


def _run_map_tasks(body: str, *, root: bool = True, stage: str = "spec-approved"):
    # .resolve() is load-bearing on macOS, not tidiness. `mkdtemp()` hands back
    # /var/folders/... while /var is a symlink to /private/var, so core's marker
    # security check — which resolves the marker before comparing it to $HOME —
    # sees /private/var/... , decides the marker points outside $HOME, and
    # rejects it. Every assertion in this file then measures that rejection
    # instead of the dispatch outcome under test. pytest's own `tmp_path` is
    # already resolved, which is why the tmp_path-based suites never saw this.
    t = Path(tempfile.mkdtemp()).resolve()
    meta = t / "p-otaman"
    (meta / ".agents" / "bus" / "active").mkdir(parents=True)
    (meta / "platform.yaml").write_text(
        yaml.safe_dump(
            {
                "project": "p",
                "spec_policy": {"enforcement": "block"},
                "repos": [{"name": "otaman-plugin", "path": "../x", "owner": "plugin-agent"}],
            }
        ),
        encoding="utf-8",
    )
    specs = t / "p-specs"
    change = specs / "openspec" / "changes" / "demo"
    change.mkdir(parents=True)
    if root:
        (specs / ".otaman").write_text("../p-otaman\nagent: spec-agent\n", encoding="utf-8")
    (change / ".openspec.yaml").write_text(yaml.safe_dump({"stage": stage}), encoding="utf-8")
    (change / "tasks.md").write_text(body, encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": str(REPO / "src"), "HOME": str(t)}
    env.pop("OTAMAN_ROOT", None)
    env.pop("MAESTRO_ROOT", None)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(change / "tasks.md")],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    try:
        report = json.loads(proc.stdout)
    except Exception:
        report = {}
    return proc, report, meta


class TestTheSandboxItselfIsSound:
    """A guard on the fixture, not the feature.

    Every assertion in this file reads an exit code from map-tasks. If the
    sandbox's marker is rejected before map-tasks gets to decide anything, the
    whole file measures the rejection and still *looks* like it is testing
    dispatch outcomes — it just reports the wrong one everywhere. That is how 9
    tests here failed on macOS while passing on Linux: `mkdtemp()` returns
    /var/folders/... , /var is a symlink to /private/var, and core resolves the
    marker before comparing it to $HOME.

    Asserting the rejection is absent catches that on ANY platform, so the next
    person to drop the `.resolve()` fails locally rather than in a macOS-only
    CI job nobody blocks on.
    """

    def test_the_marker_is_not_rejected_before_the_test_begins(self):
        proc, _, _ = _run_map_tasks("- [ ] 1.1 @otaman-plugin do it\n")
        assert "resolves outside $HOME" not in proc.stderr, (
            "the sandbox marker was rejected for security, so every exit code "
            "in this file describes that rejection rather than a dispatch outcome"
        )


class TestOutcomesAreDistinct:
    def test_root_not_found_is_its_own_exit_code(self):
        """ "Not found" and "found nothing to do" must be distinguishable."""
        proc, _, _ = _run_map_tasks("- [ ] 1.1 @otaman-plugin do it\n", root=False)
        assert proc.returncode == 3
        assert "no otaman root found" in proc.stderr
        assert "Nothing was dispatched" in proc.stderr

    def test_root_error_names_the_right_file(self):
        """It used to say ownership.json; the resolver looks for the otaman
        root via the .otaman marker. The misdirection cost real debugging."""
        proc, _, _ = _run_map_tasks("- [ ] 1.1 @otaman-plugin x\n", root=False)
        assert "ownership.json" not in proc.stderr
        assert ".otaman marker" in proc.stderr

    def test_no_tasks_is_stated_zero_work_not_an_error(self):
        proc, report, _ = _run_map_tasks("# Tasks\n\nprose only\n")
        assert proc.returncode == 0
        assert report["outcome"] == "no-tasks-in-file"
        assert "0 dispatched" in proc.stderr

    def test_nothing_to_dispatch_is_stated(self):
        proc, report, _ = _run_map_tasks("- [ ] 1.1 a plain line\n")
        assert proc.returncode == 0
        assert report["outcome"] == "nothing-to-dispatch"
        assert "0 dispatched" in proc.stderr

    def test_successful_dispatch_carries_counts(self):
        proc, report, meta = _run_map_tasks("- [ ] 1.1 @otaman-plugin do it\n")
        assert proc.returncode == 0
        assert report["outcome"] == "dispatched"
        assert report["dispatched"] == 1
        assert "1 dispatched to 1 agent(s)" in proc.stderr
        assert len(list((meta / ".agents" / "bus" / "active").glob("*.md"))) == 1


class TestDropsAreErrorsNotOmissions:
    BODY = "- [ ] 1.1 @otaman-haulops-firmware do it\n"

    def test_annotated_but_unresolvable_is_an_error(self):
        """The haulops silence: annotated for a repo that resolves to nobody,
        previously skipped without a word and exit 0."""
        proc, report, _ = _run_map_tasks(self.BODY)
        assert proc.returncode == 5
        assert report["outcome"] == "drops"
        assert report["dropped"] == 1

    def test_the_drop_is_named_with_a_fix(self):
        proc, _, _ = _run_map_tasks(self.BODY)
        assert "@otaman-haulops-firmware" in proc.stderr
        assert "NOT dispatched" in proc.stderr
        assert "platform.yaml repos[]" in proc.stderr

    def test_an_unannotated_line_is_not_a_drop(self):
        """Not everything unassigned is lost work — a plain checklist line is
        legitimately nobody's, and calling it a drop would cry wolf."""
        _, report, _ = _run_map_tasks("- [ ] 1.1 a plain line\n")
        assert report["dropped"] == 0

    @pytest.mark.parametrize(
        "body,expected",
        [
            ("- [ ] 1.1 @otaman-plugin ok\n", 0),
            ("- [ ] 1.1 @otaman-nope bad\n", 5),
        ],
    )
    def test_mixed_signal_exit_codes(self, body, expected):
        proc, _, _ = _run_map_tasks(body)
        assert proc.returncode == expected
