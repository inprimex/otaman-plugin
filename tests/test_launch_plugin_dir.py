"""launcher-plugin-dir-parity: launch-agents.sh threads --plugin-dir into
every claude invocation it builds, resolved from platform.yaml's
`runner.agent_bootstrap.plugin_dir` via launch-resolve.py's OTAMAN_PLUGIN_DIR
export.

deploy-agent finding (20260916T205241): the bash launcher never passed
--plugin-dir anywhere, so a bash-launched session had no otaman slash
commands regardless of what platform.yaml declared — the .ps1 only covered
its own SSH-remote-bash branch via a different, Windows-only field
(launch-settings.yaml's ssh_plugin_path), which never applied to a local
bash launch either.

Drives the real scripts/launch-agents.sh with fake otaman/tmux/claude on a
hermetic PATH, same harness as test_launch_agent_env.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_launch_agent_env import (  # noqa: E402
    HAVE_PYTHON3,
    _make_bindir,
    _run_launcher,
    _write_exec,
)

pytestmark = pytest.mark.skipif(not HAVE_PYTHON3, reason="python3 needed to parse platform.yaml")


def _make_root_with_plugin_dir(
    tmp_path: Path, *, owner: str = "agent", plugin_dir: str | None
) -> Path:
    root = tmp_path / "meta"
    root.mkdir()
    (root / ".otaman").write_text("", encoding="utf-8")
    runner_block = (
        f"runner:\n  agent_bootstrap:\n    plugin_dir: {plugin_dir}\n" if plugin_dir else ""
    )
    platform_text = (
        f"project: proj\nrepos:\n  - name: {owner}\n    owner: {owner}\n    path: .\n{runner_block}"
    )
    (root / "platform.yaml").write_text(platform_text, encoding="utf-8")
    return root


class TestTmuxFleetThreadsPluginDir:
    def test_plugin_dir_reaches_send_keys(self, tmp_path):
        plugin_tree = tmp_path / "otaman-plugin-tree"
        plugin_tree.mkdir()
        root = _make_root_with_plugin_dir(tmp_path, plugin_dir=str(plugin_tree))

        args_log = tmp_path / "run.log"
        tmux_log = tmp_path / "tmux.log"
        bindir = _make_bindir(tmp_path, args_log=args_log, with_tmux=True, tmux_log=tmux_log)
        r = _run_launcher(root, bindir, "--shell", "tmux", "--no-runner")
        assert r.returncode == 0, r.stderr
        log = tmux_log.read_text()
        assert f"--plugin-dir {plugin_tree}" in log

    def test_unset_plugin_dir_omits_the_flag(self, tmp_path):
        root = _make_root_with_plugin_dir(tmp_path, plugin_dir=None)
        args_log = tmp_path / "run.log"
        tmux_log = tmp_path / "tmux.log"
        bindir = _make_bindir(tmp_path, args_log=args_log, with_tmux=True, tmux_log=tmux_log)
        r = _run_launcher(root, bindir, "--shell", "tmux", "--no-runner")
        assert r.returncode == 0, r.stderr
        assert "--plugin-dir" not in tmux_log.read_text()

    def test_missing_directory_on_disk_omits_the_flag(self, tmp_path):
        """A stale/misconfigured plugin_dir degrades to unset rather than
        passing a --plugin-dir claude would reject."""
        root = _make_root_with_plugin_dir(tmp_path, plugin_dir="/no/such/otaman-plugin-tree")
        args_log = tmp_path / "run.log"
        tmux_log = tmp_path / "tmux.log"
        bindir = _make_bindir(tmp_path, args_log=args_log, with_tmux=True, tmux_log=tmux_log)
        r = _run_launcher(root, bindir, "--shell", "tmux", "--no-runner")
        assert r.returncode == 0, r.stderr
        assert "--plugin-dir" not in tmux_log.read_text()


class TestBashModeThreadsPluginDir:
    def test_plugin_dir_reaches_acting_lock_run_wrapper(self, tmp_path):
        plugin_tree = tmp_path / "otaman-plugin-tree"
        plugin_tree.mkdir()
        root = _make_root_with_plugin_dir(
            tmp_path, owner="backend-agent", plugin_dir=str(plugin_tree)
        )

        args_log = tmp_path / "run.log"
        bindir = _make_bindir(tmp_path, args_log=args_log, with_tmux=False)
        r = _run_launcher(root, bindir)
        assert r.returncode == 0, r.stderr
        assert f"--plugin-dir {plugin_tree}" in args_log.read_text()

    def test_passive_mirror_fallback_carries_plugin_dir(self, tmp_path):
        """No-tmux path (task 1.4): when acting-lock refuses (held), the
        passive read-only mirror `exec claude -c` also gets --plugin-dir —
        it's a separate hardcoded line, not built from the same array."""
        plugin_tree = tmp_path / "otaman-plugin-tree"
        plugin_tree.mkdir()
        root = _make_root_with_plugin_dir(
            tmp_path, owner="backend-agent", plugin_dir=str(plugin_tree)
        )

        args_log = tmp_path / "run.log"
        exec_log = tmp_path / "exec.log"
        bindir = _make_bindir(tmp_path, args_log=args_log, with_tmux=False)
        # Refuse the lock (exit 2) so the launcher falls through to the
        # passive-mirror `exec claude ...` line, and have that fake `claude`
        # record its own argv instead of exiting cleanly.
        _write_exec(
            bindir / "otaman",
            f"""#!/usr/bin/env bash
if [[ "$1" == "acting-lock" && "$2" == "run" ]]; then
    printf '%s\\n' "$*" >> {args_log}
    exit 2
fi
if [[ "$1" == "acting-lock" && "$2" == "probe" ]]; then
    echo '{{}}'
    exit 0
fi
exit 0
""",
        )
        _write_exec(bindir / "claude", f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> {exec_log}\n')
        r = _run_launcher(root, bindir)
        # `exec claude ...` replaces the launcher process, so the final exit
        # code is the fake claude's (0), not the acting-lock refusal (2).
        assert r.returncode == 0, r.stderr
        assert f"--plugin-dir {plugin_tree}" in exec_log.read_text()
