"""identity-divergence-hardening 1.3: launch generation sets OTAMAN_AGENT
per-pane/per-process, never via a machine-wide or tmux server-global
mechanism, regenerated from platform.yaml's repos[].owner (the same value
agents.yaml validates against, per otaman-cli's 1.1).

pmeets incident (proposal): a phantom agent status persisted for 17 hours
because nothing ever exported OTAMAN_AGENT into the launched pane's own
process — identity fell back to shared, last-writer-wins state instead.

Drives the real scripts/launch-agents.sh with fake otaman/tmux/claude on a
hermetic PATH, same harness as test_launch_acting_lock.py.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
BASH_LAUNCHER = REPO / "scripts" / "launch-agents.sh"
PS1_LAUNCHER = REPO / "scripts" / "launch-agents.ps1"

HAVE_BASH = shutil.which("bash") is not None
HAVE_PYTHON3 = shutil.which("python3") is not None

pytestmark = pytest.mark.skipif(not HAVE_BASH, reason="bash not on PATH")

_COREUTILS = (
    "bash",
    "python3",
    "sed",
    "grep",
    "tr",
    "date",
    "mkdir",
    "dirname",
    "cat",
    "cut",
    "env",
    "uname",
    "seq",
    "sleep",
)


def _make_otaman_root(tmp_path: Path, *, project: str = "proj", owner: str = "agent") -> Path:
    root = tmp_path / "meta"
    root.mkdir()
    (root / ".otaman").write_text("", encoding="utf-8")
    (root / "platform.yaml").write_text(
        f"project: {project}\nrepos:\n  - name: {owner}\n    owner: {owner}\n    path: .\n",
        encoding="utf-8",
    )
    return root


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _make_bindir(
    tmp_path: Path,
    *,
    args_log: Path,
    with_tmux: bool,
    tmux_log: Path | None = None,
) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in _COREUTILS:
        real = shutil.which(tool)
        if real:
            (bindir / tool).symlink_to(real)

    _write_exec(
        bindir / "otaman",
        f"""#!/usr/bin/env bash
if [[ "$1" == "acting-lock" && "$2" == "run" ]]; then
    printf '%s\\n' "$*" >> {args_log}
    exit 0
fi
if [[ "$1" == "acting-lock" && "$2" == "probe" ]]; then
    exit 0
fi
exit 0
""",
    )

    if with_tmux:
        _write_exec(
            bindir / "tmux",
            f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> {tmux_log}
case "$1" in
  has-session) exit 1 ;;
  *) exit 0 ;;
esac
""",
        )

    _write_exec(bindir / "claude", "#!/usr/bin/env bash\nexit 0\n")
    return bindir


def _run_launcher(root: Path, bindir: Path, *extra_args: str):
    env = {"PATH": str(bindir), "HOME": str(root.parent)}
    return subprocess.run(
        [shutil.which("bash"), str(BASH_LAUNCHER), *extra_args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


@pytest.mark.skipif(not HAVE_PYTHON3, reason="python3 needed to parse platform.yaml")
class TestBashModeExportsAgentEnv:
    def test_no_tmux_wraps_loop_with_exported_agent(self, tmp_path):
        """`--shell bash` (default), no tmux: the acting-lock run wrapper's
        `bash -lc` payload exports OTAMAN_AGENT for that process only."""
        root = _make_otaman_root(tmp_path, owner="backend-agent")
        args_log = tmp_path / "run.log"
        bindir = _make_bindir(tmp_path, args_log=args_log, with_tmux=False)
        r = _run_launcher(root, bindir)
        assert r.returncode == 0, r.stderr
        argline = args_log.read_text()
        assert "export OTAMAN_AGENT=backend-agent" in argline

    def test_tmux_present_sends_exported_agent_into_pane(self, tmp_path):
        """`--shell bash` with tmux: the identity pane's send-keys line
        carries the export too (create-and-wrap path)."""
        root = _make_otaman_root(tmp_path, owner="backend-agent")
        args_log = tmp_path / "run.log"
        tmux_log = tmp_path / "tmux.log"
        bindir = _make_bindir(tmp_path, args_log=args_log, with_tmux=True, tmux_log=tmux_log)
        r = _run_launcher(root, bindir, "--interactive")
        assert r.returncode == 0, r.stderr
        # send-keys shell-escapes the payload (printf %q), so spaces/semicolons
        # carry backslashes — check the substring survives escaping either way.
        log = tmux_log.read_text()
        assert "OTAMAN_AGENT=backend-agent" in log
        assert "export" in log


@pytest.mark.skipif(not HAVE_PYTHON3, reason="python3 needed to parse platform.yaml")
class TestTmuxFleetModeExportsAgentEnv:
    def test_per_repo_send_keys_carries_that_repos_owner(self, tmp_path):
        """`--shell tmux` (the multi-repo fleet loop): each repo's send-keys
        line exports OTAMAN_AGENT from ITS OWN owner, not a shared value."""
        root = tmp_path / "meta"
        root.mkdir()
        (root / ".otaman").write_text("", encoding="utf-8")
        (root / "platform.yaml").write_text(
            "project: proj\n"
            "repos:\n"
            "  - name: api\n"
            "    owner: backend-agent\n"
            "    path: .\n"
            "  - name: web\n"
            "    owner: frontend-agent\n"
            "    path: .\n",
            encoding="utf-8",
        )
        args_log = tmp_path / "run.log"
        tmux_log = tmp_path / "tmux.log"
        bindir = _make_bindir(tmp_path, args_log=args_log, with_tmux=True, tmux_log=tmux_log)
        r = _run_launcher(root, bindir, "--shell", "tmux", "--no-runner")
        assert r.returncode == 0, r.stderr
        log = tmux_log.read_text()
        assert "export OTAMAN_AGENT=backend-agent" in log
        assert "export OTAMAN_AGENT=frontend-agent" in log


class TestNeverServerGlobal:
    def test_bash_launcher_never_sets_environment_dash_g_for_agent(self):
        """No actual `tmux set-environment -g ... OTAMAN_AGENT` invocation —
        the phrase may appear in comments explaining what NOT to do."""
        text = BASH_LAUNCHER.read_text(encoding="utf-8")
        assert "set-environment -g OTAMAN_AGENT" not in text

    def test_ps1_launcher_never_uses_machine_or_user_scope_for_agent(self):
        text = PS1_LAUNCHER.read_text(encoding="utf-8")
        assert "[Environment]::SetEnvironmentVariable" not in text or (
            "'Machine'" not in text and "'User'" not in text
        )


class TestPs1TemplatesCarryAgentEnv:
    """Static text-contract check (pwsh execution is gated elsewhere) — every
    rebuilt launch_commands template must stamp OTAMAN_AGENT from $r.owner."""

    def test_all_rebuild_sites_reference_agent_env(self):
        text = PS1_LAUNCHER.read_text(encoding="utf-8")
        assert text.count("$agentEnv") >= 4, (
            "expected $agentEnv computed and used at each launch_commands "
            "rebuild site — found fewer than 4 references"
        )
        assert "OTAMAN_AGENT='$agentEnv'" in text
        assert "$env:OTAMAN_AGENT = '$agentEnv'" in text
