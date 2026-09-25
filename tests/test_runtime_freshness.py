"""session-runtime-freshness 1.1 — checks 1-3.

The defect this exists to remove: on 2026-09-17 thirteen fleet sessions
booted at 15:5xZ; the vendored plugin tree's `hooks.json` was rewritten five
days later. Every artifact on disk was correct the whole time, so every
file-inspecting doctor check stayed green while no running session had the
heartbeat hook. Proving it took reading `ps -o lstart=` against file mtimes
by hand.

The load-bearing test here is `test_editing_a_hook_script_body_does_not_flag`.
D3 makes the wiring-vs-script boundary part of the check's truth: hook script
bodies are read by bash at invocation and never make a session stale, so a
checker that flagged them would fire on every fleet session within a day and
teach operators to skip the section — reintroducing the invisibility it was
built to remove, through the fix itself.

Process enumeration is monkeypatched throughout. These tests assert the
VERDICT LOGIC; running them against real processes would make them a test of
whoever happens to be logged in.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import otaman_plugin.runtime_freshness as rf

DAY = 86400.0
SESSION_START = 1_000_000.0


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "platform.yaml").write_text(
        "project: t\nrunner:\n  agent_bootstrap:\n    plugin_dir: /plug\n"
        "    launch_commands:\n      - claude --continue\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def plugin_tree(tmp_path: Path) -> Path:
    d = tmp_path / "tree"
    (d / "hooks").mkdir(parents=True)
    (d / "scripts").mkdir(parents=True)
    (d / "hooks" / "hooks.json").write_text('{"hooks":{}}', encoding="utf-8")
    (d / "scripts" / "_resolve.sh").write_text("# body\n", encoding="utf-8")
    return d


def _fake_session(monkeypatch, *, pid=4242, start=SESSION_START, argv=None, tree=None):
    argv = argv or f"claude --continue --plugin-dir {tree} --mcp-config /m.json"
    # `_sessions_for` is the seam: it enumerates, then scopes to this program's
    # declared repos. Tests here assert verdict logic, so they patch past the
    # scoping; TestProgramScoping covers the scoping itself.
    monkeypatch.setattr(rf, "_sessions_for", lambda root: [pid])
    monkeypatch.setattr(rf, "_agent_pids", lambda: [pid])
    monkeypatch.setattr(rf, "_proc_start_epoch", lambda p: start)
    monkeypatch.setattr(rf, "_proc_argv", lambda p: argv)


def _touch(path: Path, when: float) -> None:
    import os

    os.utime(path, (when, when))


class TestCheck1SessionVsInputs:
    def test_input_modified_after_start_is_stale(self, monkeypatch, root, plugin_tree):
        _touch(root / "platform.yaml", SESSION_START - DAY)
        _touch(plugin_tree / "hooks" / "hooks.json", SESSION_START + DAY)
        _fake_session(monkeypatch, tree=plugin_tree)

        (f,) = rf.check_sessions_vs_inputs(root)
        assert f.verdict == "stale", f
        assert "hooks.json" in f.reason
        assert f.remedy and "elaunch" in f.remedy
        assert f.evidence["behind_seconds"] == int(DAY)

    def test_session_newer_than_every_input_is_fresh(self, monkeypatch, root, plugin_tree):
        _touch(root / "platform.yaml", SESSION_START - DAY)
        _touch(plugin_tree / "hooks" / "hooks.json", SESSION_START - DAY)
        _fake_session(monkeypatch, tree=plugin_tree)

        (f,) = rf.check_sessions_vs_inputs(root)
        assert f.verdict == "fresh", f

    def test_editing_a_hook_script_body_does_not_flag(self, monkeypatch, root, plugin_tree):
        """D3, and the reason this check is usable at all.

        Script bodies are read by bash at invocation — editing one changes what
        the NEXT tool call runs, not what the session snapshotted. Flagging it
        would mark every session on the fleet stale the moment anyone touched a
        hook, which is how a real signal gets trained out of an operator.
        """
        _touch(root / "platform.yaml", SESSION_START - DAY)
        _touch(plugin_tree / "hooks" / "hooks.json", SESSION_START - DAY)
        _touch(plugin_tree / "scripts" / "_resolve.sh", SESSION_START + 10 * DAY)
        _fake_session(monkeypatch, tree=plugin_tree)

        (f,) = rf.check_sessions_vs_inputs(root)
        assert f.verdict == "fresh", (
            "a hook SCRIPT edit made the session look stale — D3 says only inputs "
            "snapshotted at start count, and this one is read live"
        )

    def test_unenumerable_platform_is_not_checked_not_empty(self, monkeypatch, root):
        monkeypatch.setattr(rf, "_sessions_for", lambda r: None)
        (f,) = rf.check_sessions_vs_inputs(root)
        assert f.verdict == "not-checked"
        assert "could not check" in (f.remedy or "").lower()

    def test_no_sessions_running_is_silence_not_not_checked(self, monkeypatch, root):
        """`[]` and `None` from _agent_pids mean different things, and the
        distinction is the point: nothing to inspect vs could not inspect."""
        monkeypatch.setattr(rf, "_sessions_for", lambda r: [])
        assert rf.check_sessions_vs_inputs(root) == []

    def test_unreadable_start_time_is_not_checked(self, monkeypatch, root, plugin_tree):
        _fake_session(monkeypatch, tree=plugin_tree)
        monkeypatch.setattr(rf, "_proc_start_epoch", lambda p: None)
        (f,) = rf.check_sessions_vs_inputs(root)
        assert f.verdict == "not-checked"


class TestCheck2Argv:
    def test_missing_flag_is_definitive_staleness(self, monkeypatch, root, plugin_tree):
        _fake_session(monkeypatch, argv="claude --plugin-dir /t", tree=plugin_tree)
        (f,) = rf.check_session_argv(root)
        assert f.verdict == "stale"
        assert "--continue" in f.reason
        assert f.evidence["missing_flags"] == ["--continue"]

    def test_complete_argv_is_fresh(self, monkeypatch, root, plugin_tree):
        _fake_session(monkeypatch, argv="claude --continue --plugin-dir /t", tree=plugin_tree)
        (f,) = rf.check_session_argv(root)
        assert f.verdict == "fresh", f

    def test_no_declared_flags_is_not_checked(self, monkeypatch, tmp_path, plugin_tree):
        (tmp_path / "platform.yaml").write_text("project: t\n", encoding="utf-8")
        _fake_session(monkeypatch, tree=plugin_tree)
        (f,) = rf.check_session_argv(tmp_path)
        assert f.verdict == "not-checked"


class _Resp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode()

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_runner(monkeypatch, payload):
    monkeypatch.setattr(rf, "_runner_endpoint", lambda: ("127.0.0.1", "9999"))
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp(payload))


class TestCheck3Daemon:
    def test_config_newer_than_daemon_start_is_stale(self, monkeypatch, root):
        _fake_runner(
            monkeypatch,
            {
                "started_at": "2026-09-01T00:00:00+00:00",
                "config_inputs": [
                    {
                        "path": "/p/platform.yaml",
                        "mtime": "2026-09-05T00:00:00+00:00",
                        "exists": True,
                    }
                ],
            },
        )
        (f,) = rf.check_daemon_vs_config(root)
        assert f.verdict == "stale"
        assert "/p/platform.yaml" in f.reason
        assert f.remedy and "estart" in f.remedy

    def test_daemon_newer_than_config_is_fresh(self, monkeypatch, root):
        _fake_runner(
            monkeypatch,
            {
                "started_at": "2026-09-10T00:00:00+00:00",
                "config_inputs": [
                    {
                        "path": "/p/platform.yaml",
                        "mtime": "2026-09-05T00:00:00+00:00",
                        "exists": True,
                    }
                ],
            },
        )
        (f,) = rf.check_daemon_vs_config(root)
        assert f.verdict == "fresh", f

    def test_nonexistent_input_is_skipped_not_crashed(self, monkeypatch, root):
        """runner sends `{"path": "<static:default>", "mtime": null, "exists": false}`
        for an input that is a built-in default rather than a file."""
        _fake_runner(
            monkeypatch,
            {
                "started_at": "2026-09-10T00:00:00+00:00",
                "config_inputs": [{"path": "<static:default>", "mtime": None, "exists": False}],
            },
        )
        (f,) = rf.check_daemon_vs_config(root)
        assert f.verdict == "fresh"

    def test_pre_1_4_runner_is_not_checked(self, monkeypatch, root):
        """An older runner answers /status without started_at. That is 'could
        not check', not a healthy daemon."""
        _fake_runner(monkeypatch, {"ok": True, "version": "0.1.0"})
        (f,) = rf.check_daemon_vs_config(root)
        assert f.verdict == "not-checked"
        assert "started_at" in f.reason

    def test_no_endpoint_is_not_checked(self, monkeypatch, root):
        monkeypatch.setattr(rf, "_runner_endpoint", lambda: None)
        (f,) = rf.check_daemon_vs_config(root)
        assert f.verdict == "not-checked"

    def test_unreachable_runner_is_not_checked_not_a_crash(self, monkeypatch, root):
        monkeypatch.setattr(rf, "_runner_endpoint", lambda: ("127.0.0.1", "9"))
        import urllib.request

        def boom(*a, **k):
            raise OSError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", boom)
        (f,) = rf.check_daemon_vs_config(root)
        assert f.verdict == "not-checked"
        assert "unreachable" in f.reason


class TestDoctorMapping:
    def test_fresh_produces_no_doctor_noise(self, monkeypatch, root, plugin_tree):
        from otaman_plugin import doctor_checks

        monkeypatch.setattr(
            rf, "assess", lambda r: [rf.Finding("s", "session-inputs", "fresh", "ok")]
        )
        assert doctor_checks.check_runtime_freshness(root) == []

    def test_verdicts_map_to_severities_and_stable_codes(self, monkeypatch, root):
        from otaman_plugin import doctor_checks

        monkeypatch.setattr(
            rf,
            "assess",
            lambda r: [
                rf.Finding("s1", "session-inputs", "stale", "r", remedy="fix"),
                rf.Finding("s2", "daemon-config", "not-checked", "r"),
            ],
        )
        out = doctor_checks.check_runtime_freshness(root)
        assert [w.severity for w in out] == ["warn", "info"]
        assert [w.code for w in out] == [
            "SRF_SESSION_INPUTS_STALE",
            "SRF_DAEMON_CONFIG_NOT_CHECKED",
        ]

    def test_registered_in_run_all_checks(self):
        """An unregistered check never runs. Found the hard way on nss 1.1,
        where every test called the function directly and deleting its
        registration broke nothing."""
        import inspect

        from otaman_plugin import doctor_checks

        assert "check_runtime_freshness" in inspect.getsource(doctor_checks.run_all_checks)


class TestDetectionNeverEnforcement:
    def test_no_restart_machinery_anywhere_in_the_module(self):
        """D1: restarting a stale session destroys conversation context and
        in-progress work. Every finding names a remedy; nothing performs one."""
        src = Path(rf.__file__).read_text(encoding="utf-8")
        for forbidden in ("kill(", "SIGTERM", "SIGKILL", "terminate(", "systemctl restart"):
            assert forbidden not in src, f"{forbidden!r} — this check detects, it does not enforce"


class TestProgramScoping:
    """A host can run several programs' fleets at once. Doctor for program A
    must not report program B's sessions — it would name subjects the operator
    cannot act on from here, and would make the output depend on who else is
    logged in. It also kept `run_all_checks` hermetic: an unrelated root now
    yields [] rather than findings about whatever happens to be running.
    """

    def _root_with_repo(self, tmp_path: Path, repo_dir: Path) -> Path:
        root = tmp_path / "meta"
        root.mkdir()
        (root / "platform.yaml").write_text(
            f"project: t\nrepos:\n  - name: r\n    path: {repo_dir}\n", encoding="utf-8"
        )
        return root

    def test_session_in_a_declared_repo_is_in_scope(self, monkeypatch, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        root = self._root_with_repo(tmp_path, repo)
        monkeypatch.setattr(rf, "_agent_pids", lambda: [7])
        monkeypatch.setattr(rf, "_proc_cwd", lambda pid: repo)
        assert rf._sessions_for(root) == [7]

    def test_session_in_another_program_is_excluded(self, monkeypatch, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        other = tmp_path / "elsewhere"
        other.mkdir()
        root = self._root_with_repo(tmp_path, repo)
        monkeypatch.setattr(rf, "_agent_pids", lambda: [7])
        monkeypatch.setattr(rf, "_proc_cwd", lambda pid: other)
        assert rf._sessions_for(root) == []

    def test_unenumerable_still_propagates_as_none(self, monkeypatch, tmp_path):
        """Scoping must not turn 'could not look' into 'nothing here'."""
        root = self._root_with_repo(tmp_path, tmp_path / "r")
        monkeypatch.setattr(rf, "_agent_pids", lambda: None)
        assert rf._sessions_for(root) is None

    def test_assess_on_a_non_program_root_is_silent(self, tmp_path):
        """The hermeticity guard: no platform.yaml means there is nothing for a
        runtime to be fresh RELATIVE TO, so doctor says nothing rather than
        reporting the host's unrelated processes."""
        assert rf.assess(tmp_path) == []


class TestCheck4BundleSkew:
    """The comparand here was wrong TWICE before it was pinned, and both wrong
    answers failed the same way: a verdict that fires on a healthy workspace.

    1. `otaman --version` vs a sibling's pyproject version — deploy stamps the
       RELEASE version onto components while each repo keeps its own, so
       `0.5.14` vs `0.5.0` differ on a perfectly current machine.
    2. `installed_at` vs commits-on-sibling-since — sibling mains run ahead of
       the last cut BY DESIGN; that is the cadence working, not drift.

    `test_siblings_ahead_of_the_cut_is_fresh_not_skewed` is the guard for the
    second, and is the reason this check is usable at all: a section that
    flags normal operation is one operators stop reading.
    """

    def _host(self, tmp_path, *, installed: str, cuts: list[str]) -> Path:
        home = tmp_path / "home"
        (home / ".otaman").mkdir(parents=True)
        (home / ".otaman" / "release.yaml").write_text(
            f"release: {installed}\nversion: '{installed.lstrip('v')}'\n", encoding="utf-8"
        )
        deploy = tmp_path / "otaman-deploy"
        (deploy / "release-manifests").mkdir(parents=True)
        for c in cuts:
            (deploy / "release-manifests" / f"{c}.json").write_text("{}", encoding="utf-8")
        root = tmp_path / "meta"
        root.mkdir()
        (root / "platform.yaml").write_text(
            f"project: t\nrepos:\n  - name: otaman-deploy\n    path: {deploy}\n", encoding="utf-8"
        )
        return root, home

    def test_cut_but_not_rolled_is_skewed(self, monkeypatch, tmp_path):
        root, home = self._host(
            tmp_path, installed="v0.5.14", cuts=["v0.5.13", "v0.5.14", "v0.5.15"]
        )
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        (f,) = rf.check_bundle_vs_latest_release(root)
        assert f.verdict == "skewed", f
        assert "v0.5.14" in f.reason and "v0.5.15" in f.reason, "must name BOTH release versions"
        assert f.remedy and "Roll" in f.remedy
        assert f.evidence == {"installed": "v0.5.14", "latest_cut": "v0.5.15"}

    def test_siblings_ahead_of_the_cut_is_fresh_not_skewed(self, monkeypatch, tmp_path):
        """The pin's decisive clause. A host ON the latest cut is healthy even
        though every sibling main has advanced past it — that is the release
        cadence, and calling it skew is the cry-wolf failure."""
        root, home = self._host(tmp_path, installed="v0.5.15", cuts=["v0.5.14", "v0.5.15"])
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        (f,) = rf.check_bundle_vs_latest_release(root)
        assert f.verdict == "fresh", (
            "a host on the latest cut rendered SKEWED — this is the comparand "
            "failure that was rejected twice"
        )
        assert "normal state" in f.reason

    def test_ahead_of_the_latest_manifest_is_not_skewed(self, monkeypatch, tmp_path):
        """A host rolled from a cut whose manifest this checkout predates must
        not be told to roll backwards."""
        root, home = self._host(tmp_path, installed="v0.6.0", cuts=["v0.5.15"])
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        (f,) = rf.check_bundle_vs_latest_release(root)
        assert f.verdict == "fresh", f

    def test_no_release_yaml_is_not_checked(self, monkeypatch, tmp_path):
        root, home = self._host(tmp_path, installed="v0.5.14", cuts=["v0.5.14"])
        (home / ".otaman" / "release.yaml").unlink()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        (f,) = rf.check_bundle_vs_latest_release(root)
        assert f.verdict == "not-checked"

    def test_tenant_without_a_deploy_checkout_is_not_checked(self, monkeypatch, tmp_path):
        """The ordinary tenant case: nothing to learn the latest cut from. It
        must say so rather than render fresh."""
        home = tmp_path / "home"
        (home / ".otaman").mkdir(parents=True)
        (home / ".otaman" / "release.yaml").write_text("release: v0.5.14\n", encoding="utf-8")
        root = tmp_path / "meta"
        root.mkdir()
        (root / "platform.yaml").write_text("project: t\n", encoding="utf-8")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        (f,) = rf.check_bundle_vs_latest_release(root)
        assert f.verdict == "not-checked"
        assert "otaman-deploy" in f.reason

    def test_skewed_maps_to_a_doctor_warning(self, monkeypatch, root):
        from otaman_plugin import doctor_checks

        monkeypatch.setattr(
            rf, "assess", lambda r: [rf.Finding("b", "bundle-skew", "skewed", "r", remedy="roll")]
        )
        (w,) = doctor_checks.check_runtime_freshness(root)
        assert w.severity == "warn"
        assert w.code == "SRF_BUNDLE_SKEW_SKEWED"
