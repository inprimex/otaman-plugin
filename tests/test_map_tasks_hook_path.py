"""scripts/map-tasks.py resolves the project root in the DOCUMENTED layout.

The defect (deploy-agent 20260921T152252, from mildef/haulops via Roman, and
reproduced here before fixing): `scripts/map-tasks.py` carried its own 8-level
ancestor walk for `platform.yaml`. In the dedicated-otaman-folder layout that
can NEVER succeed — platform.yaml lives in the sibling `<program>-otaman/`, so
it is not an ancestor of the specs repo. Hook-driven dispatch was a silent,
total failure:

    $ python3 scripts/map-tasks.py .../otaman-specs/openspec/changes/x/tasks.md
    [map-tasks] platform.yaml not found within 8 levels above ...
    $ echo $?
    0

`otaman notify-change` was unaffected because the MODULE
(`otaman_plugin.map_tasks`) already consumes the shared resolver
(`otaman_core._resolve.find_maestro_root`, which follows the repo's `.otaman`
marker). Two implementations of "find the project root", one correct, and the
hook happened to call the wrong one — the shared-logic-single-home shape.

The fix deletes the duplicate rather than deepening `_MAX_WALK_UP`, which
would only mask it in shallower trees.

These tests use a SIBLING-LAYOUT sandbox (specs repo beside the otaman folder,
marker pointing across) because that is the layout the bug is specific to — a
fixture with platform.yaml overhead would pass against the broken version.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "map-tasks.py"


@pytest.fixture(autouse=True)
def _unpin_root(monkeypatch):
    """bus-test-isolation 4.2 footgun: isolate_bus PINS OTAMAN_ROOT, which the
    resolver would prefer over this suite's own sandbox."""
    monkeypatch.delenv("OTAMAN_ROOT", raising=False)
    monkeypatch.delenv("MAESTRO_ROOT", raising=False)


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    """The documented layout: otaman folder and specs repo as SIBLINGS.

    platform.yaml is deliberately NOT an ancestor of tasks.md — that is the
    whole point of the bug.
    """
    meta = tmp_path / "proj-otaman"
    (meta / ".agents" / "bus" / "active" / "acks").mkdir(parents=True)
    (meta / "platform.yaml").write_text(
        "project: proj\n"
        "repos:\n"
        "  - name: otaman-plugin\n"
        "    path: ../otaman-plugin\n"
        "    owner: plugin-agent\n",
        encoding="utf-8",
    )
    (meta / ".agents" / "ownership.json").write_text(
        json.dumps(
            {
                "project": "proj",
                "repos": [
                    {"name": "otaman-plugin", "path": "../otaman-plugin", "owner": "plugin-agent"}
                ],
            }
        ),
        encoding="utf-8",
    )

    specs = tmp_path / "otaman-specs"
    change = specs / "openspec" / "changes" / "demo"
    change.mkdir(parents=True)
    (specs / ".otaman").write_text("../proj-otaman\nagent: spec-agent\n", encoding="utf-8")
    (change / "tasks.md").write_text(
        "# Tasks: demo\n\n- [ ] 1.1 @otaman-plugin do the thing\n", encoding="utf-8"
    )
    return meta, change / "tasks.md"


def _run(tasks_md: Path, home: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO / "src"),
        # The marker resolver rejects a marker pointing outside $HOME, so the
        # sandbox must look like it lives under one.
        "HOME": str(home),
    }
    env.pop("OTAMAN_ROOT", None)
    env.pop("MAESTRO_ROOT", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(tasks_md)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def _dispatched(meta: Path) -> list[str]:
    return sorted(p.name for p in (meta / ".agents" / "bus" / "active").glob("*.md"))


class TestSiblingLayoutDispatch:
    def test_resolves_root_across_the_sibling_boundary(self, tmp_path):
        """The regression. platform.yaml is not an ancestor of tasks.md, so
        the old ancestor walk could not succeed by construction."""
        meta, tasks_md = _layout(tmp_path)
        r = _run(tasks_md, tmp_path)
        assert r.returncode == 0, r.stderr
        assert "platform.yaml not found" not in (r.stdout + r.stderr)

    def test_actually_dispatches_a_task_assignment(self, tmp_path):
        """Resolving is not enough — the point is that agents get assigned."""
        meta, tasks_md = _layout(tmp_path)
        _run(tasks_md, tmp_path)
        dispatched = _dispatched(meta)
        assert dispatched, "no task-assignment written — dispatch is still dead"
        assert any("plugin-agent" in n for n in dispatched)

    def test_reports_the_task_as_assigned_not_unassigned(self, tmp_path):
        meta, tasks_md = _layout(tmp_path)
        r = _run(tasks_md, tmp_path)
        report = json.loads(r.stdout)
        assert report["assigned"] == 1, report
        assert report["unassigned"] == 0, report


class TestNoSecondRootResolver:
    def test_script_holds_no_ancestor_walk_of_its_own(self):
        """It is a shim now. A second "find the project root" is what broke
        this; deepening _MAX_WALK_UP would only mask it in shallower trees."""
        src = SCRIPT.read_text(encoding="utf-8")
        # Assert on CODE, not prose: the docstring legitimately names
        # _MAX_WALK_UP when explaining what was removed, and an earlier
        # version of this test failed on exactly that.
        assert "_MAX_WALK_UP = " not in src, "the walk constant is back"
        assert "def _find_project_root" not in src
        assert ".parent" not in src, "no ancestor walking of any shape"

    def test_delegates_to_the_module(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "otaman_plugin.map_tasks" in src


class TestFailsLoudlyNotSilently:
    def test_unimportable_module_exits_nonzero_with_a_reason(self, monkeypatch):
        """The old script returned 0 on EVERY failure path ("caller ignores
        exit codes anyway"), which is why the outage was invisible even
        without the hook's `|| true`. A dispatcher that cannot dispatch must
        say so.

        Patched rather than driven via PYTHONPATH: otaman_plugin is installed
        in this venv, so no path manipulation can hide it — an earlier
        version of this test passed for that reason, not because the code
        was right.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location("_shim", SCRIPT)
        shim = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shim)

        real_import = __import__

        def _fake(name, *a, **k):
            if name == "otaman_plugin.map_tasks":
                raise ImportError("simulated missing install")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake)
        assert shim.main() == 2


class TestHookWiring:
    def test_hook_uses_the_otaman_aware_interpreter(self):
        """A bare `python3` frequently cannot import otaman_plugin even where
        the workspace venv can — which is what resolve_otaman_python exists
        for, and what this path lacked."""
        hook = (REPO / "scripts" / "spec-change-hook.sh").read_text(encoding="utf-8")
        assert "resolve_otaman_python" in hook

    def test_hook_no_longer_discards_map_tasks_stderr(self):
        """`|| true` stays (a post-commit hook must never fail a commit), but
        silence was the actual defect — >/dev/null 2>&1 hid the one message
        that said dispatch had not happened."""
        hook = (REPO / "scripts" / "spec-change-hook.sh").read_text(encoding="utf-8")
        assert '"$MAP_TASKS" "$PWD/$tasks_file" >/dev/null 2>&1' not in hook
        assert "were NOT dispatched" in hook
