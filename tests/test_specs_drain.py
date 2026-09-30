"""SessionStart drain for the specs owner (task-complete-reconciler 2.1).

`otaman complete` files a task-complete on the bus, but only the specs owner's
tasks.md edit survives the next `git pull --ff-only`. Nothing made that owner
reconcile, so filings piled up unseen: ~2 weeks of them on pmeets, the lens
reporting 5/11 against a real 11/11, and no surface saying so.

D2 — the hook drains, the verb is the engine. These tests cover what the hook
must decide before calling `otaman spec sweep`: whether this agent may write,
and how every outcome is reported. The sweep itself is cli's, tested there.

THE CENTRAL PROPERTY: a drain that found nothing owed and a drain that could
not run both apply zero ticks. Conflating them is the exact blindness this
change removes, so every path returns its own verdict and `not-checked` is
never a pass.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from otaman_plugin import specs_drain as sd

REPO = Path(__file__).resolve().parent.parent


def _config(specs_path="../specs", owner="spec-agent", with_specs=True):
    cfg = {
        "repos": [
            {"name": "backend", "path": "./backend", "owner": "dev-agent"},
            {"name": "specs", "path": specs_path, "owner": owner},
        ]
    }
    if with_specs:
        cfg["specs"] = {"path": specs_path, "format": "openspec"}
    return cfg


class TestOwnerResolution:
    def test_resolves_from_specs_path(self):
        assert sd.resolve_specs_owner(_config()) == "spec-agent"

    def test_resolves_a_program_whose_specs_live_elsewhere(self):
        """Hardcoding 'spec-agent' would name an agent absent from that fleet,
        and the drain would then be skipped for everyone, silently."""
        cfg = _config(specs_path="../rules", owner="rules-agent")
        assert sd.resolve_specs_owner(cfg) == "rules-agent"

    def test_no_specs_block_is_none_not_a_guess(self):
        assert sd.resolve_specs_owner({"repos": []}) is None

    def test_specs_path_matching_no_repo_is_none(self):
        cfg = _config()
        cfg["specs"]["path"] = "../nowhere"
        assert sd.resolve_specs_owner(cfg) is None

    def test_repo_without_owner_does_not_match(self):
        cfg = {"specs": {"path": "../s"}, "repos": [{"name": "s", "path": "../s"}]}
        assert sd.resolve_specs_owner(cfg) is None

    def test_malformed_specs_block_does_not_raise(self):
        assert sd.resolve_specs_owner({"specs": "../s", "repos": []}) is None


class TestTheOwnerGate:
    def test_non_owner_is_skipped(self, tmp_path):
        r = sd.drain("plugin-agent", _config(), tmp_path)
        assert r.verdict == sd.NOT_OWNER
        assert "plugin-agent" in r.reason and "spec-agent" in r.reason

    def test_unknown_agent_is_skipped_not_assumed_owner(self, tmp_path):
        """An unresolved identity must never be treated as the owner — that
        would have every agent sweeping."""
        r = sd.drain(None, _config(), tmp_path)
        assert r.verdict == sd.NOT_OWNER

    def test_unresolvable_owner_is_not_checked_not_skipped(self, tmp_path):
        """The distinction that matters: 'you are not the owner' is a normal
        outcome, 'nobody could be identified as owner' means the drain will
        NEVER run for anyone and must not hide inside the common case."""
        r = sd.drain("spec-agent", {"repos": []}, tmp_path)
        assert r.verdict == sd.NO_OWNER_RESOLVED
        assert r.verdict in sd.NOT_CHECKED
        assert not r.performed


class TestDegradation:
    def test_no_otaman_on_path_is_not_checked(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sd.shutil, "which", lambda _: None)
        r = sd.drain("spec-agent", _config(), tmp_path)
        assert r.verdict == sd.NO_CLI
        assert not r.performed

    def test_bundle_without_the_sweep_is_not_checked_and_says_so(self, tmp_path, monkeypatch):
        """The installed bundle lags the checkout by design. An old bundle is
        expected — silently not draining because of it is not."""
        monkeypatch.setattr(sd.shutil, "which", lambda _: "/usr/bin/otaman")
        monkeypatch.setattr(sd, "sweep_supported", lambda _: False)
        r = sd.drain("spec-agent", _config(), tmp_path)
        assert r.verdict == sd.SWEEP_UNAVAILABLE
        assert not r.performed
        assert "upgrade" in r.reason

    def test_sweep_supported_reads_the_action_list(self, monkeypatch):
        def fake(*a, **k):
            return subprocess.CompletedProcess(a, 0, "status|gate|approve|reconcile|sweep", "")

        monkeypatch.setattr(sd.subprocess, "run", fake)
        assert sd.sweep_supported("/usr/bin/otaman") is True

    def test_sweep_unsupported_when_absent_from_the_action_list(self, monkeypatch):
        def fake(*a, **k):
            return subprocess.CompletedProcess(a, 0, "status|gate|approve|reconcile", "")

        monkeypatch.setattr(sd.subprocess, "run", fake)
        assert sd.sweep_supported("/usr/bin/otaman") is False

    def test_probe_failure_is_unsupported_not_a_crash(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("no exec")

        monkeypatch.setattr(sd.subprocess, "run", boom)
        assert sd.sweep_supported("/usr/bin/otaman") is False


class TestOutcomesStayDistinct:
    """no-silent-success clause 1, applied to the thing this change is about."""

    def _run_with(self, monkeypatch, rc=0, out="", raises=None):
        monkeypatch.setattr(sd.shutil, "which", lambda _: "/usr/bin/otaman")
        monkeypatch.setattr(sd, "sweep_supported", lambda _: True)

        def fake(*a, **k):
            if raises:
                raise raises
            return subprocess.CompletedProcess(a, rc, out, "")

        monkeypatch.setattr(sd.subprocess, "run", fake)

    def test_nothing_owed_is_its_own_verdict(self, tmp_path, monkeypatch):
        self._run_with(monkeypatch, out="  Nothing owed: 4 change(s) checked")
        r = sd.drain("spec-agent", _config(), tmp_path)
        assert r.verdict == sd.NOTHING_OWED
        assert r.performed, "a sweep that ran and found nothing DID run"

    def test_applied_ticks_is_its_own_verdict(self, tmp_path, monkeypatch):
        self._run_with(monkeypatch, out="  Applied 7 tick(s) across 2 change(s).")
        r = sd.drain("spec-agent", _config(), tmp_path)
        assert r.verdict == sd.DRAINED

    def test_nothing_owed_differs_from_could_not_run(self, tmp_path, monkeypatch):
        """Both apply zero ticks. If they shared a verdict, the pmeets backlog
        would be invisible all over again."""
        self._run_with(monkeypatch, out="  Nothing owed: 0 change(s) checked")
        ran = sd.drain("spec-agent", _config(), tmp_path)
        monkeypatch.setattr(sd, "sweep_supported", lambda _: False)
        could_not = sd.drain("spec-agent", _config(), tmp_path)
        assert ran.verdict != could_not.verdict
        assert ran.performed and not could_not.performed

    def test_nonzero_exit_is_a_failure_not_a_quiet_pass(self, tmp_path, monkeypatch):
        self._run_with(monkeypatch, rc=1, out="  NOT CHECKED — stale bundle")
        r = sd.drain("spec-agent", _config(), tmp_path)
        assert r.verdict == sd.FAILED
        assert "1" in r.reason

    def test_timeout_is_a_failure(self, tmp_path, monkeypatch):
        self._run_with(monkeypatch, raises=subprocess.TimeoutExpired("otaman", 120))
        r = sd.drain("spec-agent", _config(), tmp_path)
        assert r.verdict == sd.FAILED

    def test_oserror_is_a_failure(self, tmp_path, monkeypatch):
        self._run_with(monkeypatch, raises=OSError("boom"))
        r = sd.drain("spec-agent", _config(), tmp_path)
        assert r.verdict == sd.FAILED

    def test_every_verdict_is_unique(self):
        verdicts = [
            sd.DRAINED,
            sd.NOTHING_OWED,
            sd.NOT_OWNER,
            sd.NO_OWNER_RESOLVED,
            sd.SWEEP_UNAVAILABLE,
            sd.NO_CLI,
            sd.FAILED,
        ]
        assert len(set(verdicts)) == len(verdicts)


class TestTheSweepIsInvokedCorrectly:
    def test_apply_is_passed_or_nothing_is_written(self, tmp_path, monkeypatch):
        """Without --apply the sweep is a dry run: the drain would report
        success having changed nothing."""
        seen = {}
        monkeypatch.setattr(sd.shutil, "which", lambda _: "/usr/bin/otaman")
        monkeypatch.setattr(sd, "sweep_supported", lambda _: True)

        def fake(cmd, *a, **k):
            seen["cmd"] = cmd
            seen["env"] = k.get("env") or {}
            return subprocess.CompletedProcess(cmd, 0, "Applied 1 tick(s)", "")

        monkeypatch.setattr(sd.subprocess, "run", fake)
        sd.drain("spec-agent", _config(), tmp_path)
        assert seen["cmd"][1:] == ["spec", "sweep", "--apply"]

    def test_runs_as_the_owner_identity(self, tmp_path, monkeypatch):
        """core's actualize_tasks gates the write on the acting identity; a
        drain running under someone else's OTAMAN_AGENT writes nothing."""
        seen = {}
        monkeypatch.setattr(sd.shutil, "which", lambda _: "/usr/bin/otaman")
        monkeypatch.setattr(sd, "sweep_supported", lambda _: True)

        def fake(cmd, *a, **k):
            seen["env"] = k.get("env") or {}
            return subprocess.CompletedProcess(cmd, 0, "Nothing owed", "")

        monkeypatch.setattr(sd.subprocess, "run", fake)
        sd.drain("spec-agent", _config(), tmp_path)
        assert seen["env"].get("OTAMAN_AGENT") == "spec-agent"


class TestHookWiring:
    def test_hook_is_wired_into_session_start(self):
        d = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        cmds = [
            h.get("command", "")
            for e in d.get("hooks", d)["SessionStart"]
            for h in e.get("hooks", [])
        ]
        assert any("session-start-specs-drain.sh" in c for c in cmds)

    def test_hook_script_exists_and_parses(self):
        hook = REPO / "hooks" / "session-start-specs-drain.sh"
        assert hook.is_file()
        rc = subprocess.run(["bash", "-n", str(hook)], capture_output=True)
        assert rc.returncode == 0, rc.stderr.decode()

    def test_hook_never_blocks_a_session(self):
        """A backlog that cannot be drained must not stop Claude from starting."""
        body = (REPO / "hooks" / "session-start-specs-drain.sh").read_text(encoding="utf-8")
        assert body.rstrip().endswith("exit 0")

    def test_shim_exists_and_is_thin(self):
        shim = REPO / "scripts" / "specs-drain.py"
        assert shim.is_file()
        body = shim.read_text(encoding="utf-8")
        assert "from otaman_plugin.specs_drain import drain" in body


class TestLivenessCoverage:
    """2.1 requires hook_liveness coverage so an inert drain fails install
    rather than regressing silently to LLM-memory."""

    def test_drain_hook_is_liveness_checked(self):
        from otaman_plugin.hook_liveness import LIVENESS_CHECKED_HOOKS

        assert "session-start-specs-drain.sh" in LIVENESS_CHECKED_HOOKS

    def test_the_drain_hook_is_actually_live(self):
        from otaman_plugin.hook_liveness import locate_hook, probe_hook_liveness

        v = probe_hook_liveness(locate_hook(REPO / "scripts", "session-start-specs-drain.sh"))
        assert v.state == "live", v.reason

    def test_locate_hook_finds_hooks_dir_residents(self):
        from otaman_plugin.hook_liveness import locate_hook

        p = locate_hook(REPO / "scripts", "session-start-specs-drain.sh")
        assert p.parent.name == "hooks" and p.is_file()

    def test_locate_hook_still_finds_scripts_dir_residents(self):
        from otaman_plugin.hook_liveness import locate_hook

        p = locate_hook(REPO / "scripts", "post-commit-hook.sh")
        assert p.parent.name == "scripts" and p.is_file()

    def test_a_missing_hook_still_reports_missing(self, tmp_path):
        """The locator must not turn an absent hook into a silent skip."""
        from otaman_plugin.hook_liveness import locate_hook, probe_hook_liveness

        (tmp_path / "scripts").mkdir()
        v = probe_hook_liveness(locate_hook(tmp_path / "scripts", "nope.sh"))
        assert v.state == "inert" and "not installed" in v.reason

    def test_hooks_dir_resident_without_resolve_sh_is_inert(self, tmp_path):
        """The haulops shape, for a hooks/-resident script: entry point
        present, dependency absent."""
        from otaman_plugin.hook_liveness import probe_hook_liveness

        (tmp_path / "hooks").mkdir()
        (tmp_path / "scripts").mkdir()
        hook = tmp_path / "hooks" / "h.sh"
        hook.write_text("source ../scripts/_resolve.sh\n")
        v = probe_hook_liveness(hook)
        assert v.state == "inert", v.reason


@pytest.mark.parametrize("verdict", [sd.NO_OWNER_RESOLVED, sd.SWEEP_UNAVAILABLE, sd.NO_CLI])
def test_not_checked_verdicts_are_never_performed(verdict):
    assert not sd.DrainResult(verdict, "x").performed
