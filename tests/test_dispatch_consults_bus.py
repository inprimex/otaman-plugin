"""map_tasks consults the bus before assigning — the tick-latency window.

`otaman complete` files a task-complete on the bus; spec-agent applies the
tasks.md tick on their next session sweep. Between those two moments the file
still reads `- [ ]`, so any specs push re-dispatches finished work.

Measured (spec-agent's ruling, 20260925T171639): cli-agent filed
session-runtime-freshness 1.3 complete at 2026-09-25T11:52:04Z; the 14:56 and
14:58 specs pushes re-assigned it to them twice. Three of plugin-agent's own
completed tasks were re-dispatched the same way in the same window. cli had the
context to recognise it; an agent with less would redo the work.

The ruling: during the window the BUS FILING is the authority, and tasks.md
remains the durable record it syncs to.

FAILURE DIRECTION, chosen deliberately: a `**Completed**:` spec this cannot
parse confidently yields NO ids, so the task is dispatched. Re-dispatching
finished work is noisy and recoverable — a human or the agent notices. Skipping
a task that was never completed is silent, and the work is simply lost.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from otaman_plugin.map_tasks import (
    _ALL,
    _parse_completed_spec,
    filed_complete_ids,
    task_id_of,
)

CLI_FILED_AT = "2026-09-25T11:52:04Z"
REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _unpin_root(monkeypatch):
    # bus-test-isolation 4.2 pins OTAMAN_ROOT for the whole suite; these tests
    # resolve a root from scratch through a `.otaman` marker, so the pin has to
    # come off the child env too.
    monkeypatch.delenv("OTAMAN_ROOT", raising=False)
    monkeypatch.delenv("MAESTRO_ROOT", raising=False)


def _program(tmp_path: Path) -> Path:
    root = tmp_path / "meta"
    (root / ".agents" / "bus" / "active" / "acks").mkdir(parents=True)
    (root / "platform.yaml").write_text(
        yaml.safe_dump(
            {
                "project": "p",
                "spec_policy": {"enforcement": "warn"},
                "repos": [
                    {"name": "otaman-cli", "path": "../otaman-cli", "owner": "cli-agent"},
                    {"name": "otaman-plugin", "path": "../otaman-plugin", "owner": "plugin-agent"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


def _file_completion(root: Path, *, change: str, completed: str, frm: str = "cli-agent") -> None:
    (root / ".agents" / "bus" / "active" / f"20260925T115204-{frm}-to-spec-{change}.md").write_text(
        f"---\nid: x\nfrom: {frm}\nto: spec-agent\ntype: task-complete\n"
        f"change: {change}\ntimestamp: {CLI_FILED_AT}\nstatus: pending\n---\n\n"
        f"**Agent**: {frm}\n**Change**: {change}\n**Completed**: {completed}\n",
        encoding="utf-8",
    )


class TestTaskIdExtraction:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("1.3 @otaman-cli console session view renders", "1.3"),
            ("2.1 @otaman-specs E2E on the live fleet", "2.1"),
            ("1B.4 @otaman-core something", "1B.4"),
            ("10.12 deep numbering", "10.12"),
            ("no leading id here", None),
        ],
    )
    def test_ids(self, text, expected):
        assert task_id_of(text) == expected


class TestCompletedSpecParsing:
    @pytest.mark.parametrize(
        "spec,expected",
        [
            ("tasks 1.3", {"1.3"}),
            ("1.1, 1.2", {"1.1", "1.2"}),
            ("tasks 0.1,0.2,0.3", {"0.1", "0.2", "0.3"}),
            ("all tasks", {_ALL}),
            ("tasks 1.1-1.4", {"1.1", "1.2", "1.3", "1.4"}),
        ],
    )
    def test_recognised_forms(self, spec, expected):
        assert _parse_completed_spec(spec) == expected

    @pytest.mark.parametrize("spec", ["live-test", "", "   ", "see the PR"])
    def test_unparseable_yields_nothing_so_the_task_is_dispatched(self, spec):
        """The safe direction. Skipping a task that was never completed loses
        the work silently; re-dispatching a finished one is merely noisy."""
        assert _parse_completed_spec(spec) == set()


class TestFiledCompleteIds:
    def test_clis_real_1_3_window(self, tmp_path):
        """The measured case: filed 11:52:04Z, re-dispatched 14:56 and 14:58."""
        root = _program(tmp_path)
        _file_completion(root, change="session-runtime-freshness", completed="tasks 1.3")
        cfg = yaml.safe_load((root / "platform.yaml").read_text())
        assert "1.3" in filed_complete_ids(root, "session-runtime-freshness", cfg)

    def test_a_resolved_filing_still_counts(self, tmp_path):
        """'pending OR resolved' — an acked task-complete is still a filing.
        Acks live beside the message, so the message itself is unchanged."""
        root = _program(tmp_path)
        _file_completion(root, change="session-runtime-freshness", completed="tasks 1.3")
        (root / ".agents" / "bus" / "active" / "acks").joinpath("x.ack").write_text(
            "resolved\n", encoding="utf-8"
        )
        cfg = yaml.safe_load((root / "platform.yaml").read_text())
        assert "1.3" in filed_complete_ids(root, "session-runtime-freshness", cfg)

    def test_another_changes_filing_does_not_leak(self, tmp_path):
        """change+id, not id alone — 1.3 of a different change is a different
        task, and treating it as done would silently drop real work."""
        root = _program(tmp_path)
        _file_completion(root, change="some-other-change", completed="tasks 1.3")
        cfg = yaml.safe_load((root / "platform.yaml").read_text())
        assert filed_complete_ids(root, "session-runtime-freshness", cfg) == set()

    def test_all_tasks_filing_covers_everything(self, tmp_path):
        root = _program(tmp_path)
        _file_completion(root, change="c", completed="all tasks")
        cfg = yaml.safe_load((root / "platform.yaml").read_text())
        assert filed_complete_ids(root, "c", cfg) == {_ALL}

    def test_no_bus_is_empty_not_an_error(self, tmp_path):
        root = tmp_path / "bare"
        root.mkdir()
        assert filed_complete_ids(root, "c", {}) == set()


class TestDispatchEndToEnd:
    """The behaviour spec-agent asked for, through `main()`: a filed-complete
    task is not re-dispatched, and the skip is counted AND named."""

    def _change(self, root: Path, name: str, body: str) -> Path:
        d = root.parent / "specs" / "openspec" / "changes" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "tasks.md").write_text(body, encoding="utf-8")
        (root.parent / "specs" / ".otaman").write_text(
            f"../{root.name}\nagent: spec-agent\n", encoding="utf-8"
        )
        return d / "tasks.md"

    def _run(self, tasks_path: Path, home: Path):
        import os
        import subprocess
        import sys

        env = {
            **os.environ,
            "PYTHONPATH": f"{REPO / 'src'}:{REPO.parent / 'otaman-core' / 'src'}",
            "HOME": str(home),
        }
        env.pop("OTAMAN_ROOT", None)
        env.pop("MAESTRO_ROOT", None)
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "map-tasks.py"), str(tasks_path)],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        try:
            report = json.loads(proc.stdout)
        except Exception as exc:  # pragma: no cover - diagnostic path
            raise AssertionError(
                f"map-tasks stdout was not JSON ({exc}).\n"
                f"rc={proc.returncode}\nSTDOUT={proc.stdout!r}\nSTDERR={proc.stderr}"
            ) from exc
        return proc, report

    def test_clis_1_3_is_not_re_dispatched(self, tmp_path):
        """The regression, end to end. tasks.md still says `- [ ]` because the
        sweep has not run; the bus says it is done; nothing is re-assigned."""
        root = _program(tmp_path.resolve())
        tasks = self._change(
            root,
            "session-runtime-freshness",
            "# tasks\n\n- [ ] 1.3 @otaman-cli console session view renders the verdicts\n",
        )
        _file_completion(root, change="session-runtime-freshness", completed="tasks 1.3")

        proc, report = self._run(tasks, tmp_path)
        assert report.get("dispatched") == 0, proc.stderr
        assert report.get("filed_complete") == 1
        assert "filed-complete, skipped" in proc.stderr
        assert "1.3" in proc.stderr, "the skipped task must be NAMED, not just counted"

    def test_an_unfiled_task_is_still_dispatched(self, tmp_path):
        """The consult must not become a blanket suppression."""
        root = _program(tmp_path.resolve())
        tasks = self._change(
            root,
            "session-runtime-freshness",
            "# tasks\n\n- [ ] 1.3 @otaman-cli console view\n"
            "- [ ] 2.9 @otaman-plugin something nobody filed\n",
        )
        _file_completion(root, change="session-runtime-freshness", completed="tasks 1.3")

        proc, report = self._run(tasks, tmp_path)
        assert report.get("filed_complete") == 1
        assert report.get("dispatched") == 1, f"the unfiled task was not dispatched: {proc.stderr}"


class TestRetractionOutranksTheFiling:
    """A withdrawn completion must be able to come back.

    Gap exposed by spec-agent un-ticking sam 1.5 (20260926T183603): the consult
    skipped re-dispatch citing the old filing, so an over-claimed task could
    never re-dispatch — the consult would cite a withdrawn filing forever.

    Un-ticking is how a retraction is already expressed, so this needs no new
    message type. The discriminator is narrow on purpose: only a commit that
    turns THIS line from `[x]` to `[ ]` counts. An ordinary tasks.md edit is
    not a retraction — which is exactly what keeps the original tick-latency
    fix intact, since the 14:56 pushes edited tasks.md without un-ticking
    cli's 1.3.
    """

    def _git_repo(self, tmp_path: Path):
        import subprocess

        root = _program(tmp_path.resolve())
        specs = tmp_path.resolve() / "specs"
        d = specs / "openspec" / "changes" / "c"
        d.mkdir(parents=True)
        (specs / ".otaman").write_text("../meta\nagent: spec-agent\n", encoding="utf-8")
        for cmd in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "t@e.com"],
            ["git", "config", "user.name", "t"],
        ):
            subprocess.run(cmd, cwd=specs, check=True, capture_output=True)
        return root, specs, d / "tasks.md"

    def _commit(self, specs: Path, tasks: Path, body: str, msg: str):
        import subprocess

        tasks.write_text(body, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=specs, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", msg], cwd=specs, check=True, capture_output=True
        )

    def test_an_untick_after_the_filing_re_dispatches(self, tmp_path):
        from otaman_plugin.map_tasks import last_untick_at

        root, specs, tasks = self._git_repo(tmp_path)
        self._commit(specs, tasks, "# t\n\n- [ ] 1.5 @otaman-r the task\n", "init")
        self._commit(specs, tasks, "# t\n\n- [x] 1.5 @otaman-r the task\n", "tick")
        self._commit(specs, tasks, "# t\n\n- [ ] 1.5 @otaman-r the task\n", "UN-TICK: retracted")

        assert last_untick_at(tasks, "1.5") is not None, "the un-tick commit was not detected"

    def test_an_ordinary_edit_is_not_a_retraction(self, tmp_path):
        """The guard on the original fix. cli's 1.3 was never ticked; the
        14:56 push merely edited the file. If that counted as a retraction the
        tick-latency bug comes straight back."""
        from otaman_plugin.map_tasks import last_untick_at

        root, specs, tasks = self._git_repo(tmp_path)
        self._commit(specs, tasks, "# t\n\n- [ ] 1.3 @otaman-r console view\n", "init")
        self._commit(
            specs,
            tasks,
            "# t\n\n- [ ] 1.3 @otaman-r console view\n- [ ] 2.9 @otaman-r new\n",
            "specs push: add 2.9",
        )
        assert last_untick_at(tasks, "1.3") is None, (
            "an edit that did not un-tick 1.3 was read as a retraction — this "
            "reinstates the re-dispatch bug the consult exists to fix"
        )

    def test_another_tasks_untick_does_not_retract_mine(self, tmp_path):
        from otaman_plugin.map_tasks import last_untick_at

        root, specs, tasks = self._git_repo(tmp_path)
        self._commit(specs, tasks, "# t\n\n- [x] 1.1 @otaman-r a\n- [ ] 1.3 @otaman-r b\n", "init")
        self._commit(
            specs, tasks, "# t\n\n- [ ] 1.1 @otaman-r a\n- [ ] 1.3 @otaman-r b\n", "un-tick 1.1"
        )
        assert last_untick_at(tasks, "1.1") is not None
        assert last_untick_at(tasks, "1.3") is None, "1.1's retraction leaked onto 1.3"

    def test_no_git_degrades_to_the_current_behaviour(self, tmp_path):
        """Without history we cannot see a retraction. Keep skipping — the
        base case is 'no retraction', and re-dispatching everything whenever
        history is unreadable would reinstate the original bug broadly."""
        from otaman_plugin.map_tasks import last_untick_at

        plain = tmp_path / "nogit"
        plain.mkdir()
        f = plain / "tasks.md"
        f.write_text("- [ ] 1.1 @otaman-r x\n", encoding="utf-8")
        assert last_untick_at(f, "1.1") is None

    def test_dispatch_re_sends_a_retracted_task_end_to_end(self, tmp_path):
        """Drives `main()`, not just `last_untick_at`.

        The unit tests above pass even with the retraction check removed from
        the dispatch path — they exercise the helper, not the caller. Caught by
        re-running the sabotage with a sha1 check that it applied; without this
        test the helper could be perfect and never consulted.
        """

        root, specs, tasks = self._git_repo(tmp_path)
        self._commit(specs, tasks, "# t\n\n- [ ] 1.5 @otaman-cli the task\n", "init")
        self._commit(specs, tasks, "# t\n\n- [x] 1.5 @otaman-cli the task\n", "tick")
        (root / ".agents" / "bus" / "active" / "f.md").write_text(
            "---\ntype: task-complete\nchange: c\ntimestamp: 2020-01-01T00:00:00Z\n---\n\n"
            "**Completed**: tasks 1.5\n",
            encoding="utf-8",
        )
        self._commit(specs, tasks, "# t\n\n- [ ] 1.5 @otaman-cli the task\n", "UN-TICK: retracted")

        e2e = TestDispatchEndToEnd()
        proc, report = e2e._run(tasks, tmp_path)
        assert report.get("retracted") == 1, (
            f"a task un-ticked after its filing was not re-dispatched: {proc.stderr}"
        )
        assert report.get("filed_complete") == 0
        assert report.get("dispatched") == 1
        assert "retracted since filing, re-dispatched" in proc.stderr, "the re-send must be NAMED"

    def test_dispatch_still_skips_when_there_was_no_untick(self, tmp_path):
        """The other half: cli's window, driven through main(). A filing with
        no un-tick behind it still suppresses re-dispatch."""
        root, specs, tasks = self._git_repo(tmp_path)
        self._commit(specs, tasks, "# t\n\n- [ ] 1.3 @otaman-cli console view\n", "init")
        (root / ".agents" / "bus" / "active" / "f.md").write_text(
            "---\ntype: task-complete\nchange: c\ntimestamp: 2026-09-25T11:52:04Z\n---\n\n"
            "**Completed**: tasks 1.3\n",
            encoding="utf-8",
        )
        self._commit(
            specs,
            tasks,
            "# t\n\n- [ ] 1.3 @otaman-cli console view\n- [ ] 2.9 @otaman-cli new\n",
            "specs push: add 2.9",
        )
        e2e = TestDispatchEndToEnd()
        proc, report = e2e._run(tasks, tmp_path)
        assert report.get("filed_complete") == 1, proc.stderr
        assert report.get("retracted") == 0
        assert report.get("dispatched") == 1, "the genuinely new task must still go out"
